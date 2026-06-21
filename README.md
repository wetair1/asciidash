
# asciidash

A configurable ASCII **info dashboard** for your terminal. One screen that
live-updates with a big ASCII clock, date, CPU / RAM / disk load, uptime, host
info, weather, a mini calendar and a quote of the day — all wrapped in tidy
bordered widgets with switchable color themes.

Pure **Python 3, standard library only** — no `pip install`, no `psutil`.
System stats are read straight from `/proc`, so it runs anywhere with no setup.

## Features

- 🕐 **Big ASCII clock** + full date and ISO week (12h / 24h, seconds on/off)
- 🖥 **CPU** — overall load, per-core bars, and load average
- 🧠 **Memory** and 💾 **Disk** — usage bars colored by threshold
  (green → yellow → red)
- 🌦 **Weather** — live from [wttr.in](https://wttr.in) when online, with an
  offline demo fallback so it always renders (ASCII weather icons included)
- 📅 **Calendar** for the current month with today highlighted
- 👤 **Host** — user, hostname, OS, kernel, arch, uptime
- 💬 **Quote of the day**
- 🎨 **Themes:** `arch`, `matrix`, `amber`, `nord`, `mono`
- ⚙️ **Fully configurable** via a JSON config: widgets, layout/columns,
  refresh rate, units, time format, custom quotes
- 📸 **`--once` mode** prints a single colored frame to stdout — perfect for
  screenshots or dropping into your `.bashrc` / `motd`

## Requirements

- Python 3.7+
- A terminal with 256-color / truecolor support
- Linux for the system widgets (CPU / mem / uptime read from `/proc`).
  On macOS the clock, calendar, weather, disk and quote widgets still work.

## Install

```bash
git clone https://github.com/wetair1/asciidash.git
cd asciidash
python3 dash.py
```

Optionally make it runnable from anywhere:

```bash
chmod +x dash.py
ln -s "$PWD/dash.py" ~/.local/bin/asciidash
```

## Usage

```bash
python3 dash.py                      # live TUI
python3 dash.py --once                # render one frame and exit
python3 dash.py --theme matrix        # pick a theme
python3 dash.py --interval 1          # refresh every second
python3 dash.py --location Berlin     # override weather location
python3 dash.py --list-themes
python3 dash.py --reset-config        # rewrite the default config
```

### Live keybindings

| Key | Action |
| --- | --- |
| `q` / `Esc` | quit |
| `t` | cycle theme |
| `s` | toggle seconds on the clock |
| `r` | refresh weather now |

### CLI options

| Flag | Description |
| --- | --- |
| `--once` | render a single frame to stdout and exit |
| `--theme NAME` | override the configured theme |
| `--interval SEC` | refresh interval in live mode |
| `--location NAME` | override weather location |
| `--no-color` | disable colors |
| `--width N` / `--height N` | canvas size for `--once` |
| `--config PATH` | use a custom config file |
| `--reset-config` | write the default config |
| `--list-themes` | list available themes |

## Configuration

On first run a config file is created at:

```
~/.config/asciidash/config.json
```

Example:

```json
{
  "theme": "arch",
  "refresh": 1.0,
  "time_format": "24h",
  "show_seconds": true,
  "weather": {
    "enabled": true,
    "location": "Kyiv",
    "units": "metric",
    "refresh_sec": 600
  },
  "layout": {
    "top": ["clock"],
    "columns": [
      ["weather", "cpu", "memory", "disk"],
      ["host", "calendar", "quote"]
    ]
  },
  "quotes": ["Talk is cheap. Show me the code. — Linus Torvalds"]
}
```

### Layout

- `top` — widgets stacked full-width at the top (great for the clock).
- `columns` — a list of columns; each column is a list of widgets stacked
  top to bottom. Add or remove columns to change the grid.

### Available widgets

`clock` · `weather` · `cpu` · `memory` · `disk` · `host` · `calendar` · `quote`

Remove any you don't want, or reorder them however you like.

## Themes

| Theme | Look |
| --- | --- |
| `arch` | cyan accent on blue borders |
| `matrix` | all green |
| `amber` | retro amber |
| `nord` | cool blue/cyan |
| `mono` | minimal monochrome |


## Notes

- Weather needs network access; without it the dashboard shows the
  `weather.offline_demo` values and labels them as a demo.
- CPU usage is sampled from `/proc/stat` between refreshes, so the very first
  frame may show `0%` until a delta is available.
- Tip: drop `python3 dash.py --once` into your `.bashrc` or `motd` to print a
  fresh dashboard frame every time you open a terminal.

## License

MIT
