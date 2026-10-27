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
  `bg-stripe`) the picker warns but never blocks.
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
  "schema": 2,
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
    "corner-char": "none"
  },
  "looks": {
    "default": {
      "bg": "#1B1726",
      "bg-inside": "#292238",
      "bg-inside-active": "#352B49",
      "bg-stripe": "#352B49",
      "fg": "#D4C8EB",
      "fg-muted": "#A392C0",
      "fg-accent": "#F5CD68",
      "fg-success": "#7FD1A0",
      "fg-warn": "#E09F67",
      "fg-error": "#FF6B6B",
      "border-bg": "#292238",
      "border-fg": "#A392C0",
      "border-bg-active": "#352B49",
      "border-fg-active": "#F5CD68",
      "header-fg": "#F5CD68",
      "header-bg": "#292238"
    },
    "contrast-dark":  { "bg": "#000000", "...": "the other 15 keys" },
    "contrast-light": { "bg": "#FFFFFF", "...": "the other 15 keys" }
  }
}
```

- `schema` must be `2`. A schema-1 file still loads: `tui/theme_migrate.py`
  renames the nine slots and derives the five new ones in memory, and the first
  save rewrites it as schema 2. A read never rewrites a file.
- `name` is a slug (`[a-z0-9][a-z0-9-]*`) and must match the filename
  (`themes/<name>.json`); `display` is free text for page titles. The top-level
  keys are exactly `schema name display properties looks`.
- `looks` holds exactly `default`, `contrast-dark` and `contrast-light`, each
  with exactly the sixteen keys below, each a `#rrggbb` string. A save keeps the
  case the document already carries but canonicalises structure once (a missing
  `#` is added, keys re-ordered, 2-space indent, one trailing LF), so an
  already-canonical file round-trips byte for byte and a hand-written one is
  tidied once.
- `properties` holds all nine keys; `table_zebra` is a boolean. Allowed values
  live in `tui/theme_schema.py` (`PROPERTY_VALUES`, re-exported by
  `tui/theme_engine.py`). `selection_style` is gone: a selection is
  `bg-inside-active` as the fill with `border-fg-active` on the focused frame.

| key | paints |
|---|---|
| `bg` | the page ground behind a whole page, and the even rows of a striped table |
| `bg-inside` | box interiors (`tui.panel`, the menu, header/footer bars) and the odd rows of a striped table |
| `bg-inside-active` | the selected menu row's fill (the pointed row, `fg-accent` on this) |
| `bg-stripe` | stripes and alternate rows in the reader (shortcut bar, alternate table row) and the editor preview |
| `fg` | body text and the icons/labels that are not one of the semantic colours below |
| `fg-muted` | secondary text: field keys, hints, dimmed and inactive labels |
| `fg-accent` | accent text and markers: headings, the menu pointer, `[info]`, and a button focused with `focus_style: accent` |
| `fg-success` | `[ok]` status text and the recency ramp's fresh end |
| `fg-warn` | `[warn]` status text |
| `fg-error` | `[error]` status text |
| `border-bg` | the background band behind a frame's glyphs |
| `border-fg` | frame glyphs: panel/table boxes, rules and the reader's window frame |
| `border-bg-active` | the same band for a focused frame |
| `border-fg-active` | the glyphs of a focused frame |
| `header-fg` | header text: the masthead title, table headers and banner titles |
| `header-bg` | the full-width ground behind a header band |

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
| `corner-char` | `none` `@` `x` `#` `+` `o` `*` | replaces the four corner cells only; edges, tees and rules still come from `border_style`, and `none` keeps the family's own corners |

`table.style` in `config.ini` still overrides `border_style` for one run
(`ascii` forces `+ - |`, `unicode` keeps the theme's glyphs), and a non-Unicode
terminal degrades every family except `none` to ASCII. `corner-char` lands after
that degradation, so a custom corner is always the byte the theme asked for. The
shipped values reproduce the default look byte for byte.

Validation is all-or-nothing: one missing key, unknown top-level key, unknown
look/property key or unknown value rejects the file, so a typo cannot ship a
half-theme. A schema-1 file is the one exception: it is read through the
migration step, so old files still load, but a schema-2 document that still
carries a retired key such as `selection_style` is rejected rather than
silently dropped. A missing or invalid theme file never breaks rendering - the
scripts fall back to the shipped `cozypurple` document, which is also the only
copy of the built-in palette (no embedded hex table). If `themes/cozypurple.json`
itself is missing or unreadable, reads raise one clear `ThemeError` instead of
inventing colours.

Look selectors: `soft`/`default` = `default`, `light`/`contrast-light` =
`contrast-light`, `dark`/`contrast-dark` = `contrast-dark`. `theme toggle`
cycles soft -> light -> dark -> soft.

## Sharing a theme

Copy the JSON here, keep `name` equal to the filename, and select it in
`theme.ini` (`catro-scripts theme set theme.name <name>`) or with the editor's
Load popup. Keep every non-background colour at or above 4.5:1 contrast against
both `bg` and `bg-stripe` if you want it to stay readable for everyone: the
shipped looks meet that threshold and are pinned by a test, while the editor's
colour picker only warns about a custom file below it.
