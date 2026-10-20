# NEXUS Klipper Macro Suite

Printer-side macros that unlock advanced panel features. Install **after the
current print finishes** — editing `printer.cfg` requires a Klipper restart,
which aborts any job in progress.

## Install

1. Save the macro blocks below as `nexus_macros.cfg` next to `printer.cfg`
   (same folder Moonraker exposes, usually `~/printer_data/config/`).
2. Add one line to the top of `printer.cfg`:

   ```ini
   [include nexus_macros.cfg]
   ```

3. Restart Klipper (host action or `FIRMWARE_RESTART` after the printer is idle).
4. Verify each macro appears in the panel's macro/console lists.

## Prerequisites

- `[pause_resume]` must exist in your config for `RESUME` (most installs have it).
- `[virtual_sdcard]`, `[bed_mesh]`, and `[gcode_macro]` support are standard.
- Macros emit `RESPOND MSG="NEXUS_*"` lines. Moonraker records these in
  `server.gcode_store`, so the panel console and feature parsers can read them.
  No extra setup is needed — structured markers appear as `// NEXUS_*` lines.

## Slicer hooks (optional but recommended)

In OrcaSlicer → Printer Settings → Machine G-code, add:

| Slot | G-code |
|------|--------|
| Start G-code (after homing/heat) | `NEXUS_CHECKPOINT` |
| Layer change G-code | `NEXUS_LAYER_MARK L={layer_num+1}` |
| Layer change G-code (timelapse mode only) | `NEXUS_LAYER_PHOTO` |
| End G-code | `NEXUS_POST_REPORT` |
| Pause macro (slicer pause) | `NEXUS_PARK_PHOTO` |

`{layer_num+1}` is OrcaSlicer's variable for the current layer index.

---

## Macros

### `NEXUS_LAYER_MARK` — precise layer event markers

Emits a machine-readable marker per layer. The panel uses it for exact layer
counts even when `SET_PRINT_STATS_INFO` is not configured, and to trigger
timelapse captures on true layer boundaries instead of inferred Z changes.

```ini
[gcode_macro NEXUS_LAYER_MARK]
description: Emit a structured layer marker consumed by the NEXUS panel
gcode:
    RESPOND MSG="NEXUS_LAYER L={params.L|default(0)}"
```

### `NEXUS_LAYER_PHOTO` — clean layer timelapse frames

Parks the toolhead briefly at a fixed position so every layer photo shows the
model, not the nozzle. `SAVE/RESTORE_GCODE_STATE` preserves feed rate,
absolute/relative modes, and position. Tune `park_x`/`park_y` to a corner that
clears your gantry and frames the print for the camera.

```ini
[gcode_macro NEXUS_LAYER_PHOTO]
description: Park the toolhead briefly for a clean layer snapshot
variable_park_x: 10
variable_park_y: 210
variable_z_hop: 5
variable_dwell_ms: 400
gcode:
    {% set X = params.X|default(park_x)|float %}
    {% set Y = params.Y|default(park_y)|float %}
    {% set ZHOP = params.ZHOP|default(z_hop)|float %}
    {% set DWELL = params.DWELL|default(dwell_ms)|int %}
    SAVE_GCODE_STATE NAME=nexus_photo
    G91
    G1 Z{ZHOP} F900
    G90
    G1 X{X} Y{Y} F9000
    M400
    G4 P{DWELL}
    RESPOND MSG="NEXUS_PHOTO_READY"
    RESTORE_GCODE_STATE NAME=nexus_photo
```

Only enable this in the slicer **or** trigger it manually — a park move on
every layer adds several seconds per layer to the print.

### `NEXUS_PARK_PHOTO` — posed shot for completion cards

Longer dwell than the layer version; used for the finish photo and incident
snapshots. Does not restore position (meant for paused/finished states).

```ini
[gcode_macro NEXUS_PARK_PHOTO]
description: Move the toolhead to a clean photo position
variable_park_x: 10
variable_park_y: 210
variable_z_hop: 20
gcode:
    {% set X = params.X|default(park_x)|float %}
    {% set Y = params.Y|default(park_y)|float %}
    {% set ZHOP = params.ZHOP|default(z_hop)|float %}
    SAVE_GCODE_STATE NAME=nexus_park
    G91
    G1 Z{ZHOP} F900
    G90
    G1 X{X} Y{Y} F9000
    M400
    G4 P600
    RESPOND MSG="NEXUS_PHOTO_READY"
    RESTORE_GCODE_STATE NAME=nexus_park
```

