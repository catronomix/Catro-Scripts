# Catro-Scripts - Development

Internal notes for working on the collection: how terminal output is built, how
the theme system works, and how the suite is run. User-facing usage lives in
[README.md](README.md); repository conventions for contributors live in
[AGENTS.md](AGENTS.md).

## Language composition

- **Python**: 89.2%
- **Shell**: 5.9%
- **Batchfile**: 4.9%

## Terminal styling (`tui/`)

The `tui/` package is the one place terminal presentation lives: capability
detection, the house palette, styled text, tables, prompts, screen primitives,
progress, paging and the frame loop that hosts `.screensaver` plugins. Scripts
import it instead of carrying their own escape codes, so colours, box glyphs and
pipe behaviour stay consistent.

Styling is resolved once per run, in this order: `NO_COLOR`,
`FORCE_COLOR`/`CLICOLOR_FORCE`, `CATRO_COLOR` (`none|16|256|true`), then
`config.ini`, then autodetection (terminal type, Windows console age, SSH, tty).
Colour and layout come from a named JSON theme under `themes/`
(`cozypurple.json` ships; `themes/README.md` documents the schema). Every theme
carries three hand-authored looks - `default` (shown as `soft`),
`contrast-light` and `contrast-dark` - plus rendering properties: header
alignment, border/table/button/scrollbar styles, focus style and zebra rows.
The gitignored `theme.ini` next to the wrappers selects the theme name and the
look, and every script shares both, so switching `theme` switches the whole
collection, never one script. `list`'s default appearance therefore changed
from the old purple-on-black to cozy purple; the checked-in golden fixture pins
the new default. Each colour is defined once and downgraded to the running
colour level, so a 16-colour terminal and a truecolor one show the same layout.

A page is composed from the shared chrome helpers rather than hand-printed
banners: `tui.header()` (title band plus rule), `tui.panel()` (framed block),
`tui.rule()`, `tui.field()` (key/value rows), `tui.status()` (`[ok]`/`[warn]`/
`[error]`/`[info]` lines), `tui.fill()` (a full-width background band) and
`tui.menu()`, on top of `tui.render_table()`/`print_table()`/`key_values()`/
`banner()`/`section()`. The frame is `border-fg`, headers and bars sit on
`bg-inside`, zebra rows and footer bars on `bg-stripe`, so a script that prints a
page looks like every other script. `mdreader` keeps its curses/rich renderer
but maps its three display modes onto the same three palettes (mode 0 `soft`,
mode 1 `contrast-light`, mode 2 `contrast-dark`) and paints its window
background, frame, status bar and shortcut bar from `bg`, `border-fg`,
`bg-inside` and `bg-stripe`.

A pipe stays plain by default: no ANSI escapes, no box glyphs, no padding - table
rows become TAB-separated fields, which keeps `list`, `count`, `action list` and
friends usable in scripts and `grep`. An explicit colour request on the pipe
(`FORCE_COLOR`/`CLICOLOR_FORCE`, or a real `CATRO_COLOR` level) turns plain off
instead: the pipe gets the full styled table - borders, padding, zebra rows and
escapes - so `FORCE_COLOR=3 list.py | cat` is both coloured and readable.
`NO_COLOR` still wins over any request. Turning colour off on a real terminal
(`NO_COLOR`, `TERM=dumb`, `theme set color.level none`) only removes the escapes:
the table keeps its borders, alignment and truncation.

Theme selection lives in `theme.ini` next to the wrappers (gitignored, one per
checkout); the colour level and table style stay in `config.ini`. Both are
managed with the `theme` command, which `python -m tui` also runs:

| command | effect |
|---|---|
| `theme` | overview: theme name, look, level, table style, paths, writability |
| `theme cozypurple` | select `themes/cozypurple.json`; exit 2 when missing or invalid |
| `theme list` | list the available themes |
| `theme soft` / `theme default` | the default look |
| `theme light` / `theme contrast-light` | the contrast-light look |
| `theme dark` / `theme contrast-dark` | the contrast-dark look |
| `theme toggle` | cycle soft -> light -> dark -> soft |
| `theme palette` | the active look's swatches |
| `theme set theme.name <name>` | select a theme by name |
| `theme set theme.look <look>` | select a look (short or long spelling) |
| `theme set color.level <level>` | `auto`, `none`, `16`, `256` or `true` |
| `theme set table.style <style>` | `auto`, `unicode` or `ascii` |
| `theme edit [name]` | full-screen editor (needs an interactive terminal) |

Piped, every page degrades to TAB-joined `key<TAB>value` rows with no escapes.
An unwritable `theme.ini`/`config.ini` prints one line naming the path and exits
1; `theme edit` off a terminal prints one line on stderr and exits 2.

`theme edit` opens the editor on the active theme, or on `<name>` when given. Its
three previews show the three looks live: Properties edits the nine rendering
properties, Colours opens a hex/HSV colour picker per palette key, and the
picker warns below WCAG AA (4.5:1 against `bg`/`bg-stripe`) but never blocks.
`Ctrl-S` saves atomically to `themes/<name>.json` (the filename is preseeded,
`.json` is implied, and an existing different file asks before it is
overwritten). A save only rewrites the lines you changed: the document's hex
spelling is kept, so re-saving an untouched theme leaves the file byte-identical.
Load lists every theme, marks the active one `*` and keeps an invalid file as an
`!` row. To share a theme, copy its JSON into `themes/`, keeping `name` equal to
the filename.

`CATRO_ASCII=1` forces ASCII box fallbacks, and
`CATRO_THEME=soft|contrast-light|contrast-dark` overrides the file for one run.

## Testing

Stdlib-only smoke suite, no installs needed: `python -m unittest discover -s tests -v`

Linux/POSIX compatibility is verified in a checked-in container instead of a
throwaway interpreter, because this host's only WSL distribution is
`docker-desktop` (no shell, no `python3`). Requires Docker:

```bash
python tests/container/run.py                    # both interpreters, stdlib + extras
python tests/container/run.py --python 3.12      # one interpreter
python tests/container/run.py --extras 0         # acceptance gate only
```

The runner builds `tests/container/Dockerfile` twice - `EXTRAS=0` (stdlib only,
the acceptance gate: every script must import cleanly and answer `--help`) and
`EXTRAS=1` (adds `pillow`, `piexif`, `pydub`) - then runs the smoke suite plus
the Linux column of the cross-platform sweep inside each image, read-only and
without network. Exit code is non-zero on a failing suite, a hanging or crashing
probe, or a probe that exits 0 after printing an error line. Evidence lands in
`.devteam/artifacts/container/` (`.devteam/` is not tracked). Details, including
the deliberately skipped `decord`/`ffmpeg` extras, are in
`tests/container/README.md`.

WSL is *not* covered: the container is the POSIX oracle, and the wrappers were
not exercised natively inside WSL.
