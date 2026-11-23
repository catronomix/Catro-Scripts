# Readerbox: full-screen document-to-speech reader for Chatterbox TTS
"""
			READERBOX
			==========
A full-screen reader that turns Markdown or plain text into narration through a
running Chatterbox TTS server. The left pane explores the current working
directory; opening a text file swaps that pane for settings and actions while
the right pane shows the text that will be spoken.

Usage:
	catro-scripts readerbox [--config PATH]

Configuration:
	readerbox-config.yaml lives beside this script, inside the catro-scripts
	install folder, and is gitignored. When it does not exist the script writes
	a commented template there and exits, asking for server and port first.
	Server, port, audio format, sample rate and turbo live only in the file;
	voice and generation parameters can also be changed in the TUI.

Keys:
	Up/Down	    move in the focused pane           Enter	open file / choose
	Tab	    switch pane focus                   Esc	back, cancel or quit
	Home/End    first/last                          PgUp/PgDn	page

Actions:
	[preview]    renders the first two sentences to a `.preview` file beside the
		     source and opens it for playback
	[render]     renders every chunk, merges the audio and saves it beside the
		     selected text file, with a progress popup while it works
	[save config] writes the current voice and generation settings to the config

Markdown handling:
	*italics*, (parentheses) and "quotes" become spaced dashes so they read as
	natural interjections. A line without final punctuation gets a comma and a
	paragraph without final punctuation gets a full stop. Paragraphs start new
	chunks; headings, subheadings and horizontal rules get a short silence.

Exit status:
	0 = clean quit, 2 = configuration or terminal error, 1 = runtime failure.
"""

import argparse
import io
import json
import os
import random
import re
import subprocess
import sys
import time
import wave
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlsplit, urlunsplit

import tui

CONFIG_NAME = "readerbox-config.yaml"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, CONFIG_NAME)
SUPPORTED_TEXT = (".md", ".markdown", ".txt", ".text")
AUDIO_FORMATS = ("wav", "mp3", "opus")

DEFAULTS = {
	"server": "",
	"port": 0,
	"audio_format": "wav",
	"sample_rate": 44100,
	"turbo": False,
	"voice": "",
	"voice_mode": "predefined",
	"chunk_size": 150,
	"temperature": 0.8,
	"exaggeration": 0.5,
	"cfg_weight": 0.5,
	"seed": 0,
}

DEFAULT_TEXT = """# Readerbox configuration
# Edit server and port, then run `catro-scripts readerbox` again.
# server and port are required; every other key has a working default.
server: ""
port: ""
audio_format: wav
sample_rate: 44100
# turbo: false uses the original Chatterbox model, true uses Chatterbox Turbo.
# readerbox asks the server to hot-swap to that model at startup when needed.
turbo: false
# voice is a filename returned by the server; blank uses the server default.
voice: ""
voice_mode: predefined
chunk_size: 150
temperature: 0.8
exaggeration: 0.5
cfg_weight: 0.5
# seed: 0 means a random seed for every render.
seed: 0
"""

SETTING_STEPS = {
	"chunk_size": 10,
	"temperature": 0.05,
	"exaggeration": 0.05,
	"cfg_weight": 0.05,
	"seed": 1,
}

SETTING_LABELS = (
	("voices", "Voices"),
	("chunk_size", "Chunk size"),
	("temperature", "Temperature"),
	("exaggeration", "Exaggeration"),
	("cfg_weight", "CFG"),
	("seed", "Seed"),
)

ACTION_LABELS = (
	("preview", "[preview]"),
	("render", "[render]"),
	("save", "[save config]"),
)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ReaderboxError(Exception):
	"""A user-facing failure: configuration, API or rendering."""


class ConfigError(ReaderboxError):
	"""The configuration file is missing values or has invalid ones."""


