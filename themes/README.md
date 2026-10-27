# Themes

One JSON file per theme in this directory. `cozypurple.json` ships with the
repository and holds the current default look (cozy purple: gold on velvet
purple), the look the golden fixture pins.

Select a theme by writing its `name` in the gitignored `theme.ini` next to the
scripts; the look (`soft`, `light`, `dark`) can also be changed with
`catro-scripts theme soft|light|dark` or `theme toggle`. `catro-scripts theme`
prints the active look and the paths it uses, and falls back to the built-in
`cozypurple` default whenever the file is missing or invalid.

## The editor

`catro-scripts theme edit [name]` opens the full-screen editor on `<name>`, or
on the active theme when no name is given. It needs an interactive terminal and
exits 2 without one.

- Properties edits the nine rendering properties; Colours opens a hex/HSV colour
  picker for the selected palette key. Below WCAG AA (4.5:1 against `bg` and
  `zebra_bg`) the picker warns but never blocks.
- The three previews show the three looks of the document under edit, live.
- `Ctrl-S` saves. The filename is preseeded with the theme name and `.json` is
  implied; the name must be a legal slug (`a-z`, `0-9`, `-`). Saving is atomic
  and updates `theme.ini` to the saved theme. An existing different file asks
  `overwrite? y/n` first, so `n` leaves it byte-identical.
- Load lists every `themes/*.json` sorted, marks the active theme with `*` and
  an unreadable or invalid file with `!`; Enter loads a valid row (asking first
  when there are unsaved changes) and the list keeps working after an invalid
  row is chosen.

## Schema

```json
{
  "schema": 1,
  "name": "cozypurple",
  "display": "Cozy Purple",
  "properties": {
    "header_align": "left",
    "border_style": "rounded",
    "button_style": "filled",
    "button_decoration": "brackets",
    "table_style": "box",
    "table_zebra": true,
    "focus_style": "reverse",
    "scrollbar_style": "block",
    "selection_style": "accent"
  },
  "looks": {
    "default":        { "bg": "#1B1726", "...": "11 keys" },
    "contrast-dark":  { "bg": "#000000", "...": "11 keys" },
    "contrast-light": { "bg": "#FFFFFF", "...": "11 keys" }
  }
}
```

- `schema` must be `1`.
- `name` is a slug (`[a-z0-9][a-z0-9-]*`) and must match the filename
  (`themes/<name>.json`); `display` is free text for page titles.
- `looks` holds exactly `default`, `contrast-dark` and `contrast-light`, each
  with exactly `bg surface fg muted accent success warn error border header
  zebra_bg`, each a `#rrggbb` string (`#` optional on read; lowercase written).
- `properties` holds all nine keys; `table_zebra` is a boolean. Allowed values
  live in `tui/theme_schema.py` (`PROPERTY_VALUES`, re-exported by
  `tui/theme_engine.py`).

| property | values | effect |
|---|---|---|
| `header_align` | `left` `center` `right` | label placement in the masthead band |
| `border_style` | `rounded` `square` `heavy` `double` `ascii` `none` | table/chrome frame glyphs (`rounded` is the shipped set; `none` keeps the layout and drops the borders) |
| `button_style` | `filled` `outline` `plain` `underline` | `chrome.button` ground and attributes |
| `button_decoration` | `none` `brackets` `angles` `braces` `colons` `pipes` `chevron` `ellipsis` | wrapper drawn around a button label |
| `table_style` | `box` `borderless` `compact` | table frame (an explicit `box=` argument still wins) |
| `table_zebra` | `true` `false` | alternating row background (an explicit `zebra=` wins) |
| `focus_style` | `reverse` `accent` `underline` | how a focused button is restyled |
| `scrollbar_style` | `block` `line` `ascii` | `chrome.scrollbar` thumb/track glyphs |
| `selection_style` | `accent` | reserved; single value in v1 |

`table.style` in `config.ini` still overrides `border_style` for one run
(`ascii` forces `+ - |`, `unicode` keeps the theme's glyphs), and a non-Unicode
terminal degrades every family except `none` to ASCII. The shipped values
reproduce the default look byte for byte.

Validation is all-or-nothing: one missing key or unknown value rejects the file,
so a typo cannot ship a half-theme. A missing or invalid file never breaks
rendering - the scripts fall back to the built-in `cozypurple` default look.

Look selectors: `soft`/`default` = `default`, `light`/`contrast-light` =
`contrast-light`, `dark`/`contrast-dark` = `contrast-dark`. `theme toggle`
cycles soft -> light -> dark -> soft.

## Sharing a theme

Copy the JSON here, keep `name` equal to the filename, and select it in
`theme.ini` (`catro-scripts theme set theme.name <name>`) or with the editor's
Load popup. Keep every non-background colour at or above 4.5:1 contrast against
both `bg` and `zebra_bg` if you want it to stay readable for everyone: the
shipped looks meet that threshold and are pinned by a test, while the editor's
colour picker only warns about a custom file below it.