### `NEXUS_HEAT_SOAK` — consistent first layer via thermal dwell

Heats the bed (and optionally the nozzle), then soaks until heat has spread
evenly through the bed plate. Cold-start prints benefit most; call it at the
top of your Start G-code or from the panel before a print.

```ini
[gcode_macro NEXUS_HEAT_SOAK]
description: Preheat then dwell so the bed is thermally saturated
variable_bed: 60
variable_nozzle: 0
variable_soak_s: 180
gcode:
    {% set BED = params.BED|default(bed)|int %}
    {% set NOZ = params.NOZZLE|default(nozzle)|int %}
    {% set SOAK = params.SOAK|default(soak_s)|int %}
    RESPOND MSG="NEXUS_HEAT_SOAK start bed={BED} nozzle={NOZ} soak={SOAK}s"
    M140 S{BED}
    {% if NOZ > 0 %}
    M104 S{NOZ}
    {% endif %}
    M190 S{BED}
    {% if NOZ > 0 %}
    M109 S{NOZ}
    {% endif %}
    G4 P{SOAK * 1000}
    RESPOND MSG="NEXUS_HEAT_SOAK done bed={printer.heater_bed.temperature|round(1)} nozzle={printer.extruder.temperature|round(1)}"
```

### `NEXUS_PRIME_PURGE` — position-aware purge line

Purges near a chosen corner (or the first print position the slicer passes in
via `X`/`Y` params) instead of a fixed skirt location.

```ini
[gcode_macro NEXUS_PRIME_PURGE]
description: Purge a short line near a chosen position
variable_len: 30
variable_x: 20
variable_y: 20
gcode:
    {% set X = params.X|default(x)|float %}
    {% set Y = params.Y|default(y)|float %}
    {% set LEN = params.LEN|default(len)|float %}
    G90
    G1 X{X} Y{Y} F6000
    G1 Z0.3 F600
    M83
    G1 E{LEN} F300
    G92 E0
    G1 Z2 F600
    RESPOND MSG="NEXUS_PRIME_PURGE done x={X} y={Y} len={LEN}"
```

### `NEXUS_FILAMENT_CHECK` — pre-print extruder sanity test

Extrudes a small amount and reports state; the panel's pre-flight check pairs
it with the motion sensor (if fitted) to catch a jam before committing to a
long print.

```ini
[gcode_macro NEXUS_FILAMENT_CHECK]
description: Extrude a test length and report extruder state
variable_purge_len: 15
variable_extruder_min_temp: 170
gcode:
    {% set LEN = params.LEN|default(purge_len)|float %}
    {% if printer.extruder.temperature < extruder_min_temp %}
        RESPOND MSG="NEXUS_FILAMENT_CHECK blocked: nozzle {printer.extruder.temperature|round(1)}C below {extruder_min_temp}C"
    {% else %}
        M83
        G1 E{LEN} F240
        M400
        G92 E0
        RESPOND MSG="NEXUS_FILAMENT_CHECK done purge={LEN}mm temp={printer.extruder.temperature|round(1)}C"
    {% endif %}
```

### `NEXUS_SAFE_RESUME` — guarded resume

Refuses to resume onto a cold print. If your slicer pause parks the head with
heaters on, this is a second safety net for power glitches and long pauses.

```ini
[gcode_macro NEXUS_SAFE_RESUME]
description: Resume only if heaters are still at print temperature
variable_min_extruder: 170
variable_min_bed: 40
gcode:
    {% if printer.extruder.target < min_extruder %}
        RESPOND MSG="NEXUS_SAFE_RESUME blocked: nozzle target {printer.extruder.target|round(0)}C"
    {% elif printer.extruder.temperature < min_extruder - 10 %}
        RESPOND MSG="NEXUS_SAFE_RESUME blocked: nozzle at {printer.extruder.temperature|round(1)}C, reheating"
        M109 S{printer.extruder.target|round(0)}
        RESUME
    {% elif printer.heater_bed.target < min_bed %}
        RESPOND MSG="NEXUS_SAFE_RESUME blocked: bed target {printer.heater_bed.target|round(0)}C"
    {% else %}
        RESUME
        RESPOND MSG="NEXUS_SAFE_RESUME resumed"
    {% endif %}
```

