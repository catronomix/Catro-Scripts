# Readerbox tests: config, Markdown, chunking, API and headless UI
"""
		READERBOX
		==========
No Chatterbox inference and no real terminal are used here. Configuration,
Markdown rewriting, chunk planning, WAV merging, the HTTP client and the
full-screen key flow are all driven through their injected seams.
"""

import io
import json
import os
import sys
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
	sys.path.insert(0, str(REPO))

import readerbox  # noqa: E402
import tui  # noqa: E402

CONFIG = {
	"server": "127.0.0.1",
	"port": 8004,
	"audio_format": "wav",
	"sample_rate": 24000,
	"turbo": False,
	"voice": "",
	"voice_mode": "predefined",
	"chunk_size": 150,
	"temperature": 0.8,
	"exaggeration": 0.5,
	"cfg_weight": 0.5,
	"seed": 0,
}


def wav_blob(frames=2400, rate=24000):
	"""One second of silence as a mono 16-bit WAV."""
	buffer = io.BytesIO()
	with wave.open(buffer, "wb") as handle:
		handle.setnchannels(1)
		handle.setsampwidth(2)
		handle.setframerate(rate)
		handle.writeframes(b"\x00\x00" * frames)
	return buffer.getvalue()


class ConfigTests(unittest.TestCase):
	def test_missing_file_writes_a_template_and_returns_2(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "readerbox-config.yaml")
			out, err = io.StringIO(), io.StringIO()
			with redirect_stdout(out), redirect_stderr(err):
				status = readerbox.main(["--config", path])
			self.assertEqual(status, 2)
			self.assertTrue(os.path.exists(path))
			text = Path(path).read_text(encoding="utf-8")
			self.assertIn("server:", text)
			self.assertIn("port:", text)
			self.assertIn("configure", (out.getvalue() + err.getvalue()).lower()
						  or "readerbox")

	def test_default_config_lives_beside_the_script(self):
		self.assertEqual(os.path.dirname(readerbox.CONFIG_PATH),
						 os.path.dirname(os.path.abspath(readerbox.__file__)))
		self.assertTrue(readerbox.CONFIG_PATH.endswith("readerbox-config.yaml"))

	def test_blank_server_is_a_config_error(self):
		values = dict(CONFIG, server="")
		with self.assertRaises(readerbox.ConfigError):
			readerbox.validate_config(values)

	def test_blank_port_names_the_missing_setting(self):
		with self.assertRaisesRegex(readerbox.ConfigError, "port is blank"):
			readerbox.validate_config(dict(CONFIG, port=""))

	def test_main_refuses_a_config_that_still_has_errors(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "cfg.yaml")
			Path(path).write_text("server: ''\nport: 8004\n", encoding="utf-8")
			out, err = io.StringIO(), io.StringIO()
			with redirect_stdout(out), redirect_stderr(err):
				status = readerbox.main(["--config", path])
		self.assertEqual(status, 2)
		self.assertIn("server is blank", err.getvalue())

	def test_main_aborts_when_the_api_is_not_available(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "cfg.yaml")
			readerbox.write_config(path, CONFIG)
			out, err = io.StringIO(), io.StringIO()
			with mock.patch.object(readerbox.ChatterboxClient, "model_info",
								   side_effect=readerbox.ApiError("down")), \
				 redirect_stdout(out), redirect_stderr(err):
				status = readerbox.main(["--config", path])
		self.assertEqual(status, 2)
		self.assertIn("not available", err.getvalue().lower())

	def test_invalid_port_format_and_ranges_are_rejected(self):
		for values in (
				dict(CONFIG, port=0),
				dict(CONFIG, port=70000),
				dict(CONFIG, audio_format="flac"),
				dict(CONFIG, sample_rate=100),
				dict(CONFIG, chunk_size=10),
				dict(CONFIG, temperature=4),
				dict(CONFIG, seed=-1)):
			with self.assertRaises(readerbox.ConfigError, msg=values):
				readerbox.validate_config(values)

	def test_parse_defaults_and_round_trip(self):
		text = "server: host\nport: 9000\nturbo: true\nchunk_size: 120\n"
		values = readerbox.parse_config(text)
		self.assertEqual((values["server"], values["port"]), ("host", 9000))
		self.assertTrue(values["turbo"])
		self.assertEqual(values["audio_format"], "wav")
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "cfg.yaml")
			readerbox.write_config(path, values)
			self.assertEqual(readerbox.read_config(path), values)

	def test_unknown_option_is_an_error(self):
		with self.assertRaises(readerbox.ConfigError):
			readerbox.parse_config("server: host\nport: 1\nsurprise: yes\n")

	def test_base_url_appends_the_configured_port_once(self):
		self.assertEqual(readerbox.base_url(dict(CONFIG, server="host")),
						 "http://host:8004")
		self.assertEqual(readerbox.base_url(dict(CONFIG, server="host:9000")),
						 "http://host:9000")
		self.assertEqual(readerbox.base_url(dict(CONFIG, server="https://host")),
						 "https://host:8004")


