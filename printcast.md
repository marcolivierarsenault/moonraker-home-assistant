# PRINTCAST — Predictive Print Forecasting

**Status:** design-complete, ready for implementation
**Category created:** predictive print operations — forecasting outcomes *before* a job starts, instead of monitoring it after.
**New terms coined:** Printcast, Printability Index, Filament Hydration Dose, Spool Saturation, Mass Ledger, Extrusion Debt.

Every 3D printing tool today is reactive: status displays, and failure alerts that
fire *after* damage starts. Printcast answers the question users actually ask
before pressing print — **"is this going to work?"** — as a weather-style forecast
with a named score, named risk factors, and a top recommendation that recovers the
most points.

```
◈ PRINTCAST — 01_MAIN_BODY_PETG.gcode
  PRINTABILITY: 74/100 — PROCEED WITH CAUTION
  ├ −12  spool saturation 62% (PETG threshold)
  ├ −10  bed mesh 11 days old
  ├ −6   this file has failed 1 of 3 attempts
  └ ambient 21 °C — inside PETG envelope ✓
  RECOMMENDATION: re-probe bed mesh or dry spool → +12 pts
```

---

## 1. Three new measurements (the engine)

### 1.1 Filament Hydration Dose → Spool Saturation

No mainstream tool tracks how much moisture a spool has absorbed. We do.

- **Model:** while a spool is the *active* Spoolman spool, it accrues
  `dose += max(0, RH% − 40) × Δt_hours` every analyze cycle. Below 40 % RH a
  spool is effectively in dry storage; only the excess counts.
- **Source precedence:** `CONF_OPTION_HUMIDITY_SENSOR` (new option, HA humidity
  entity) → fallback: any Klipper env sensor already reporting `humidity` in
  status (bme280/sht3x/aht10/htu21d — `sensor.py` line ~704 proves these exist)
  → else tracking disabled, dose metric `None`, zero penalty.
- **Saturation %** = `dose / material_threshold × 100`. Thresholds (RH·hrs
  above 40 %, calibration-needed starting values documented as such):

  | Material | Threshold | Hygroscopicity |
  |---|---|---|
  | PA/NYLON, PC, PVA | 40 | extreme |
  | TPU, PETG | 80 | high |
  | ABS, ASA | 120 | medium |
  | PLA, default | 160 | low |

  Add a `moisture` key to `MATERIAL_PROFILES` + default fallback.
- **Per-spool persistence:** `spool_dose` dict keyed by `spool_id`
  `{dose_rh_h, material, last_dry_iso, untracked}` — bounded to 24 spools in the
  analyzer Store. Swapping spools keeps each spool's dose (Spoolman already
  reports the active `spool_id`). A spool_id never seen starts at dose 0 with
  `untracked: true` until one full day of samples accumulates.