class ApiError(ReaderboxError):
	"""The Chatterbox server could not be reached or refused a request."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _unquote(value):
	value = value.strip()
	if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
		return value[1:-1]
	return value


def _scalar(value):
	value = _unquote(value)
	if value in ("true", "True", "yes", "on"):
		return True
	if value in ("false", "False", "no", "off"):
		return False
	if value in ("", "null", "~"):
		return ""
	try:
		return int(value)
	except ValueError:
		pass
	try:
		return float(value)
	except ValueError:
		return value


def parse_config(text):
	"""Parse the flat YAML subset this script writes; unknown keys are errors."""
	values = dict(DEFAULTS)
	for number, raw in enumerate(str(text).splitlines(), 1):
		line = raw.strip()
		if not line or line.startswith("#"):
			continue
		if "#" in line:
			line = line.split("#", 1)[0].rstrip()
		if not line:
			continue
		if ":" not in line:
			raise ConfigError("line {}: expected 'key: value'".format(number))
		key, value = line.split(":", 1)
		key = key.strip()
		if not key:
			raise ConfigError("line {}: empty option name".format(number))
		if key not in DEFAULTS:
			raise ConfigError("line {}: unknown option '{}'".format(number, key))
		values[key] = _scalar(value)
	return validate_config(values)


def validate_config(values):
	"""Return a normalised copy, or raise ConfigError naming the first fault."""
	config = dict(DEFAULTS)
	config.update(values)
	server = str(config.get("server") or "").strip()
	if not server:
		raise ConfigError("server is blank - set the Chatterbox server host")
	config["server"] = server

	raw_port = config.get("port")
	if raw_port is None or str(raw_port).strip() == "":
		raise ConfigError("port is blank - set the Chatterbox server port")
	try:
		port = int(raw_port)
	except (TypeError, ValueError):
		raise ConfigError("port must be an integer")
	if not 1 <= port <= 65535:
		raise ConfigError("port must be between 1 and 65535")
	config["port"] = port

	fmt = str(config.get("audio_format") or "wav").lower()
	if fmt not in AUDIO_FORMATS:
		raise ConfigError("audio_format must be one of {}".format(
			", ".join(AUDIO_FORMATS)))
	config["audio_format"] = fmt

	try:
		rate = int(config.get("sample_rate"))
	except (TypeError, ValueError):
		raise ConfigError("sample_rate must be an integer")
	if not 8000 <= rate <= 192000:
		raise ConfigError("sample_rate must be between 8000 and 192000")
	config["sample_rate"] = rate

	config["turbo"] = bool(config.get("turbo"))
	config["voice"] = str(config.get("voice") or "").strip()
	mode = str(config.get("voice_mode") or "predefined").lower()
	if mode not in ("predefined", "clone"):
		raise ConfigError("voice_mode must be 'predefined' or 'clone'")
	config["voice_mode"] = mode

	ranges = (("chunk_size", 50, 500), ("temperature", 0.0, 1.5),
			  ("exaggeration", 0.25, 2.0), ("cfg_weight", 0.2, 1.0))
	for key, low, high in ranges:
		try:
			number = float(config.get(key))
		except (TypeError, ValueError):
			raise ConfigError("{} must be a number".format(key))
		if not low <= number <= high:
			raise ConfigError("{} must be between {} and {}".format(
				key, low, high))
		config[key] = int(number) if key == "chunk_size" else round(number, 3)

	try:
		seed = int(config.get("seed"))
	except (TypeError, ValueError):
		raise ConfigError("seed must be an integer")
	if seed < 0:
		raise ConfigError("seed must be 0 or greater")
	config["seed"] = seed
	return config


def default_config_text():
	"""The template written when the config file is missing."""
	return DEFAULT_TEXT


def read_config(path):
	"""Load and validate `path`; FileNotFoundError lets the caller create it."""
	with open(path, "r", encoding="utf-8") as handle:
		text = handle.read()
	return parse_config(text)


def write_config(path, values):
	"""Write the flat YAML document atomically; never leaves a partial file."""
	config = validate_config(values)
	lines = [
		"# Readerbox configuration",
		"# server and port are required; the rest can also be edited in the TUI.",
	]
	for key in DEFAULTS:
		value = config[key]
		if isinstance(value, bool):
			text = "true" if value else "false"
		elif isinstance(value, str):
			text = json.dumps(value)
		else:
			text = str(value)
		lines.append("{}: {}".format(key, text))
	directory = os.path.dirname(os.path.abspath(path)) or "."
	temporary = os.path.join(directory, "." + os.path.basename(path) + ".tmp")
	with open(temporary, "w", encoding="utf-8", newline="\n") as handle:
		handle.write("\n".join(lines) + "\n")
	os.replace(temporary, path)
	return path


# ---------------------------------------------------------------------------
# Chatterbox API
# ---------------------------------------------------------------------------


def base_url(config):
	"""`http://host:port` from the server and port options."""
	server = str(config["server"]).strip()
	if "://" not in server:
		server = "http://" + server
	parts = urlsplit(server)
	netloc = parts.netloc or parts.path
	if ":" not in netloc.rsplit("]", 1)[-1]:
		netloc = "{}:{}".format(netloc, int(config["port"]))
	return urlunsplit((parts.scheme or "http", netloc, "", "", ""))


class ChatterboxClient:
	"""Small JSON/audio client for the devnen Chatterbox TTS Server."""

	def __init__(self, config, timeout=10.0):
		self.config = config
		self.base = base_url(config)
		self.timeout = float(timeout)

	def _request(self, method, path, payload=None, timeout=None):
		url = self.base + path
		data = None
		headers = {"Accept": "application/json, audio/*"}
		if payload is not None:
			data = json.dumps(payload).encode("utf-8")
			headers["Content-Type"] = "application/json"
		request = urlrequest.Request(url, data=data, headers=headers,
									 method=method)
		try:
			with urlrequest.urlopen(request, timeout=timeout or self.timeout) as response:
				body = response.read()
				content_type = response.headers.get("Content-Type", "")
		except urlerror.HTTPError as exc:
			detail = ""
			try:
				detail = exc.read().decode("utf-8", "replace")
				detail = json.loads(detail).get("detail", detail)
			except (ValueError, AttributeError):
				pass
			raise ApiError("{} {}: {}".format(
				method, path, detail or "HTTP {}".format(exc.code)))
		except (urlerror.URLError, OSError, ValueError) as exc:
			reason = getattr(exc, "reason", exc)
			raise ApiError("cannot reach {}: {}".format(self.base, reason))
		return body, content_type

	def _json(self, path, timeout=None):
		body, _ = self._request("GET", path, timeout=timeout)
		try:
			return json.loads(body.decode("utf-8"))
		except (UnicodeDecodeError, ValueError):
			raise ApiError("{} returned invalid JSON".format(path))

	def model_info(self, timeout=None):
		"""Loaded engine details, or ApiError when the server is unreachable."""
		return self._json("/api/model-info", timeout=timeout)

	def voices(self):
		"""Every predefined and reference voice, as dicts with id/label/mode."""
		found = []
		try:
			for row in self._json("/get_predefined_voices") or []:
				if isinstance(row, str):
					filename, label = row, row
				else:
					filename = row.get("filename") or row.get("id") or ""
					label = row.get("display_name") or filename
				if filename:
					found.append({"id": filename, "label": label,
								  "mode": "predefined"})
		except ApiError:
			pass
		try:
			for filename in self._json("/get_reference_files") or []:
				if filename:
					found.append({"id": filename,
								  "label": "Clone: " + str(filename),
								  "mode": "clone"})
		except ApiError:
			pass
		if not found:
			try:
				rows = self._json("/v1/audio/voices").get("voices", [])
				found = [{"id": row, "label": row, "mode": "predefined"}
						 for row in rows if row]
			except (ApiError, AttributeError):
				pass
		return found

	def save_settings(self, payload):
		"""Merge a partial config into the server's own config.yaml."""
		return self._json_object("POST", "/save_settings", payload)

	def restart_server(self):
		"""Hot-swap the server's loaded model to the configured one."""
		return self._json_object("POST", "/restart_server", {}, timeout=300)

	def _json_object(self, method, path, payload, timeout=None):
		body, _ = self._request(method, path, payload=payload, timeout=timeout)
		try:
			return json.loads(body.decode("utf-8"))
		except (UnicodeDecodeError, ValueError):
			return {}

	def ensure_model(self, turbo, timeout=180):
		"""Make the server run the model the config asks for; returns info.

		A server that is still loading, or that refuses the hot-swap, is left
		alone: the caller reports the mismatch but keeps working.
		"""
		info = self.model_info()
		wanted = "turbo" if turbo else "original"
		if not info.get("loaded") or info.get("type") == wanted:
			return info
		selector = "chatterbox-turbo" if turbo else "chatterbox"
		self.save_settings({"model": {"repo_id": selector}})
		note = self.restart_server()
		deadline = time.monotonic() + timeout
		while time.monotonic() < deadline:
			time.sleep(1.0)
			try:
				info = self.model_info(timeout=5)
			except ApiError:
				continue
			if info.get("loaded") and info.get("type") == wanted:
				return info
		raise ApiError("model hot-swap did not finish ({})".format(
			note.get("message", "no response")))

	def synthesize(self, text, settings, seed=None):
		"""Render one chunk and return the WAV bytes."""
		voice = str(settings.get("voice") or "")
		mode = settings.get("voice_mode", "predefined")
		payload = {
			"text": text,
			"voice_mode": mode,
			"output_format": "wav",
			"split_text": False,
			"chunk_size": int(settings["chunk_size"]),
			"temperature": float(settings["temperature"]),
			"seed": int(seed if seed is not None else settings["seed"]),
			"speed_factor": 1.0,
			"language": "en",
		}
		if voice:
			key = ("predefined_voice_id" if mode == "predefined"
				   else "reference_audio_filename")
			payload[key] = voice
		if not settings.get("turbo"):
			payload["exaggeration"] = float(settings["exaggeration"])
			payload["cfg_weight"] = float(settings["cfg_weight"])
		body, content_type = self._request("POST", "/tts", payload,
										   timeout=max(120, self.timeout))
		if "json" in content_type.lower():
			raise ApiError("server returned an error instead of audio: {}".format(
				body.decode("utf-8", "replace")[:300]))
		if len(body) < 44 or body[:4] != b"RIFF":
			raise ApiError("server returned no WAV audio")
		return body


