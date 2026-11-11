# Colour math: hex/RGB/HSV conversions, WCAG helpers and the grid column scale
"""
			COLOUR MATH
			===========
Pure colour functions shared by the picker and by any caller that needs to
reason about a colour without drawing one: `hex_to_rgb`/`rgb_to_hex` for the
`#rrggbb` spelling, `rgb_to_hsv`/`hsv_to_rgb` for the HSV model, `luminance`/
`contrast_ratio` with the `WCAG_AA` threshold for the accessibility gate, and
`cell_index` for mapping a 0-1 component onto the picker's 16 two-cell columns
(`STEPS` lives here because that mapping is the only thing that needs it).

Nothing here reads a file, a config or the terminal; `import tui.color_math`
is inert.
"""

import colorsys

WCAG_AA = 4.5  # minimum contrast ratio the picker warns below
STEPS = 16  # grid columns: the scale `cell_index` rounds onto


def hex_to_rgb(value):
	"""(r, g, b) for `#rrggbb` or `rrggbb`; `ValueError` for anything else."""
	text = str(value).strip().removeprefix("#")
	if len(text) != 6 or any(char not in "0123456789abcdefABCDEF" for char in text):
		raise ValueError("not a #rrggbb colour: {!r}".format(value))
	return tuple(int(text[at:at + 2], 16) for at in (0, 2, 4))


def rgb_to_hex(rgb):
	"""Canonical lowercase `#rrggbb` for an (r, g, b) triple."""
	return "#{:02x}{:02x}{:02x}".format(*(int(part) for part in rgb))


def rgb_to_hsv(rgb):
	"""(hue 0-360, saturation 0-1, value 0-1) for an (r, g, b) triple."""
	hue, saturation, value = colorsys.rgb_to_hsv(*(part / 255 for part in rgb))
	return (hue * 360, saturation, value)


def hsv_to_rgb(hsv):
	"""(r, g, b) for an (hue, saturation, value) triple; the hue wraps."""
	hue, saturation, value = (float(part) for part in hsv)
	red, green, blue = colorsys.hsv_to_rgb(hue % 360 / 360, min(1.0, max(0.0, saturation)),
										   min(1.0, max(0.0, value)))
	return tuple(round(part * 255) for part in (red, green, blue))


def luminance(value):
	"""WCAG 2.x relative luminance (0-1) for a `#rrggbb` colour."""
	channels = [part / 255 for part in hex_to_rgb(value)]
	return sum(w * (c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
			   for w, c in zip((0.2126, 0.7152, 0.0722), channels))


def contrast_ratio(first, second):
	"""WCAG 2.x ratio (1.0-21.0) between two `#rrggbb` colours."""
	high, low = sorted((luminance(first), luminance(second)), reverse=True)
	return (high + 0.05) / (low + 0.05)


def cell_index(fraction):
	"""Grid column for a 0-1 component; 0.5 reads as the midpoint, column 8."""
	return max(0, min(STEPS - 1, int(round(float(fraction) * (STEPS - 1)))))