class MarkdownTests(unittest.TestCase):
	def test_interjections_become_spaced_dashes(self):
		units = readerbox.markdown_units(
			'He said *quietly* (almost a whisper) "hello" to me.\n')
		self.assertEqual(units[0].text,
						 "He said - quietly - - almost a whisper - - hello - to me.")

	def test_line_endings_get_commas_and_paragraph_gets_a_full_stop(self):
		units = readerbox.markdown_units(
			"first line\nsecond line\n\nlast paragraph\n")
		self.assertIn("first line,", units[0].text)
		self.assertTrue(units[0].text.endswith("."))
		self.assertTrue(units[1].text.endswith("."))
		self.assertEqual(len(units), 2)

	def test_heading_and_rule_create_their_own_pauses(self):
		units = readerbox.markdown_units("# Title\n\n### Sub\n\ntext\n\n---\n")
		self.assertEqual(units[0].kind, "heading")
		self.assertGreaterEqual(units[0].pause_ms,
								readerbox.HEADING_PAUSE_MS)
		self.assertGreater(units[1].pause_ms, units[0].pause_ms)
		self.assertGreater(units[0].pause_ms, units[2].pause_ms)
		self.assertEqual(units[2].kind, "text")
		self.assertEqual(units[3].kind, "rule")
		self.assertEqual(units[3].text, "")
		self.assertGreaterEqual(units[3].pause_ms, readerbox.RULE_PAUSE_MS)

	def test_plain_text_gets_no_markdown_rewrite(self):
		units = readerbox.document_units("readme.txt",
										 "line one\n\nline two")
		self.assertEqual([unit.text for unit in units],
						 ["line one", "line two"])

	def test_preprocess_produces_display_text(self):
		text = readerbox.preprocess_markdown("# T\n\nA *b* line\n")
		self.assertIn("T", text)
		self.assertIn("- b -", text)


class ChunkTests(unittest.TestCase):
	def test_every_paragraph_starts_a_new_chunk(self):
		units = [readerbox.Unit("one.", "text"),
				 readerbox.Unit("two.", "text")]
		self.assertEqual([chunk.text for chunk in
						  readerbox.build_chunks(units, 150)],
						 ["one.", "two."])

	def test_long_block_splits_on_sentences_within_size(self):
		text = " ".join("Sentence number {} is fine.".format(i)
						for i in range(20))
		chunks = readerbox.build_chunks(
			[readerbox.Unit(text, "text")], 80)
		self.assertGreater(len(chunks), 1)
		self.assertTrue(all(len(chunk.text) <= 80 for chunk in chunks))
		self.assertTrue(all(chunk.text.endswith(".") for chunk in chunks))

	def test_rule_becomes_an_empty_silence_chunk(self):
		chunks = readerbox.build_chunks(
			[readerbox.Unit("", "rule", 600)], 150)
		self.assertEqual([(chunk.text, chunk.pause_ms) for chunk in chunks],
						 [("", 600)])

	def test_preview_collects_two_sentences(self):
		chunks = [readerbox.Chunk("One. Two. Three.")]
		self.assertEqual(readerbox.preview_sentences(chunks), "One. Two.")


class MergeTests(unittest.TestCase):
	def test_merges_blobs_and_inserts_silence(self):
		with tempfile.TemporaryDirectory() as directory:
			path = os.path.join(directory, "out.wav")
			readerbox.merge_wavs([wav_blob(100), wav_blob(100)], [500, 0],
								 path, "wav", 24000)
			with wave.open(path, "rb") as handle:
				self.assertEqual(handle.getnframes(), 200 + 12000)

	def test_unique_output_avoids_overwriting(self):
		with tempfile.TemporaryDirectory() as directory:
			first = os.path.join(directory, "a.wav")
			Path(first).write_bytes(b"x")
			second = readerbox.unique_output(first)
			self.assertTrue(second.endswith("a (2).wav"))


class _Response:
	def __init__(self, body, content_type="application/json"):
		self.body = body
		self.headers = {"Content-Type": content_type}

	def read(self):
		return self.body

	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False


