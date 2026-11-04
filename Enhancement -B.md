# NEXUS Enhancement Plan B — 30 items

Builds on `Enhancement -A.md` (Waves 1–3 complete). Key gap: every Wave 1–3
monitor runs only while a browser has the panel open and stores state in that
browser's localStorage. Plan B moves intelligence into Home Assistant, adds
native HA surfaces, and hardens the panel.

## A. Backend intelligence & native HA integration

1. **Server-side analyzer** — move thermal sentinel, flow headroom, mesh drift,
   ghost-print guard (Plan A #10) and console-health decoding into a
   coordinator-side analyzer fed by the existing websocket stream.
2. **Persistent server-side state** — mesh baselines, maintenance ledger,
   energy totals and preferences in HA `Store` instead of localStorage.
3. **Analytics as HA entities** — volumetric flow, flow headroom %, mesh RMS
   drift, kWh/print, print cost, retransmit trend, maintenance-due sensor.
4. **Repairs issues** — re-level suggested, service due, PID oscillation,
   update available, printer unreachable > 24h.
5. **Event entities** — print start / layer / pause / complete / error / runout.
6. **Update entities** — from `machine.update.status`; admin-only install.
7. **Diagnostics download** — `diagnostics.py` with token redaction.
8. **Per-print history record** — duration, filament, kWh, cost, estimate
   accuracy, faults, completion photo.

## B. Predictive failure prevention

9. Camera-frame spaghetti detection (optional local model) + auto-pause window.
10. First-layer inspection against the rendered layer-1 toolpath.
11. Heater baseline learning — warn on heat-up time degradation.
12. Continuous spool run-out prediction with layer-boundary pause offer.
13. Ambient environment watch via HA temperature / humidity sensors.
14. Input-shaper limit cross-check against sliced speeds / accelerations.

## C. Workflow & automation

15. Smart queue scheduling (quiet hours, tariff, spool changes).
16. "Print when ready" HA automation blueprint.
17. Actionable companion-app notifications (admin-gated).
18. Auto power-off after cooldown with queue awareness.
19. Recovery checkpoint library (resume from layer N with reviewable G-code).
20. Material profiles matched to file metadata and active spool.

## D. Panel quality & performance

21. Split `panel_client.js` into ES modules, lazy per page.
22. Web Worker toolpath parsing + WebGL / OffscreenCanvas rendering.
23. IndexedDB parsed-toolpath cache keyed by path + mtime.
24. **Theming + mobile layout** — light / high-contrast / follow-HA themes,
    touch-first phone layout.
25. **Accessibility** — keyboard navigation, ARIA live regions, focus styles,
    colour-blind-safe palette, labelled canvases.
26. **Panel translations** — en / es / fr matching the integration's
    translations, auto-selected from the HA user language.

## E. Reliability, security & engineering

27. Role-based permissions (viewer / operator / admin) + mutation audit log.
28. Playwright end-to-end tests against a mock Moonraker.
29. Recorded-traffic replay harness for analyzer false-positive tuning.
30. Resilience / load tests with an enforced API-calls-per-minute budget.

## Implementation order

| Wave | Items | Focus |
|------|-------|-------|
| UI Polish | 24, 25, 26 | Requested first |
| 5 | 1, 2, 3, 7, 8 | Backend foundation |
| 6 | 4, 5, 6, 17, 18 | Native HA surfaces |
| 7 | 21, 22, 23, 28 | Panel architecture + browser tests |
| 8 | 11, 12, 13, 14, 20 | Predictive maintenance |
| 9 | 9, 10, 19, 29 | Vision + recovery |
| 10 | 15, 16, 27, 30 | Scheduling, permissions, hardening |

Every item ships with regression tests; the 100% coverage gate stays.