# ---------------------------------------------------------------------------
# Markdown preprocessing and chunking
# ---------------------------------------------------------------------------

PARAGRAPH_PAUSE_MS = 350
SENTENCE_PAUSE_MS = 140
HEADING_PAUSE_MS = 500
RULE_PAUSE_MS = 600
TERMINAL_PUNCT = ".?!,:;â€¦â€”-"
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_RULE = re.compile(r"^\s{0,3}([-*_])(?:\s*\1){2,}\s*$")
_SENTENCE = re.compile(r"[^.!?â€¦]+(?:[.!?â€¦]+|$)")


class Unit:
	"""One block of speech plus the silence that follows it."""

	def __init__(self, text, kind="text", pause_ms=PARAGRAPH_PAUSE_MS):
		self.text = str(text)
		self.kind = kind
		self.pause_ms = int(pause_ms)

	def __eq__(self, other):
		return (isinstance(other, Unit) and self.text == other.text
				and self.kind == other.kind and self.pause_ms == other.pause_ms)


class Chunk:
	"""One TTS request; an empty text is silence only."""

	def __init__(self, text, pause_ms=PARAGRAPH_PAUSE_MS):
		self.text = str(text)
		self.pause_ms = int(pause_ms)

	def __eq__(self, other):
		return (isinstance(other, Chunk) and self.text == other.text
				and self.pause_ms == other.pause_ms)


def _interjections(text):
	"""Dashes around italics, parentheses and quoted asides."""
	text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
	text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r" - \1 - ", text)
	text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r" - \1 - ", text)
	text = re.sub(r"\(([^()\n]+)\)", r" - \1 - ", text)
	text = re.sub(r'"([^"\n]+)"', r" - \1 - ", text)
	text = re.sub(r"â€œ([^â€\n]+)â€", r" - \1 - ", text)
	text = re.sub(r"â€˜([^â€™\n]+)â€™", r" - \1 - ", text)
	text = re.sub(r"\s+([.,!?;:])", r"\1", text)
	return re.sub(r"\s+", " ", text).strip()


def _paragraph_text(lines):
	"""Inline conversion plus a comma or full stop on every line ending."""
	converted = []
	for line in lines:
		line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
		line = _interjections(line)
		if line:
			converted.append(line)
	for index, line in enumerate(converted):
		if line[-1] not in TERMINAL_PUNCT:
			converted[index] = line + ("," if index < len(converted) - 1 else ".")
		elif line[-1] == "-" and index < len(converted) - 1:
			converted[index] = line + ","
	return " ".join(converted)


def markdown_units(text):
	"""Blocks for speech: paragraphs, headings and horizontal rules."""
	lines = str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n")
	units, paragraph = [], []
	in_fence = False

	def flush():
		if not paragraph:
			return
		units.append(Unit(_paragraph_text(paragraph), "text"))
		del paragraph[:]

	for line in lines:
		if line.strip().startswith("```"):
			flush()
			in_fence = not in_fence
			continue
		if in_fence:
			paragraph.append(line)
			continue
		heading = _HEADING.match(line)
		if heading:
			flush()
			content = _interjections(heading.group(2))
			if content:
				units.append(Unit(content, "heading",
								  HEADING_PAUSE_MS + 50 * len(heading.group(1))))
			continue
		if _RULE.match(line):
			flush()
			units.append(Unit("", "rule", RULE_PAUSE_MS))
			continue
		if not line.strip():
			flush()
			continue
		paragraph.append(line)
	flush()
	return units


def plain_units(text):
	"""Paragraph blocks for a plain text document, without punctuation edits."""
	units, paragraph = [], []
	for line in str(text).replace("\r\n", "\n").replace("\r", "\n").split("\n"):
		if not line.strip():
			if paragraph:
				units.append(Unit(" ".join(paragraph), "text"))
				del paragraph[:]
			continue
		paragraph.append(line.strip())
	if paragraph:
		units.append(Unit(" ".join(paragraph), "text"))
	return units


def sentences(text):
	"""Sentence-ish splits, keeping terminal punctuation and closing quotes."""
	return [match.group(0).strip() for match in _SENTENCE.finditer(str(text))
			if match.group(0).strip()]


def _split_words(text, size):
	"""Hard split a too-long sentence into word-boundary pieces."""
	pieces, current = [], ""
	for word in text.split():
		candidate = word if not current else current + " " + word
		if len(candidate) <= size:
			current = candidate
			continue
		if current:
			pieces.append(current)
		current = word
	while len(current) > size:
		pieces.append(current[:size])
		current = current[size:]
	if current:
		pieces.append(current)
	return pieces or [text]


def _split_block(text, size):
	"""Sentences accumulated to at most `size` characters."""
	if len(text) <= size:
		return [text]
	pieces, current = [], ""
	for sentence in sentences(text):
		if len(sentence) > size:
			if current:
				pieces.append(current)
				current = ""
			pieces.extend(_split_words(sentence, size))
			continue
		candidate = sentence if not current else current + " " + sentence
		if len(candidate) <= size:
			current = candidate
			continue
		pieces.append(current)
		current = sentence
	if current:
		pieces.append(current)
	return pieces


def build_chunks(units, size=150):
	"""Every paragraph/heading starts a chunk; long blocks split by sentence."""
	size = max(50, int(size))
	chunks = []
	for unit in units:
		if unit.kind == "rule" or not unit.text.strip():
			chunks.append(Chunk("", unit.pause_ms))
			continue
		pieces = _split_block(unit.text, size)
		for index, piece in enumerate(pieces):
			pause = (unit.pause_ms if index == len(pieces) - 1
					 else min(SENTENCE_PAUSE_MS, unit.pause_ms))
			chunks.append(Chunk(piece, pause))
	return chunks


def preprocess_markdown(text):
	"""The flat display text for a Markdown document."""
	return "\n\n".join(unit.text for unit in markdown_units(text) if unit.text)


def document_units(path, text):
	"""Markdown gets the speech rewrite; plain text only keeps paragraphs."""
	if os.path.splitext(path)[1].lower() in (".md", ".markdown"):
		return markdown_units(text)
	return plain_units(text)