### `NEXUS_CHECKPOINT` — recovery breadcrumb

Logs position, file, and progress. Call it from Start G-code and (optionally)
every layer. After a power loss or Klipper restart the panel reads the last
checkpoint from `server.gcode_store` to show where the job died.

```ini
[gcode_macro NEXUS_CHECKPOINT]
description: Log a recovery breadcrumb line for the panel
gcode:
    RESPOND MSG="NEXUS_CHECKPOINT pos={printer.toolhead.position.x|round(2)},{printer.toolhead.position.y|round(2)},{printer.toolhead.position.z|round(3)} file={printer.virtual_sdcard.file_path} progress={printer.virtual_sdcard.progress|round(4)}"
```

Note: this records state only. Full power-loss recovery additionally needs
`SDCARD_RESET_FILE` workflows; the checkpoint gives the panel enough context
to display and gate them.

### `NEXUS_POST_REPORT` — structured completion summary

Emits a machine-parseable end-of-print line the panel archives into its
print history card (actual vs estimated time, filament used, final state).

```ini
[gcode_macro NEXUS_POST_REPORT]
description: Emit a structured end-of-print summary for the panel
gcode:
    RESPOND MSG="NEXUS_REPORT file={printer.print_stats.filename} state={printer.print_stats.state} duration={printer.print_stats.print_duration|round(0)}s total={printer.print_stats.total_duration|round(0)}s filament={printer.print_stats.filament_used|round(1)}mm"
```

### `NEXUS_QUIET_FAN` — quiet-hours fan cap

One-shot cap on the part-cooling fan for quiet hours. Note: subsequent print
G-code `M106`/`M107` commands can override it — call it at layer change from
the slicer if you need a persistent cap, or accept it as a start-of-print cap.

```ini
[gcode_macro NEXUS_QUIET_FAN]
description: Cap the part cooling fan speed for quiet operation
variable_cap: 40
gcode:
    {% set CAP = params.CAP|default(cap)|int %}
    {% if CAP < 0 %}{% set CAP = 0 %}{% endif %}
    {% if CAP > 100 %}{% set CAP = 100 %}{% endif %}
    M106 S{CAP * 255 // 100}
    RESPOND MSG="NEXUS_QUIET_FAN cap={CAP}%"
```

### `NEXUS_MESH_AUDIT` — bed mesh decay breadcrumb

Reports the active mesh profile and min/max offsets. The panel's decay
tracker compares consecutive audits to flag a drifting or sagging bed before
first layers start failing.

```ini
[gcode_macro NEXUS_MESH_AUDIT]
description: Report active bed mesh stats for decay tracking
gcode:
    RESPOND MSG="NEXUS_MESH profile={printer.bed_mesh.profile_name} count={printer.bed_mesh.probe_count} min={printer.bed_mesh.mesh_min} max={printer.bed_mesh.mesh_max}"
```

Call manually, from Start G-code after homing, or let the panel request it.

---

## Panel consumption map

| Macro output | Consumed by |
|--------------|-------------|
| `NEXUS_LAYER L=` | Layer counter, timelapse triggers, replay sync |
| `NEXUS_PHOTO_READY` | Camera snapshot orchestration |
| `NEXUS_HEAT_SOAK` | Pre-flight card, thermal sentinel baseline |
| `NEXUS_FILAMENT_CHECK` | Pre-flight go/no-go |
| `NEXUS_SAFE_RESUME` | Resume gating in Job Control |
| `NEXUS_CHECKPOINT` | Power-loss recovery card |
| `NEXUS_REPORT` | History/forensics entries |
| `NEXUS_QUIET_FAN` | Quiet-hours automation |
| `NEXUS_MESH` | Bed mesh decay tracker |
| `NEXUS_PRIME_PURGE` | Print-start pipeline |
