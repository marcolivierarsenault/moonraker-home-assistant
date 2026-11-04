# NEXUS Enhancement Plan C — 30 findings

Builds on `Enhancement -A.md` and `Enhancement -B.md` (Waves 1–10 shipped).
Plans A and B delivered server-side analysis, mesh tram/surface decomposition,
vision checks, recovery checkpoints, queue scheduling, themes, and panel polish.
Plan C targets deeper print science, fleet intelligence, and features that are
rare or absent in current Klipper/Moonraker tooling.

## A. Print-science diagnostics

1. **Layer-time periodicity / Z-banding detection** — track per-layer durations
   from `display_status` + position deltas; a repeating layer-time signature at
   leadscrew-pitch Z spacing means Z-banding; report the dominant period in mm.
2. **VFA / ringing estimation** — correlate `motion_report` velocity segments
   with measured accelerometer spectra (Klipper `adxl345` status when present);
   flag frequencies landing in the input-shaper notch.
3. **Input-shaper drift watch** — periodically re-read the last shaper
   calibration frequencies from `configfile.settings`; warn when mechanical
   resonance shifts (loose belts, worn bearings) vs. the saved baseline.
4. **Pressure-advance consistency** — monitor `motion_report.live_extruder_velocity`
   reversals during direction changes; growing extrusion stutter at constant PA
   suggests nozzle wear or partial clogs.
5. **First-layer flow uniformity** — during layer 1, sample extrusion volume per
   XY region via toolpath + extrusion counters; uneven first-layer flow maps to
   bed-mesh blind spots and feeds back into the mesh health card.
6. **Thermistor drift detection** — compare heater temperature vs. power draw at
   steady state over weeks; a slowly rising power-for-temperature ratio means
   thermistor decay or heater cartridge aging.
7. **Nozzle wear index** — trend volumetric-flow headroom shrinkage across
   prints of the same material; a falling ceiling on identical G-code profiles
   implies nozzle enlargement or internal wear.
8. **Stepper-driver thermal prediction** — extrapolate MCU/TMC temperature
   slope during high-velocity phases; warn before thermal shutdown instead of
   after, with the projected crossing time.
9. **PSU / voltage sag watch** — subscribe `mcu` analog stats where available;
   dip patterns during heat-up = undersized PSU or failing supply.
10. **Extruder skip acoustic heuristic** — sudden `live_extruder_velocity`
    stalls at high commanded feed rates logged as probable skip events, counted
    per print for a grind-skip score.

## B. Per-print quality science

11. **Golden-run twin comparison** — on repeat prints of the same file, overlay
    live telemetry (temps, flow, layer times, fan) against the best historical
    run; deviation percentage becomes a live "twin drift" metric and finding.
12. **Per-print quality scorecard** — combine fault count, estimate accuracy,
    twin drift, thermal stability, and retransmit rate into an A–F grade stored
    in print history; farm-wide grade trend becomes a sensor.
13. **File success-rate memory** — per-G-code-file history: attempts,
    completions, cancels, faults. Warn at job start: "this file failed 2 of 3
    times — last fault: extrusion stall at layer 114."
14. **Failure forensics snapshot** — when a print fails or cancels, capture the
    last N minutes of full telemetry + findings + console tail into the print
    record for postmortem review in the history view.
15. **Cooling/warp correlation** — correlate ambient/chamber temperature at
    print start with historical warp-related failures per material; recommend
    chamber pre-heat or enclosure door state before high-shrink materials.
16. **Estimate-drift learning per file** — learned slicer-estimate correction
    already exists globally; refine it per file+material so repeat prints get
    near-exact ETAs and the farm scheduler can trust them.

## C. Fleet & job intelligence

17. **Multi-printer job router** — score queued jobs across all configured
    printers by fit: loaded material match, spool sufficiency, bed size,
    printer health grade, current queue depth; recommend (or with permission,
    apply) the best target printer per job.
18. **Pre-flight checklist gate** — before `start_print`, run a passive
    checklist: spool fits, mesh snapshot fresh, Klippy connected, nozzle at
    room temp, camera reachable, previous job cleaned (optional camera check);
    surface a GO/NO-GO summary with the blocking reason.
19. **Farm utilization & OEE** — per-printer uptime, print-vs-idle ratio,
    failure rate, and throughput rolled into fleet sensors + a farm summary
    strip on the dashboard.
20. **Ambient-aware scheduler** — hold queue starts until chamber reaches a
    material-appropriate temperature, or delay starts past quiet hours; reuse
    the TTS quiet-hours windows.
21. **Spool-inventory allocator** — reserve filament against queued jobs so a
    shared spool can't be oversubscribed across printers; flag queue jobs that
    would overrun the reservation.

## D. Panel & UX upgrades

22. **Exclude-object control** — Klipper `exclude_object` is already reported;
    render live object list with per-object cancel buttons + a minimap of
    object positions for selective cancellation.
23. **Guided tramming wizard** — step-by-step corner adjustment flow: pick a
    corner, panel shows its live offset shrinking to zero as you turn the
    screw, then moves to the next corner; finishes with an auto re-mesh offer.
24. **G-code file diff** — compare two versions of a sliced file (or a file vs.
    its previous print): slicer changes, estimated time delta, filament delta,
    bounding-box shift; catches "re-sliced and broke it" mistakes.
25. **Installable PWA** — manifest + service worker so the panel installs to a
    phone home screen with its own icon and full-screen chrome.
26. **Voice control via HA Assist** — expose print status as Assist intents
    ("how long left on the Voron", "pause the print") using `intent` handlers;
    mutating intents confirm before acting.
27. **Export timelapse to video** — encode captured frames server-side
    (ffmpeg on host or browser-side WebCodecs) into mp4/webm with a share link
    in the completion card.
28. **Print-photo AI captioning** — reuse the `ai_task` pipeline to generate a
    one-line description of the completion photo ("benchy intact, minor stringing")
    attached to the history record and notification.

## E. Integration & ecosystem

29. **printer.cfg drift tracking** — periodically hash `configfile.config`;
    snapshot and diff Klipper config over time so silent slicer/start-macro
    edits are visible in history (and can power a "what changed since it last
    worked" view).
30. **OctoEverywhere/Obico-style remote relay option** — document + harden a
    secure remote-access path: the panel already proxies through HA, so
    exposing it via `hass` ingress/Nabu Casa gives authenticated remote control
    without a third-party plugin on the printer.
