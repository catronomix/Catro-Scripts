# Themes

One JSON file per theme in this directory. `cozypurple.json` ships with the
repository and reproduces the look the scripts have always had.

Select a theme by writing its `name` in the gitignored `theme.ini` next to the
scripts; the look (`soft`, `light`, `dark`) can also be changed with
`catro-scripts theme soft|light|dark` or `theme toggle`. `catro-scripts theme`
prints the active look and the paths it uses, and falls back to the built-in
`cozypurple` default whenever the file is missing or invalid.

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

Validation is all-or-nothing: one missing key or unknown value rejects the file,
so a typo cannot ship a half-theme. A missing or invalid file never breaks
rendering - the scripts fall back to the built-in `cozypurple` default look.

Look selectors: `soft`/`default` = `default`, `light`/`contrast-light` =
`contrast-light`, `dark`/`contrast-dark` = `contrast-dark`. `theme toggle`
cycles soft -> light -> dark -> soft.

## Sharing a theme

Copy the JSON here, keep `name` equal to the filename, and select it in
`theme.ini`. Keep every non-background colour at or above 4.5:1 contrast against
both `bg` and `zebra_bg` if you want it to stay readable for everyone: the
shipped looks meet that threshold and are pinned by a test, while a custom file
is only warned about by later tooling (see the theme-engine contract).