class ApiTests(unittest.TestCase):
	def client(self):
		return readerbox.ChatterboxClient(CONFIG)

	def test_model_info_parses_json(self):
		response = _Response(json.dumps({"loaded": True, "type": "turbo"}).encode())
		with mock.patch.object(readerbox.urlrequest, "urlopen",
							   return_value=response):
			self.assertEqual(self.client().model_info()["type"], "turbo")

	def test_unreachable_server_raises_api_error(self):
		with mock.patch.object(readerbox.urlrequest, "urlopen",
							   side_effect=readerbox.urlerror.URLError("down")):
			with self.assertRaises(readerbox.ApiError):
				self.client().model_info()

	def test_voices_combine_predefined_and_reference_lists(self):
		responses = [
			_Response(json.dumps([{"filename": "a.wav",
								   "display_name": "Alice"}]).encode()),
			_Response(json.dumps(["ref.wav"]).encode()),
		]
		with mock.patch.object(readerbox.urlrequest, "urlopen",
							   side_effect=responses):
			voices = self.client().voices()
		self.assertEqual([voice["id"] for voice in voices], ["a.wav", "ref.wav"])
		self.assertEqual(voices[1]["mode"], "clone")

	def test_synthesize_sends_params_and_returns_audio(self):
		captured = {}

		def fake(request, timeout=None):
			captured["url"] = request.full_url
			captured["body"] = json.loads(request.data.decode())
			return _Response(wav_blob(10), "audio/wav")

		settings = dict(CONFIG, voice="a.wav", seed=7)
		with mock.patch.object(readerbox.urlrequest, "urlopen", side_effect=fake):
			blob = self.client().synthesize("hello", settings)
		self.assertTrue(blob.startswith(b"RIFF"))
		self.assertEqual(captured["url"], "http://127.0.0.1:8004/tts")
		self.assertEqual(captured["body"]["text"], "hello")
		self.assertEqual(captured["body"]["predefined_voice_id"], "a.wav")
		self.assertEqual(captured["body"]["seed"], 7)
		self.assertIn("exaggeration", captured["body"])

	def test_turbo_omits_the_unsupported_controls(self):
		captured = {}

		def fake(request, timeout=None):
			captured["body"] = json.loads(request.data.decode())
			return _Response(wav_blob(10), "audio/wav")

		with mock.patch.object(readerbox.urlrequest, "urlopen", side_effect=fake):
			self.client().synthesize("hi", dict(CONFIG, turbo=True))
		self.assertNotIn("exaggeration", captured["body"])
		self.assertNotIn("cfg_weight", captured["body"])

	def test_ensure_model_leaves_a_matching_model_alone(self):
		client = self.client()
		with mock.patch.object(client, "model_info",
							   return_value={"loaded": True, "type": "original"}), \
			 mock.patch.object(client, "save_settings") as save:
			client.ensure_model(False)
		save.assert_not_called()

	def test_ensure_model_hot_swaps_a_mismatched_model(self):
		client = self.client()
		with mock.patch.object(client, "model_info", side_effect=[
				{"loaded": True, "type": "turbo"},
				{"loaded": True, "type": "original"}]), \
			 mock.patch.object(client, "save_settings") as save, \
			 mock.patch.object(client, "restart_server",
							   return_value={"message": "ok"}), \
			 mock.patch.object(readerbox.time, "sleep"):
			info = client.ensure_model(False)
		self.assertEqual(info["type"], "original")
		save.assert_called_once_with({"model": {"repo_id": "chatterbox"}})


