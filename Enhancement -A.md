# NEXUS Enhancement Plan — Batch A

Advanced upgrades for the Moonraker Home Assistant integration. One batch is
printer-side macros (`macros.md`); the other fourteen run inside this
integration. All work happens without touching the printer or restarting Home
Assistant while a print is active.

## Data sources already available

- Coordinator polling + Moonraker websocket status pushes (`notify_status_update`)
- Parsed G-code toolpath (positions, fractions, extrusion indices, bounds)
- `print_stats`, `virtual_sdcard`, `toolhead`, `gcode_move`, heaters, fans
- `server.gcode_store` console history + live responses
- `server.job_queue`, `server.history.totals`, `server.spoolman.status`
- `machine.device_power`, `machine.update.status`, webcam snapshots
- HA `window.hass` (states, services, notify, media players)

## Batch A items

### Phase 1 — Frontend only

1. **Layer-time analytics + honest ETA** — bucket parsed moves by Z and
   feedrate → per-layer time graph, slow-layer hotspots, corrected total ETA
   vs slicer estimate.
2. **Print replay mode** — scrub the toolpath slider and synced timelapse
   frames follow the matching layer; watch the finished object re-grow.
3. **Completion card v2** — webcam finish snapshot + slicer thumbnail,
   actual-vs-estimated accuracy, PRINT AGAIN (enqueue), CLEAR BED reminder.
4. **Quiet-hours queue gate** — hold `start_queue`/auto-advance while quiet
   hours are active; second press within a short window overrides.

### Phase 2 — Cross-source correlation

5. **Spool-aware pre-flight check** — file metadata vs Spoolman remaining,
   material match, model bounds vs bed size, ETA vs quiet hours → GO/NO-GO.
6. **Console health decoder** — parse console for `bytes_retransmit`, MCU
   warnings, shutdown reasons → System page health chips + trend.
7. **Maintenance ledger** — `history.totals` hours/filament + XY travel
   estimate → configurable countdowns (nozzle, PTFE, belts) with reset.
8. **Fleet overview strip** — all configured printers' state/progress/temps
   in a compact bar; click to switch.
9. **Bed-mesh decay tracking** — per-print mesh snapshot diff vs baseline
   RMS; "re-level suggested" + decay heatmap (pairs with `NEXUS_MESH_AUDIT`).

### Phase 3 — Detection & intelligence

10. **Ghost-print anomaly guard** — compare live `gcode_move` E position and
    toolhead motion against expected extrusion at current progress; flag
    sustained motion-without-extrusion (jam/air-print). Opt-in toggle,
    hysteresis to avoid false alarms.
11. **Thermal health sentinel** — heater duty ≥98% sustained while temp falls
    → detached heater/thermistor early warning; PID oscillation detection on
    the collected temp history.
12. **Volumetric flow headroom gauge** — E-velocity × filament area → mm³/s
    vs configured hotend max; gauge + sustained-saturation warning.
13. **Energy & cost accounting** — user-selected HA power sensor entity →
    live watts, kWh per print, cost per print at a configurable rate.
14. **Multi-camera synchronized timelapse** — capture every assigned camera
    each layer; per-camera or quad replay within the byte budget.

### Phase 4 — Printer side

15. **NEXUS macro suite** — `macros.md` (layer markers, photo parks, heat
    soak, filament check, safe resume, checkpoints, post report, quiet fan,
    mesh audit, prime purge). Install after the active print finishes.

## Implementation rules

- Every feature ships with `tests/panel_ui.test.cjs` coverage; backend
  changes add `tests/test_panel.py`/`tests/test_init.py` cases. The strict
  suite (`scripts/test_strict`) must stay at 100% coverage.
- No printer-mutating calls from passive/read paths; mutations stay behind
  explicit user actions.
- Nothing deploys to Home Assistant or restarts Core while a print runs.
- Panel changes must degrade cleanly when a data source is absent
  (no Spoolman, no power sensor, single printer, etc.).