- **Dry reset:** new button entity **"Mark Spool Dried"** — local-only
  `press_fn` calling `analyzer.printcast.mark_dried()`; sends **no** printer
  command (safe per printer-safety rules; it's bookkeeping). Panel gets a
  "MARK DRIED" chip too, routed through the same path.
- **Metrics:** `spool_hydration_dose_rh_h`, `spool_saturation_pct`,
  `humidity_pct` (source reading).
- **Finding:** severity `warn`, label `filament moisture risk`, when
  saturation > 70 % for a hygroscopic material and a print is queued/active.

### 1.2 Mass Ledger → Extrusion Debt

Reconciliation of declared vs. reported filament mass, per completed print.

- **Per completed print** (`state == "complete"`, `filament_total` known):
  `debt_pct = (filament_used_mm − filament_total_mm) / filament_total_mm × 100`.
- **Honest baseline:** completed prints legitimately report *more* than the
  slicer metadata (skirt, priming, purge). So the ledger learns a per-printer
  baseline EMA of `debt_pct`; the alarm signal is the **deviation from that
  learned baseline**, not from zero — a sudden −4 pt drop on an identical file
  is an under-extrusion signature (partial clog forming).
- **Cancelled/error prints excluded** (shortfall is expected there).
- **Storage:** `mass_ledger` deque of 30 records
  `{file, expected_mm, reported_mm, debt_pct, at}` + `extrusion_debt_ema`.
- **Metrics:** `extrusion_debt_pct` (EMA), `extrusion_debt_trend`,
  `mass_ledger_entries`.
- **Finding:** `extrusion drift` warn when EMA deviates > 4 pts below the
  learned baseline across ≥ 5 prints.

### 1.3 Printability Index — the forecast model

Additive risk model: `score = 100 − Σ penalties`, clamped [0, 100]. Every
penalty carries `{key, points, detail, remedy}` so the UI can name each factor
and pick the top recoverable recommendation.

| Factor | Penalty | Data source (already exists) |
|---|---|---|
| Klippy not ready / unreachable | NO-GO (−100) | `klippy_state`, coordinator.last_update_success |
| Spool shortfall for target file | NO-GO (−100) | `filament_total` vs `spool_remaining_mm` |
| Material mismatch file↔spool | −40 | `filament_type` vs `spool_material` |
| Spool saturation (hygroscopic) | up to −25 (`−0.25×sat%`) | §1.1 |
| Stale mesh (> MESH_FRESH_DAYS) | −10 | `preflight.mesh_fresh` |
| Mesh surface-drift finding active | −8 | findings |
| File history: prior faults | −8/fault kind, −6/failed attempt, cap −20 | `file_stats` |
| Ambient below material floor | −15 | `ambient_c` vs profile |
| Extrusion debt below baseline | up to −15 | §1.2 |
| Nozzle wear > 15 % | −8 | `nozzle_wear_pct` |
| Config changed < 24 h | −5 | `config_changed_at` |
| Active PSU-sag / driver-thermal finding | −10 each | findings |

**Verdicts:** ≥ 85 CLEAR · 60–84 CAUTION · 40–59 POOR · < 40 **or any NO-GO
factor** → NO-GO.

**Recommendation engine:** the factor with the largest recoverable points and a
remedy string becomes `top_recommendation` — "re-probe bed mesh → +10 pts".

---

## 2. Forecast triggers (when a forecast is produced)

1. **Continuous (idle):** `virtual_sdcard.file_path` is the *selected* file —
   the coordinator already subscribes to it (`__init__.py` line 673). While
   `print_stats.state == "standby"` and a file is selected, the forecast is
   recomputed every analyze cycle.
2. **On file select (the magic moment):** when `file_path` *changes* while
   idle → fire HA event `moonraker_printcast` with the full forecast payload →
   optional `notify_service`/TTS announcement: *"Printcast: 74, proceed with
   caution. Risks: spool saturation, stale mesh."* Deduped per
   `filename + verdict bucket`; only announced when score < 85 or worsened.
3. **Active print:** forecast switches to "in-flight" mode — score still
   computed but labeled "live"; twin-drift replaces the pre-print factors that
   no longer apply.
4. **Queue jobs:** each `queue_plan` entry gains a `printability` field — the
   queue view shows which jobs are safe to auto-run.
5. **On demand:** new GET endpoint `panel_printcast?filename=…` computes a
   forecast for *any* file in the browser (metadata fetched via
   `SERVER_FILES_METADATA`, same as `_queue_meta_updater`). File-browser rows
   get a score badge lazily on expand — bounded cost.

---

## 3. Data inventory — all verified present

| Need | Source | Status |
|---|---|---|
| Active spool id, weight, material, density | `spool_details` via `_spool_status_updater` | ✅ live |
| Filament cross-section math | `_spool_remaining_mm` density/diameter math | ✅ live |
| Selected filename | `virtual_sdcard.file_path` subscription | ✅ live |
| Per-file slicer metadata | `SERVER_FILES_METADATA` (`_queue_meta_updater`) | ✅ live |
| Ambient temp | `CONF_OPTION_AMBIENT_SENSOR` | ✅ live |
| Humidity | Klipper env sensors in status | ⚠️ optional; add HA option |
| File attempt history | `file_stats` | ✅ live |
| Mesh freshness/drift | `preflight.mesh_fresh`, mesh findings | ✅ live |
| Klippy state, PSU/driver findings | existing analysis | ✅ live |
| Notify service + TTS | `notify_service` option, `moonraker_print_event` bus pattern | ✅ live |
| Local-only button entities | `button.py` `press_fn` | ✅ pattern exists |

**Zero new hardware required.** Every input already flows through the
coordinator except an optional dedicated room-humidity sensor.

---

## 4. Implementation map (file by file)

| File | Change |
|---|---|
| `const.py` | `CONF_OPTION_HUMIDITY_SENSOR`; `SIGNAL_PRINTCAST = "moonraker_printcast"` |
| `config_flow.py` | humidity `EntitySelector(device_class=HUMIDITY)` |
| `translations/{en,es,fr}.json` | option label; issues `moisture_risk`, `extrusion_drift` |
| `analyzer.py` | instantiate `MoonrakerPrintcast`; call per cycle; store keys `spool_dose`, `mass_ledger`, `extrusion_debt_ema`, `printcast_last_file`; moisture keys in `MATERIAL_PROFILES` |
| `printcast.py` **(new)** | `MoonrakerPrintcast` class: dose tracker, mass ledger, scoring model, forecast assembly, `mark_dried()`, `forecast_for_file(filename, meta)`, event firing. Separate module keeps analyzer.py reviewable — same Store via a `state` dict handed in/out |
| `sensor.py` | `Printability Index` (%), `Printcast Verdict` (text + factor attrs), `Spool Saturation` (%), `Extrusion Debt` (%) |
| `button.py` | "Mark Spool Dried" — local bookkeeping, no printer command |
| `panel.py` | `payload["printcast"]`; `MoonrakerPanelPrintcastView` GET endpoint |
| `panel.html` | PRINTCAST card markup (score dial, verdict chip, factor list, dose gauge, ledger line, MARK DRIED chip) |
| `panel_client.js` | `renderPrintcast()`, file-row badges, mark-dried call, event toast on `moonraker_printcast` |
| `docs/printcast.rst` **(new)** | concepts, model weights, calibration notes, setup; linked from `index.rst` |
| `tests/test_printcast.py` **(new)** | full coverage of dose, ledger, model, triggers, store round-trip |
| `tests/{test_sensor,test_panel,test_button}.py` | new entity/payload coverage |
| `tests/panel_ui.test.cjs` | card render, badges, mark-dried, verdict coloring |

---

## 5. Safety & resource rules (inherited)

- **Passive only.** Printcast reads coordinator data; the only state it mutates
  is its own Store records. `mark_dried` touches no printer API.
- **Bounded:** 24 spool records, 30 ledger entries, one forecast dict —
  trivially small.
- **Graceful absence:** no humidity source → dose `None`, no penalty. No
  Spoolman → saturation/shortfall factors skipped, not penalized. No metadata →
  forecast limited to machine-side factors with an explicit `partial: true`
  flag so the UI can say "partial forecast".
- **Corrupt store** → ignored, re-learned (existing analyzer pattern).
- **No mutating commands anywhere** in the forecast path — verified by the
  code-review rule for passive paths.

---

## 6. Phases

1. **P1 Engine:** `printcast.py` — dose tracker, mass ledger, scoring model,
   `MATERIAL_PROFILES.moisture`, store persistence, metrics/findings.
2. **P2 Plumbing:** humidity option (const/config_flow/translations),
   sensors, mark-dried button, file-select trigger + `moonraker_printcast`
   event + notify/TTS.
3. **P3 Panel:** payload, PRINTCAST card, `panel_printcast` endpoint,
   file badges, mark-dried chip, event toast.
4. **P4 Queue integration:** per-job `printability` in `queue_plan` + fleet
   router reasons.
5. **P5 Validation & docs:** `test_printcast.py` to 100 %, UI tests, ruff,
   `docs/printcast.rst`, strict suite, commit, deploy (restart required —
   ask first per stored rule).

---

## 7. Open calibration notes (documented, not blockers)

- Hydration thresholds are physically-motivated starting values; expose them
  as constants at module top so real-world feedback can tune them. The
  saturation %, not raw dose, drives the penalty — thresholds tune per
  material without touching the model.
- Extrusion-debt baseline needs ≥ 5 completed prints before the drift finding
  arms; until then the metric reports but never alarms (`armed: false`).
- The forecast is probabilistic guidance, not a guarantee — the verdict
  labels deliberately read like weather language, and `partial` forecasts are
  labeled as such.