class UiTests(unittest.TestCase):
	def setUp(self):
		self._td = tempfile.TemporaryDirectory()
		self.root = Path(self._td.name)
		(self.root / "notes.md").write_text(
			"# Heading\n\nA *short* paragraph.\n", encoding="utf-8")
		(self.root / "sub").mkdir()
		(self.root / "sub" / "inner.txt").write_text("inner", encoding="utf-8")
		self.canvas = tui.Canvas(width=100, height=30, stream=io.StringIO())
		self.app = readerbox.ReaderBox(
			None, dict(CONFIG), str(self.root / "cfg.yaml"), root=str(self.root),
			canvas=self.canvas, cap=tui.detect(), voices=[
				{"id": "a.wav", "label": "Alice", "mode": "predefined"},
				{"id": "b.wav", "label": "Bob", "mode": "predefined"}])

	def tearDown(self):
		self._td.cleanup()

	def test_explorer_lists_folders_then_supported_files(self):
		labels = [entry[0] for entry in self.app.entries]
		self.assertEqual(labels, ["sub/", "notes.md"])

	def test_enter_opens_a_file_and_switches_to_the_menu(self):
		self.app.explorer_index = 1
		self.app.handle("enter")
		self.assertEqual(self.app.mode, "read")
		self.assertEqual(os.path.basename(self.app.selected_path), "notes.md")
		self.assertGreater(len(self.app.chunks), 0)
		self.assertTrue(any("- short -" in chunk.text
							for chunk in self.app.chunks))

	def test_folder_navigation_stays_below_the_root(self):
		self.app.explorer_index = 0
		self.app.handle("enter")
		self.assertTrue(self.app.cwd.endswith("sub"))
		self.app.explorer_index = 0
		self.app.handle("enter")
		self.assertEqual(os.path.normcase(self.app.cwd),
						 os.path.normcase(str(self.root)))

	def test_voice_popup_selects_with_arrows(self):
		self.app.open_file(str(self.root / "notes.md"))
		self.app.focus = "left"
		self.app.menu_index = 0
		self.app.handle("enter")
		self.assertEqual(self.app.popup["kind"], "choice")
		self.app.handle("down")
		self.app.handle("enter")
		self.assertEqual(self.app.settings["voice"], "a.wav")
		self.assertIsNone(self.app.popup)

	def test_numeric_popup_adjusts_and_commits(self):
		self.app.open_file(str(self.root / "notes.md"))
		self.app.menu_index = 5
		self.app.handle("enter")
		self.app.handle("up")
		self.app.handle("enter")
		self.assertEqual(self.app.settings["seed"], 1)

	def test_escape_returns_to_explorer_then_quits(self):
		self.app.open_file(str(self.root / "notes.md"))
		self.app.handle("esc")
		self.assertEqual(self.app.mode, "browse")
		self.app.handle("esc")
		self.assertTrue(self.app.closed)

	def test_draw_paints_status_and_both_panes(self):
		self.app.draw()
		rendered = "\n".join(self.canvas.region(0, 0, 100, 30))
		self.assertIn("readerbox", rendered)
		self.assertIn("chatterbox", rendered)
		self.app.open_file(str(self.root / "notes.md"))
		self.app.draw()
		rendered = "\n".join(self.canvas.region(0, 0, 100, 30))
		self.assertIn("Settings & Actions", rendered)
		self.assertIn("notes.md", rendered)

	def test_save_config_writes_tui_changes(self):
		self.app.open_file(str(self.root / "notes.md"))
		self.app.settings["temperature"] = 0.65
		self.assertTrue(self.app.save_config())
		values = readerbox.read_config(str(self.root / "cfg.yaml"))
		self.assertEqual(values["temperature"], 0.65)

	def test_render_document_without_network_is_reported(self):
		self.app.open_file(str(self.root / "notes.md"))
		self.app.client = mock.Mock(base="http://fake")
		self.app.client.synthesize.side_effect = readerbox.ApiError("down")
		self.assertIsNone(self.app.render_document())
		self.assertEqual(self.app.message[0], "error")

	def test_render_document_saves_audio_beside_the_source(self):
		class FakeClient:
			base = "http://fake"

			def __init__(self):
				self.calls = []

			def synthesize(self, text, settings, seed=None):
				self.calls.append((text, seed))
				return wav_blob(120)

		client = FakeClient()
		self.app.client = client
		self.app.open_file(str(self.root / "notes.md"))
		written = self.app.render_document()
		self.assertIsNotNone(written)
		self.assertTrue(written.endswith("notes.wav"))
		self.assertTrue(os.path.exists(written))
		self.assertEqual(len(client.calls), len(
			[chunk for chunk in self.app.chunks if chunk.text]))
		self.assertEqual(self.app.message[0], "success")

	def test_preview_renders_only_two_sentences(self):
		class FakeClient:
			base = "http://fake"

			def __init__(self):
				self.texts = []

			def synthesize(self, text, settings, seed=None):
				self.texts.append(text)
				return wav_blob(120)

		client = FakeClient()
		self.app.client = client
		self.app.open_file(str(self.root / "notes.md"))
		with mock.patch.object(readerbox, "_open_audio", return_value=False):
			written = self.app.render_preview()
		self.assertTrue(os.path.exists(written))
		self.assertEqual(os.path.dirname(written), str(self.root))
		self.assertIn(".preview.", written)
		self.assertEqual(len(client.texts), 1)
		self.assertEqual(len(readerbox.sentences(client.texts[0])), 2)

	def test_menu_scrolls_so_the_selected_action_stays_visible(self):
		self.app.open_file(str(self.root / "notes.md"))
		self.app.menu_index = 8
		with mock.patch.object(tui.canvas, "terminal_size",
							   return_value=(88, 12)):
			self.app.draw()
		rendered = "\n".join(tui.strip_ansi(line)
							 for line in self.canvas.region(0, 0, 88, 12))
		self.assertGreater(self.app.menu_offset, 0)
		self.assertIn("[save config]", rendered)


if __name__ == "__main__":
	unittest.main()
