# Panel Themes

The Moonraker control panel supports 10 built-in themes plus custom themes
uploaded as JSON files. This document describes the theme file format and how
to build your own.

## Theme file format

A theme file is a JSON object with two keys:

```json
{
  "name": "My Theme",
  "vars": {
    "--bg": "#050b16",
    "--panel": "#0a1424",
    "--panel-hi": "#101d33",
    "--line": "#1d3a5f",
    "--line-hi": "#2f6db3",
    "--green": "#4ade80",
    "--green-soft": "#a7f3c9",
    "--cyan": "#4fc3ff",
    "--red": "#ff5d73",
    "--amber": "#f5b94e",
    "--text": "#c8dcf0",
    "--muted": "#5d7d9e"
  }
}
```

| Key    | Required | Rules                                              |
| ------ | -------- | -------------------------------------------------- |
| `name` | yes      | String, 1–50 characters. Shown in the theme picker.|
| `vars` | yes      | Object mapping CSS custom property names to values.|

### Variables

All color variables are required. Values must be a hex color
(`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`) or an `rgb()/rgba()`/`hsl()/hsla()`
function.

| Variable        | Purpose                                          |
| --------------- | ------------------------------------------------ |
| `--bg`          | Page background                                  |
| `--panel`       | Card/panel background                            |
| `--panel-hi`    | Raised surfaces, hover states                    |
| `--line`        | Borders, dividers, grid lines                    |
| `--line-hi`     | Highlighted borders, active outlines             |
| `--green`       | Primary accent — ok/healthy states, brand color  |
| `--green-soft`  | Soft accent — glows, bright labels               |
| `--cyan`        | Secondary accent — links, info states            |
| `--red`         | Error/danger states                              |
| `--amber`       | Warning states                                   |
| `--text`        | Primary text                                     |
| `--muted`       | Secondary text, captions                         |

Optional variables:

| Variable       | Purpose                                                   |
| -------------- | --------------------------------------------------------- |
| `--glow`       | Radial glow tint at the top of the page (rgba)            |
| `--grid`       | Background grid-line tint (rgba)                          |
| `--input-bg`   | Input/select field background                             |
| `--input-text` | Input/select field text                                   |
| `--input-line` | Input/select field border                                 |
| `--on-accent`  | Text drawn on accent-filled buttons (must contrast `--green`) |
| `--mono`       | Monospace font stack for console/telemetry text           |
| `--sans`       | Sans font stack for labels and body text                  |

Omitting `--glow`/`--grid`/`--input-*`/`--on-accent` inherits the NEXUS dark
defaults. Every surface in the panel — cards, tiles, inputs, toasts, charts,
and all accent tints — derives from these variables via `color-mix()`, so a
theme never leaves hardcoded green behind. Font values may be any font-family
stack such as `"Inter", "Segoe UI", sans-serif`.

## Uploading a custom theme

1. Open the panel → **SYSTEM → Display Access**.
2. Choose your `.json` file under **Custom Theme**.
3. On success the theme is applied immediately, appears in the Theme picker
   as `<NAME> (CUSTOM)`, and persists across sessions (stored in the browser's
   local storage, shared across all printers).

Invalid files are rejected with a message naming every problem found, e.g.
`Theme rejected: missing required variable "--red"; "--cyan" has an invalid
value`. No partial theme is ever applied.

## Built-in themes

| Theme            | Character                                        |
| ---------------- | ------------------------------------------------ |
| NEXUS DARK       | Default. Fluorescent green on near-black         |
| MIDNIGHT OPS     | Deep navy ops-console, cyan and green accents    |
| EMBER FORGE      | Industrial dark amber/orange                     |
| CARBON           | Neutral graphite, single restrained blue accent  |
| SOLARIZED DARK   | Classic Solarized base03 palette                 |
| SOLARIZED LIGHT  | Solarized base3 — light professional             |
| VIOLET GRID      | Synthwave purple                                 |
| ARCTIC           | Ice-blue light theme, dark text                  |
| STEALTH          | Ultra-low-light monochrome for dark rooms        |
| CLINICAL         | High-legibility light lab theme                  |

`DAYLIGHT`, `HIGH CONTRAST`, and `FOLLOW HOME ASSISTANT` remain available as
accessibility/system modes alongside the palette themes.

## Building a theme — tips

- Dark backgrounds with a saturated `--line-hi` suit the console aesthetic.
- Keep `--text`/`--bg` contrast at or above WCAG AA (4.5:1) so telemetry stays
  readable; check `--muted` against `--panel` too (3:1 minimum).
- `--green` and `--red` carry status meaning (ok vs. fault) — keep them
  visually distinct from each other and from `--amber`.
- Light themes look best with a subtle dark-tinted `--grid`
  (e.g. `rgba(70, 100, 125, 0.08)`) and a soft `--glow`.
- The colour-blind-safe palette toggle still applies on top of any theme and
  remaps the status colours automatically.