def preview_sentences(chunks, count=2):
	"""The first `count` spoken sentences across the chunks."""
	found = []
	for chunk in chunks:
		for sentence in sentences(chunk.text):
			if sentence[-1] not in ".?!â€¦":
				sentence += "."
			found.append(sentence)
			if len(found) >= count:
				return " ".join(found)
	return " ".join(found)


# ---------------------------------------------------------------------------
# WAV merging and output conversion
# ---------------------------------------------------------------------------


def _ffmpeg():
	"""ffmpeg from PATH, or the copy shipped beside the scripts."""
	directory = os.path.dirname(os.path.abspath(__file__))
	for name in ("ffmpeg.exe", "ffmpeg"):
		candidate = os.path.join(directory, name)
		if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
			return candidate
	return "ffmpeg"


def _read_wav(blob):
	with wave.open(io.BytesIO(blob), "rb") as handle:
		params = handle.getparams()
		return params, handle.readframes(params.nframes)


def merge_wavs(blobs, pauses_ms, destination, audio_format="wav",
			   sample_rate=44100):
	"""Concatenate WAV blobs with silence; convert the result when needed."""
	if not blobs:
		raise ReaderboxError("nothing was rendered")
	params, first = _read_wav(blobs[0])
	frames = [first]
	block = params.nchannels * params.sampwidth
	for index, blob in enumerate(blobs[1:], start=1):
		params_here, data = _read_wav(blob)
		if (params_here.nchannels, params_here.sampwidth,
				params_here.framerate) != (params.nchannels, params.sampwidth,
											params.framerate):
			raise ReaderboxError("server returned inconsistent WAV formats")
		pause = pauses_ms[index - 1] if index - 1 < len(pauses_ms) else 0
		if pause > 0:
			frames.append(b"\x00" * (int(params.framerate * pause / 1000.0)
									 * block))
		frames.append(data)
	native = destination + ".native.wav"
	with wave.open(native, "wb") as handle:
		handle.setnchannels(params.nchannels)
		handle.setsampwidth(params.sampwidth)
		handle.setframerate(params.framerate)
		handle.writeframes(b"".join(frames))

	fmt = str(audio_format).lower()
	target = max(0, int(sample_rate))
	if fmt == "wav" and (target == 0 or target == params.framerate):
		os.replace(native, destination)
		return destination
	if fmt == "wav" and target:
		args = ["-ar", str(target)]
	else:
		args = ["-ar", str(target or params.framerate)]
		codecs = {"mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
				  "opus": ["-c:a", "libopus", "-b:a", "128k"]}
		args.extend(codecs.get(fmt, []))
	try:
		subprocess.run([_ffmpeg(), "-y", "-loglevel", "error", "-i", native]
					   + args + [destination], check=True,
					   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
	except (OSError, subprocess.CalledProcessError) as exc:
		if fmt == "wav":
			os.replace(native, destination)
		else:
			os.unlink(native)
			raise ReaderboxError(
				"ffmpeg is needed to write {} audio".format(fmt))
	finally:
		if os.path.exists(native):
			try:
				os.unlink(native)
			except OSError:
				pass
	return destination


def unique_output(path):
	"""`path`, or `path (2)`/`(3)` when it exists."""
	if not os.path.exists(path):
		return path
	stem, extension = os.path.splitext(path)
	number = 2
	while os.path.exists("{} ({}){}".format(stem, number, extension)):
		number += 1
	return "{} ({}){}".format(stem, number, extension)


def _open_audio(path):
	"""Best-effort playback through the desktop's default audio handler."""
	try:
		if os.name == "nt":
			os.startfile(path)  # noqa: S606 - user-requested playback
		elif sys.platform == "darwin":
			subprocess.Popen(["open", path])
		else:
			subprocess.Popen(["xdg-open", path])
		return True
	except (OSError, AttributeError):
		return False


# ---------------------------------------------------------------------------
# Full-screen UI
# ---------------------------------------------------------------------------


class ReaderBox:
	"""One full-screen session; all state can be driven with injected keys."""

	def __init__(self, client, config, config_path, *, root=None, canvas=None,
				 keys=None, cap=None, voices=None):
		self.client = client
		self.config = dict(config)
		self.config_path = config_path
		self.root = os.path.abspath(root or os.getcwd())
		self.canvas = canvas
		self.key_queue = keys
		self.cap = cap or tui.detect()
		self.screen = None
		self.stream = None
		self.closed = False

		self.mode = "browse"
		self.focus = "left"
		self.cwd = self.root
		self.entries = []
		self.explorer_index = 0
		self.explorer_offset = 0

		self.selected_path = None
		self.raw_text = ""
		self.units = []
		self.chunks = []
		self.preview_lines = []
		self.right_scroll = 0
		self.menu_index = 0
		self.menu_offset = 0

		self.voices = list(voices or [])
		self.settings = {
			"voice": config.get("voice", ""),
			"voice_mode": config.get("voice_mode", "predefined"),
			"chunk_size": int(config.get("chunk_size", 150)),
			"temperature": float(config.get("temperature", 0.8)),
			"exaggeration": float(config.get("exaggeration", 0.5)),
			"cfg_weight": float(config.get("cfg_weight", 0.5)),
			"seed": int(config.get("seed", 0)),
			"turbo": bool(config.get("turbo", False)),
		}
		self.popup = None
		self.progress = None
		self.message = ("info", "Ready")
		self._status = "checking..."
		self._refresh_status()
		self._reload()

	# -- state -----------------------------------------------------------

	def _refresh_status(self):
		if self.client is None:
			self._status = "offline"
			return
		try:
			info = self.client.model_info(timeout=3)
		except ApiError:
			self._status = "offline"
			return
		if not info.get("loaded"):
			self._status = "online (model loading)"
			return
		self._status = "online - {} - {} Hz".format(
			info.get("type") or "unknown", info.get("sample_rate") or "?")

	def _online(self):
		self._status = "online"

	def _offline(self, reason=""):
		self._status = "offline" + (" - " + reason if reason else "")

	def _reload(self):
		"""Read one directory, clamped to the session root."""
		try:
			names = sorted(os.scandir(self.cwd), key=lambda entry: (
				not entry.is_dir(follow_symlinks=False),
				entry.name.casefold()))
		except OSError as exc:
			self.message = ("error", "cannot read {}: {}".format(self.cwd, exc))
			names = []
		entries = []
		if os.path.normcase(self.cwd) != os.path.normcase(self.root):
			entries.append(("..", "up", os.path.dirname(self.cwd)))
		for entry in names:
			try:
				is_dir = entry.is_dir(follow_symlinks=False)
			except OSError:
				continue
			if entry.name.startswith("."):
				continue
			if is_dir:
				entries.append((entry.name + "/", "dir", entry.path))
			elif os.path.splitext(entry.name)[1].lower() in SUPPORTED_TEXT:
				entries.append((entry.name, "file", entry.path))
		self.entries = entries
		self.explorer_index = min(self.explorer_index, max(0, len(entries) - 1))
		self.explorer_offset = 0

	def _rebuild_chunks(self):
		self.chunks = build_chunks(self.units, self.settings["chunk_size"])
		self._wrap_preview()

	def _wrap_preview(self):
		width = self._right_width() - 2
		text = (preprocess_markdown(self.raw_text)
				if os.path.splitext(self.selected_path or "")[1].lower()
				in (".md", ".markdown") else self.raw_text)
		self.preview_lines = tui.wrap(text, max(10, width))
		self.right_scroll = min(self.right_scroll, max(
			0, len(self.preview_lines) - self._right_height()))

	def open_file(self, path):
		"""Load one text file and switch to the settings/preview layout."""
		try:
			with open(path, "r", encoding="utf-8", errors="replace") as handle:
				text = handle.read()
		except OSError as exc:
			self.message = ("error", "cannot open {}: {}".format(
				os.path.basename(path), exc))
			return False
		self.selected_path = path
		self.raw_text = text
		self.units = document_units(path, text)
		self._rebuild_chunks()
		self.mode = "read"
		self.focus = "left"
		self.menu_index = 0
		self.menu_offset = 0
		self.right_scroll = 0
		self.message = ("info", "{} - {} chunk(s)".format(
			os.path.basename(path), len([c for c in self.chunks if c.text])))
		return True

	# -- geometry --------------------------------------------------------

	def _left_width(self):
		if self.canvas is None:
			return 44
		width = self.canvas.width
		share = 2 if self.mode == "browse" else 3
		return max(28, min(52, width // share))

	def _right_width(self):
		width = self.canvas.width if self.canvas else 80
		return max(10, width - self._left_width())

	def _pane_height(self):
		height = self.canvas.height if self.canvas else 24
		return max(4, height - 3)

	def _right_height(self):
		return max(1, self._pane_height() - 2)

	# -- drawing ---------------------------------------------------------

	def _p(self, fg=None, bg=None, bold=False, dim=False, reverse=False):
		return tui.palette.prefix(fg=fg, bg=bg, bold=bold, dim=dim,
								  reverse=reverse, cap=self.cap) or None

	def _fill(self, x, y, width, height, color):
		for row in range(height):
			self.canvas.draw_text(x, y + row, " " * width, color)

	def _panel(self, x, y, width, height, title, focused):
		color = self._p(fg="border-fg", bg="border-bg")
		self._fill(x, y, width, height, self._p(fg="fg", bg="bg"))
		self.canvas.box(x, y, width, height)
		frame = self._p(fg="fg-accent" if focused else "border-fg",
						bg="border-bg", bold=focused)
		for offset in range(width):
			self.canvas.draw_char(x + offset, y, "\u2500", frame)
			self.canvas.draw_char(x + offset, y + height - 1, "\u2500", frame)
		for row in range(1, height - 1):
			self.canvas.draw_char(x, y + row, "\u2502", frame)
			self.canvas.draw_char(x + width - 1, y + row, "\u2502", frame)
		for cx, cy, glyph in ((x, y, "\u250c"), (x + width - 1, y, "\u2510"),
							  (x, y + height - 1, "\u2514"),
							  (x + width - 1, y + height - 1, "\u2518")):
			self.canvas.draw_char(cx, cy, glyph, frame)
		label = " {} ".format(title)
		self.canvas.draw_text(x + 2, y, tui.truncate(label, max(1, width - 4)),
							  self._p(fg="header-fg", bg="border-bg", bold=True))
		return color

	def _selected_color(self, focused):
		if focused:
			return self._p(fg="fg", bg="button-bg-active", bold=True)
		return self._p(fg="fg", bg="bg-stripe")

	def draw(self, full=True):
		"""Paint one frame on the injected canvas."""
		if self.canvas is None:
			return self
		tui.palette.begin_frame()
		try:
			self.canvas.clear()
			self._fill(0, 0, self.canvas.width, self.canvas.height,
					   self._p(fg="fg", bg="bg"))
			self._draw_status()
			left_w = self._left_width()
			height = self._pane_height()
			if self.mode == "browse":
				self._draw_explorer(0, 1, left_w, height)
				self._draw_help(left_w, 1, self.canvas.width - left_w, height)
			else:
				self._draw_menu(0, 1, left_w, height)
				self._draw_preview(left_w, 1, self.canvas.width - left_w, height)
			self._draw_hints()
			if self.progress:
				self._draw_progress()
			elif self.popup:
				self._draw_popup()
		finally:
			tui.palette.end_frame()
		return self

	def _draw_status(self):
		width = self.canvas.width
		cwd = tui.truncate(self.cwd, max(10, width - 34))
		left = " readerbox  {} ".format(cwd)
		right = " chatterbox: {} ".format(self._status)
		line = tui.pad(tui.truncate(left, width), width)
		line = line[:max(0, width - len(right))] + right[-width:]
		self.canvas.draw_text(0, 0, tui.truncate(line, width),
							  self._p(fg="border-fg", bg="border-bg", bold=True))

	def _draw_hints(self):
		width = self.canvas.width
		if self.mode == "browse":
			hint = " Up/Down move   Enter open   Tab pane   Esc quit "
		else:
			hint = " Up/Down select   Enter choose   Tab pane   Esc back "
		hint += " | " + self.message[1]
		self.canvas.draw_text(0, self.canvas.height - 1,
							  tui.pad(tui.truncate(hint, width), width),
							  self._p(fg="fg", bg="bg-stripe",
									  dim=self.message[0] == "info"))

	def _draw_explorer(self, x, y, width, height):
		focused = self.focus == "left"
		title = os.path.basename(self.cwd) or self.cwd
		self._panel(x, y, width, height, title, focused)
		rows = max(1, height - 2)
		if not self.entries:
			self.canvas.draw_text(x + 2, y + 1, "(empty folder)",
								  self._p(fg="fg-muted", bg="bg"))
			return
		if self.explorer_index < self.explorer_offset:
			self.explorer_offset = self.explorer_index
		elif self.explorer_index >= self.explorer_offset + rows:
			self.explorer_offset = self.explorer_index - rows + 1
		for row, index in enumerate(range(self.explorer_offset,
										  min(len(self.entries),
											  self.explorer_offset + rows))):
			label, kind, _ = self.entries[index]
			marker = "  " if kind == "file" else "+ "
			text = tui.truncate(marker + label, width - 3)
			color = (self._selected_color(focused)
					 if index == self.explorer_index
					 else self._p(fg="fg", bg="bg"))
			self.canvas.draw_text(x + 1, y + 1 + row,
								  tui.pad(text, width - 2), color)

	def _draw_help(self, x, y, width, height):
		self._panel(x, y, width, height, "readerbox", self.focus == "right")
		lines = [
			"Select a Markdown or text file on the left.",
			"",
			"Markdown is rewritten for speech:",
			"  *italics*, (asides) and \"quotes\" become",
			"  spaced dashes; lines get commas, paragraphs",
			"  get full stops, and headings get a short",
			"  silence before the next chunk.",
			"",
			"The rendered audio is saved beside the source.",
		]
		for row, text in enumerate(lines[:max(0, height - 2)]):
			self.canvas.draw_text(x + 2, y + 1 + row, tui.truncate(text, width - 4),
								  self._p(fg="fg-muted", bg="bg"))

	def _menu_rows(self):
		"""Selectable descriptors in display order, with separator rows."""
		rows, selectable = [], []
		rows.append(("sep", "SETTINGS", None))
		for key, label in SETTING_LABELS:
			value = self._setting_text(key)
			selectable.append(("setting", key, label))
			rows.append(("setting", label, value))
		rows.append(("sep", "ACTIONS", None))
		for key, label in ACTION_LABELS:
			selectable.append(("action", key, label))
			rows.append(("action", label, ""))
		return rows, selectable

	def _setting_text(self, key):
		if key == "voices":
			voice = self.settings["voice"]
			if not voice:
				return "(default)"
			for item in self.voices:
				if item["id"] == voice and item["mode"] == self.settings["voice_mode"]:
					return str(item["label"])
			return str(voice)
		value = self.settings[key]
		if key in ("temperature", "exaggeration", "cfg_weight"):
			return "{:.2f}".format(float(value))
		return str(value)

	def _draw_menu(self, x, y, width, height):
		focused = self.focus == "left"
		self._panel(x, y, width, height, "Settings & Actions", focused)
		rows, _selectable = self._menu_rows()
		visible = max(1, height - 2)
		ordinal, entries, selected_row = -1, [], 0
		for kind, label, value in rows:
			if kind != "sep":
				ordinal += 1
				if ordinal == self.menu_index:
					selected_row = len(entries)
			entries.append((kind, label, value, ordinal))
		if selected_row < self.menu_offset:
			self.menu_offset = selected_row
		elif selected_row >= self.menu_offset + visible:
			self.menu_offset = selected_row - visible + 1
		self.menu_offset = max(0, min(self.menu_offset,
									 max(0, len(entries) - visible)))
		for row, (kind, label, value, ordinal) in enumerate(
				entries[self.menu_offset:self.menu_offset + visible]):
			line_y = y + 1 + row
			if kind == "sep":
				self.canvas.draw_text(x + 2, line_y, tui.truncate(label, width - 4),
									  self._p(fg="header-fg", bg="bg", bold=True))
				continue
			prefix = "> " if ordinal == self.menu_index else "  "
			text = "{}{}".format(prefix, label)
			if value:
				room = max(1, width - 4 - len(label) - 3)
				text = tui.pad(tui.truncate(text, width - 4 - room), width - 4 - room)
				text += tui.truncate(" " + value, room)
			else:
				text = tui.truncate(text, width - 4)
			color = (self._selected_color(focused)
					 if ordinal == self.menu_index
					 else self._p(fg="fg", bg="bg"))
			self.canvas.draw_text(x + 2, line_y, tui.pad(text, width - 4), color)

	def _draw_preview(self, x, y, width, height):
		focused = self.focus == "right"
		title = (os.path.basename(self.selected_path)
				 if self.selected_path else "Text preview")
		self._panel(x, y, width, height, title, focused)
		rows = max(1, height - 2)
		self.right_scroll = max(0, min(self.right_scroll,
									   max(0, len(self.preview_lines) - rows)))
		for row, line in enumerate(self.preview_lines[self.right_scroll:
													  self.right_scroll + rows]):
			self.canvas.draw_text(x + 2, y + 1 + row,
								  tui.truncate(line, width - 4),
								  self._p(fg="fg", bg="bg"))
		if not self.preview_lines:
			self.canvas.draw_text(x + 2, y + 1, "(empty)", self._p(
				fg="fg-muted", bg="bg"))

	def _popup_rect(self, width, height):
		width = min(self.canvas.width - 4, width)
		height = min(self.canvas.height - 2, height)
		return ((self.canvas.width - width) // 2,
				max(1, (self.canvas.height - height) // 2), width, height)

	def _draw_popup(self):
		popup = self.popup
		rows = popup.get("options") or []
		if popup["kind"] == "number":
			rows = ["< {} >".format(popup["draft"])]
		height = len(rows) + 4
		x, y, width, height = self._popup_rect(
			max(36, min(self.canvas.width - 8, popup.get("width", 46))), height)
		self._fill(x, y, width, height, self._p(fg="fg", bg="bg-inside"))
		self._panel(x, y, width, height, popup["title"], True)
		if not rows:
			self.canvas.draw_text(x + 2, y + 2, tui.truncate(
				popup.get("empty", "(nothing to choose)"), width - 4),
				self._p(fg="fg-muted", bg="bg-inside"))
		visible_count = max(1, height - 3)
		offset = popup.get("offset", 0)
		if popup["index"] < offset:
			offset = popup["index"]
		elif popup["index"] >= offset + visible_count:
			offset = popup["index"] - visible_count + 1
		popup["offset"] = offset
		visible = rows[offset:offset + visible_count]
		for row, text in enumerate(visible):
			index = offset + row
			color = (self._selected_color(True) if index == popup["index"]
					 else self._p(fg="fg", bg="bg-inside"))
			self.canvas.draw_text(x + 2, y + 2 + row,
								  tui.pad(tui.truncate(str(text), width - 4),
										  width - 4), color)
		self.canvas.draw_text(x + 2, y + height - 2,
							  tui.truncate(popup.get("hint",
													 "Up/Down choose  Enter apply  Esc cancel"),
										   width - 4),
							  self._p(fg="fg-muted", bg="bg-inside"))

	def _draw_progress(self):
		progress = self.progress
		total = max(1, int(progress["total"]))
		done = max(0, min(int(progress["done"]), total))
		width = min(self.canvas.width - 4, 54)
		x, y, width, height = self._popup_rect(width, 7)
		self._fill(x, y, width, height, self._p(fg="fg", bg="bg-inside"))
		self._panel(x, y, width, height, progress.get("title", "Rendering"),
					True)
		text = tui.progress.bar(done, total, max(10, width - 16), cap=self.cap)
		self.canvas.draw_text(x + 2, y + 2, "{} {}/{}".format(text, done, total),
							  self._p(fg="fg", bg="bg-inside"))
		self.canvas.draw_text(x + 2, y + 3, tui.truncate(
			progress.get("note", ""), width - 4),
			self._p(fg="fg-muted", bg="bg-inside"))
		self.canvas.draw_text(x + 2, y + 4, tui.truncate(
			"Please wait...", width - 4),
			self._p(fg="fg-muted", bg="bg-inside"))

	def _paint_now(self):
		"""Repaint from a blocking action (render progress)."""
		if self.canvas is None or self.stream is None:
			return
		self.draw(full=True)
		self.canvas.render(full=False)

	# -- keys ------------------------------------------------------------

	def handle(self, token):
		"""One key token; returns `self` for easy chaining."""
		if token in (None, ""):
			return self
		if self.progress:
			return self
		if self.popup:
			self._popup_key(token)
			return self
		if token == "ctrl-c":
			self.closed = True
			return self
		if token == "esc":
			if self.mode == "read":
				self.mode = "browse"
				self.focus = "left"
				self.message = ("info", "back to explorer")
			else:
				self.closed = True
			return self
		if token == "tab":
			self.focus = "right" if self.focus == "left" else "left"
			return self
		if self.mode == "browse":
			self._browse_key(token)
		else:
			self._read_key(token)
		return self

	def _browse_key(self, token):
		steps = {"up": -1, "down": 1, "pageup": -max(1, self._pane_height() - 2),
				 "pagedown": max(1, self._pane_height() - 2),
				 "home": -len(self.entries), "end": len(self.entries)}
		if token in steps:
			self.explorer_index = max(0, min(len(self.entries) - 1,
											 self.explorer_index + steps[token]))
			return
		if token in ("enter", "right"):
			self._activate_entry()
			return

	def _activate_entry(self):
		if not self.entries:
			return
		_, kind, path = self.entries[self.explorer_index]
		if kind == "up":
			self.cwd = path
			self.explorer_index = 0
			self._reload()
		elif kind == "dir":
			self.cwd = path
			self.explorer_index = 0
			self._reload()
		else:
			self.open_file(path)

	def _read_key(self, token):
		if self.focus == "right":
			steps = {"up": -1, "down": 1,
					 "pageup": -self._right_height(),
					 "pagedown": self._right_height(),
					 "home": -len(self.preview_lines), "end": len(self.preview_lines)}
			if token in steps:
				self.right_scroll = max(0, min(
					steps[token] + self.right_scroll,
					max(0, len(self.preview_lines) - self._right_height())))
			return
		_, selectable = self._menu_rows()
		if token in ("up", "down", "home", "end"):
			step = {"up": -1, "down": 1, "home": -len(selectable),
					"end": len(selectable)}[token]
			self.menu_index = max(0, min(len(selectable) - 1,
										 self.menu_index + step))
			return
		if token in ("enter", "right"):
			kind, key, _label = selectable[self.menu_index]
			if kind == "setting":
				self._open_setting(key)
			else:
				self._run_action(key)

	# -- popups ----------------------------------------------------------

	def _open_setting(self, key):
		if key == "voices":
			options = ["(default)"]
			self._voice_options = [{"id": "", "label": "(default)",
									"mode": "predefined"}]
			for item in self.voices:
				self._voice_options.append(item)
				options.append(item["label"])
			selected = 0
			for index, item in enumerate(self._voice_options):
				if (item["id"] == self.settings["voice"]
						and item["mode"] == self.settings["voice_mode"]):
					selected = index
			self.popup = {"kind": "choice", "setting": key, "title": "Voices",
						  "options": options, "index": selected, "offset": 0,
						  "width": min(self.canvas.width - 8,
									   max(36, max(map(len, options), default=20) + 8))
						  if self.canvas else 46,
						  "empty": "no voices returned by the server"}
			return
		self.popup = {"kind": "number", "setting": key,
					  "title": dict(SETTING_LABELS)[key],
					  "draft": self.settings[key], "index": 0,
					  "hint": "Up/Down adjust  Enter apply  Esc cancel"}

	def _popup_key(self, token):
		popup = self.popup
		if token in ("esc", "ctrl-c"):
			self.popup = None
			return
		if popup["kind"] == "choice":
			options = popup["options"]
			if token == "up":
				popup["index"] = max(0, popup["index"] - 1)
			elif token == "down":
				popup["index"] = min(len(options) - 1, popup["index"] + 1)
			elif token == "pageup":
				popup["index"] = max(0, popup["index"] - 8)
			elif token == "pagedown":
				popup["index"] = min(len(options) - 1, popup["index"] + 8)
			elif token == "enter" and options:
				item = self._voice_options[popup["index"]]
				self.settings["voice"] = item["id"]
				self.settings["voice_mode"] = item["mode"]
				self.message = ("info", "voice: " + item["label"])
				self.popup = None
			return
		key = popup["setting"]
		step = SETTING_STEPS.get(key, 1)
		if token in ("up", "right"):
			popup["draft"] = self._clamp_setting(key, popup["draft"] + step)
		elif token in ("down", "left"):
			popup["draft"] = self._clamp_setting(key, popup["draft"] - step)
		elif token == "pageup":
			popup["draft"] = self._clamp_setting(key, popup["draft"] + 10 * step)
		elif token == "pagedown":
			popup["draft"] = self._clamp_setting(key, popup["draft"] - 10 * step)
		elif token == "enter":
			self.settings[key] = popup["draft"]
			if key == "chunk_size":
				self._rebuild_chunks()
			self.message = ("info", "{}: {}".format(
				dict(SETTING_LABELS)[key], self._setting_text(key)))
			self.popup = None

	def _clamp_setting(self, key, value):
		bounds = {"chunk_size": (50, 500), "temperature": (0.0, 1.5),
				  "exaggeration": (0.25, 2.0), "cfg_weight": (0.2, 1.0),
				  "seed": (0, 99999999)}
		low, high = bounds.get(key, (0, 99999999))
		value = max(low, min(high, value))
		if key in ("temperature", "exaggeration", "cfg_weight"):
			return round(value, 2)
		return int(value)

	# -- actions ---------------------------------------------------------

	def _run_action(self, key):
		if key == "save":
			self.save_config()
		elif key == "preview":
			self.render_preview()
		elif key == "render":
			self.render_document()

	def save_config(self):
		values = dict(self.config)
		values.update({
			"voice": self.settings["voice"],
			"voice_mode": self.settings["voice_mode"],
			"chunk_size": self.settings["chunk_size"],
			"temperature": self.settings["temperature"],
			"exaggeration": self.settings["exaggeration"],
			"cfg_weight": self.settings["cfg_weight"],
			"seed": self.settings["seed"],
		})
		try:
			write_config(self.config_path, values)
		except (OSError, ConfigError) as exc:
			self.message = ("error", "save config failed: {}".format(exc))
			return False
		self.config = values
		self.message = ("success", "config saved to " + self.config_path)
		return True

	def _seed_plan(self, count):
		base = self.settings["seed"]
		if not base:
			base = random.randint(1, 2 ** 31 - 2)
		return [base + index for index in range(count)]

	def _render(self, chunks, destination, title):
		"""Synthesize every non-empty chunk, merge, and write `destination`.

		Empty chunks (horizontal rules) contribute their pause to the next
		speech chunk, so a rule is heard as silence rather than dropped.
		"""
		spoken = [chunk for chunk in chunks if chunk.text.strip()]
		if not spoken:
			raise ReaderboxError("the document has no speakable text")
		seeds = self._seed_plan(len(spoken))
		blobs, pauses = [], []
		pending, seed_index = 0, 0
		self.progress = {"title": title, "done": 0, "total": len(spoken),
						 "note": "contacting {}".format(self.client.base)}
		self._paint_now()
		for chunk in chunks:
			if not chunk.text.strip():
				pending += chunk.pause_ms
				continue
			if blobs and pending:
				pauses[-1] += pending
			pending = 0
			self.progress["done"] = seed_index
			self.progress["note"] = "chunk {}/{}  {} chars".format(
				seed_index + 1, len(spoken), len(chunk.text))
			self._paint_now()
			try:
				blobs.append(self.client.synthesize(
					chunk.text, self.settings, seed=seeds[seed_index]))
				self._online()
			except ApiError as exc:
				self._offline(str(exc))
				self.progress = None
				raise
			pauses.append(chunk.pause_ms)
			seed_index += 1
		self.progress["done"] = len(spoken)
		self.progress["note"] = "merging {} chunk(s)".format(len(spoken))
		self._paint_now()
		written = merge_wavs(blobs, pauses, destination,
							 self.config["audio_format"],
							 self.config["sample_rate"])
		self.progress = None
		return written

	def render_preview(self):
		"""Render just the first two sentences beside the selected file."""
		if not self.selected_path:
			self.message = ("warn", "open a file first")
			return None
		text = preview_sentences(self.chunks, 2)
		if not text:
			self.message = ("warn", "nothing to preview")
			return None
		stem = os.path.splitext(self.selected_path)[0]
		path = unique_output(stem + ".preview." + self.config["audio_format"])
		chunks = [Chunk(text, 200)]
		try:
			written = self._render(chunks, path, "Preview")
		except (ReaderboxError, OSError) as exc:
			self.message = ("error", "preview failed: {}".format(exc))
			return None
		played = _open_audio(written)
		self.message = ("success", "preview {}: {}".format(
			"playing" if played else "saved", written))
		return written

	def render_document(self):
		"""Render the whole document and save it beside the source file."""
		if not self.selected_path:
			self.message = ("warn", "open a file first")
			return None
		stem = os.path.splitext(self.selected_path)[0]
		path = unique_output(stem + "." + self.config["audio_format"])
		try:
			written = self._render(self.chunks, path, "Rendering document")
		except (ReaderboxError, OSError) as exc:
			self.message = ("error", "render failed: {}".format(exc))
			return None
		self.message = ("success", "saved " + written)
		return written

	# -- terminal loop ---------------------------------------------------

	def pump(self, tokens=None):
		"""Feed an injected key sequence, stopping when the session closes."""
		for token in (self.key_queue if tokens is None else tokens) or ():
			if self.closed:
				break
			self.handle(token)
		return self

	def run(self, stream=None):
		"""Own the terminal for one session; always restores the screen."""
		stream = sys.stdout if stream is None else stream
		self.stream = stream
		self.cap = self.cap or tui.detect(stream)
		self.screen = tui.screen.Screen(stream)
		self.canvas = tui.screen.Canvas(stream=stream)
		reader = tui.keys.KeyReader()
		with tui.keys.raw_mode():
			self.screen.enter()
			try:
				full = True
				reader.start()
				while not self.closed:
					token = reader.wait(0.1)
					if token is not None:
						self.handle(token)
					if self.screen.poll_resize():
						self.canvas = tui.screen.Canvas(stream=stream)
						full = True
					self.draw(full=full)
					self.canvas.render(full=full)
					full = False
			finally:
				reader.stop()
				self.screen.exit()
		return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _report(kind, text, cap):
	stream = sys.stderr if kind == "error" else sys.stdout
	print(tui.status(kind, text, cap=cap), file=stream)


def main(argv=None):
	parser = argparse.ArgumentParser(
		prog="readerbox",
		description="Full-screen document-to-speech reader for Chatterbox TTS.")
	parser.add_argument("--config", default=None,
						help="configuration file (default: {} beside the script)".format(
							CONFIG_NAME))
	parser.add_argument("--no-model-switch", action="store_true",
						help="leave the server's loaded model alone")
	args = parser.parse_args(argv)

	tui.init_ansi()
	cap = tui.detect()
	path = os.path.abspath(os.path.expanduser(args.config or CONFIG_PATH))

	if not os.path.exists(path):
		try:
			with open(path, "w", encoding="utf-8", newline="\n") as handle:
				handle.write(default_config_text())
		except OSError as exc:
			_report("error", "cannot create {}: {}".format(path, exc), cap)
			return 2
		_report("warn", "created {}. Configure server and port in that file, "
				"then run readerbox again.".format(path), cap)
		return 2

	try:
		config = read_config(path)
	except ConfigError as exc:
		_report("error", "{}: {}".format(path, exc), cap)
		return 2
	except OSError as exc:
		_report("error", "cannot read {}: {}".format(path, exc), cap)
		return 2

	client = ChatterboxClient(config)
	try:
		info = client.model_info()
	except ApiError as exc:
		_report("error", "Chatterbox API is not available at {}: {}".format(
			client.base, exc), cap)
		_report("info", "start the Chatterbox TTS Server, check server/port "
				"in {}, then rerun.".format(path), cap)
		return 2

	if not args.no_model_switch:
		try:
			wanted = "turbo" if config["turbo"] else "original"
			if info.get("type") and info.get("type") != wanted:
				_report("info", "switching the server model to Chatterbox {} "
						"(this can take a minute)...".format(wanted), cap)
			info = client.ensure_model(config["turbo"])
		except ApiError as exc:
			_report("warn", "could not switch the server model: {}".format(exc),
					cap)
			try:
				info = client.model_info()
			except ApiError:
				info = {}
	if info.get("loaded") and not config["turbo"] and info.get("type") == "turbo":
		_report("warn", "config says original Chatterbox but the server is "
				"running turbo", cap)

	voices = []
	try:
		voices = client.voices()
	except ApiError:
		pass

	tui.require_tty("readerbox")
	app = ReaderBox(client, config, path, voices=voices, cap=cap)
	return app.run()


if __name__ == "__main__":
	sys.exit(main())
