# PRINTCAST — Implementation Todo

Companion to `printcast.md`. Check items off as phases complete.
Rules: passive-only paths, bounded storage, 100 % test coverage, no printer
commands from forecast logic, HA restart requires explicit user approval.

## P1 — Engine (`printcast.py`)

- [ ] Add `moisture` key to `MATERIAL_PROFILES` + default threshold map
      (PA/PC/PVA 40 · TPU/PETG 80 · ABS/ASA 120 · PLA/default 160 RH·hrs)
- [ ] `MoonrakerPrintcast` class init'd by analyzer; handed coordinator, hass,
      options, and a `state` dict slice for persistence
- [ ] Humidity source resolver: option sensor → Klipper env sensor
      (`humidity` key in status objects) → `None`
- [ ] Hydration dose integrator: `dose += max(0, RH−40)×Δh` each cycle,
      active spool only, per-spool records keyed by `spool_id` (bound 24)
- [ ] Saturation % = dose / material threshold; `untracked` flag for
      newly-seen spool ids (< 24 h of samples)
- [ ] `mark_dried()` — zero dose + stamp `last_dry_iso` for active spool
- [ ] Metrics: `spool_hydration_dose_rh_h`, `spool_saturation_pct`,
      `humidity_pct`, `extrusion_debt_pct`, `extrusion_debt_trend`,
      `mass_ledger_entries`, `printability_score`, `printability_verdict`,
      `printability_factors`, `printability_recommendation`
- [ ] Mass ledger: on `complete` prints with `filament_total` known, append
      `{file, expected_mm, reported_mm, debt_pct, at}` (deque 30); skip
      cancelled/error
- [ ] Debt EMA vs learned baseline; finding `extrusion drift` at >4 pt drop,
      armed only after ≥5 prints
- [ ] Finding `filament moisture risk` when saturation >70 % + hygroscopic +
      job active/queued
- [ ] Scoring model: all 12 factors from plan §1.3 with `{key, points,
      detail, remedy}`; NO-GO overrides; verdict buckets
      (≥85 CLEAR / 60 CAUTION / 40 POOR / NO-GO)
- [ ] `top_recommendation` = factor with max recoverable points + remedy text
- [ ] `forecast_for_file(filename, meta)` — per-file forecast for on-demand
      endpoint and queue entries; `partial: true` when metadata missing
- [ ] Store persistence: `spool_dose`, `mass_ledger`, `extrusion_debt_ema`,
      `printcast_last_file` — load/save/mark_dirty via analyzer Store;
      corrupt entries ignored

## P2 — Plumbing

- [ ] `const.py`: `CONF_OPTION_HUMIDITY_SENSOR`, `SIGNAL_PRINTCAST`
- [ ] `config_flow.py`: humidity `EntitySelector` (device_class HUMIDITY)
- [ ] `translations/{en,es,fr}.json`: `humidity_sensor` option label;
      issues `moisture_risk`, `extrusion_drift`
- [ ] `sensor.py`: Printability Index (%), Printcast Verdict (text + attrs
      for factors/recommendation), Spool Saturation (%), Extrusion Debt (%)
- [ ] `button.py`: "Mark Spool Dried" → `analyzer.printcast.mark_dried()`
      (local only — no Moonraker call; regression test asserting no API call)
- [ ] File-select trigger: detect `virtual_sdcard.file_path` change while
      `print_stats.state == "standby"` → compute forecast → `hass.bus`
      `advance_moonraker_control_printcast` event with payload
- [ ] Notify/TTS on file select when score <85 or verdict worsened; dedupe
      per `filename + verdict bucket`
- [ ] Live mode: while printing, forecast relabeled "live" — twin-drift
      factors replace pre-print-only factors

## P3 — Panel

- [ ] `panel.py`: `payload["printcast"]` = current forecast dict
- [ ] `panel.py`: `MoonrakerPanelPrintcastView` GET
      `/api/advance_moonraker_control/panel_printcast?filename=` — computes per-file forecast
      via `SERVER_FILES_METADATA`
- [ ] `panel.html`: PRINTCAST card — score dial (theme vars), verdict chip,
      factor list w/ point deltas, top recommendation, humidity dose gauge,
      mass-ledger line, MARK DRIED chip, `partial` badge
- [ ] `panel_client.js`: `renderPrintcast()` in refresh cycle; per-file score
      badge in G-code browser (lazy fetch on expand); mark-dried call;
      `advance_moonraker_control_printcast` event → toast + optional TTS
- [ ] Theme compliance: all new colors via `var(--*)`, no literals

## P4 — Queue & fleet

- [ ] `queue_plan` entries gain `printability` score
- [ ] Fleet router: printcast score folded into per-printer reasons
- [ ] Queue view shows per-job forecast badge

## P5 — Validation, docs, ship

- [ ] `tests/test_printcast.py`: dose accrual, dry reset, spool swap keeps
      dose, untracked flag, humidity fallback chain, ledger math, baseline
      arming, drift finding, all 12 scoring factors + NO-GO overrides,
      verdict boundaries, partial forecast, file-select event, notify dedupe,
      store round-trip + corrupt data, live-mode relabel
- [ ] Sensor/button/panel/endpoint tests to 100 % coverage
- [ ] `tests/panel_ui.test.cjs`: card render, verdict colors, badges,
      mark-dried, toast
- [ ] `docs/printcast.rst` + `index.rst` toctree; calibration notes §7
- [ ] `scripts/lint` clean; `scripts/test_strict` 100 %; `scripts/test_panel_ui`
- [ ] Commit logical chunks; deploy passive file copy; ask before HA restart
- [ ] Update `printcast.md` + this file with any calibration changes
