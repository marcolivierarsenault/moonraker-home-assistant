# NEXUS Control - Master Product, UX and Implementation Specification

Working concept: an original cybernetic, Borg-inspired Klipper/Moonraker touchscreen interface that looks sophisticated and intimidatingly capable while remaining readable, predictable and safe for daily 3D-printing work. The package intentionally avoids Star Trek logos, Borg insignia or copied screen graphics; it uses an original visual system built from dark graphite surfaces, emerald circuitry, cut-corner panel geometry and precise technical typography.

This document is written as an implementation contract for a coding AI or software team. When a visual choice and a safety/data-integrity rule conflict, the safety/data-integrity rule wins.

## 1. Product goals

- Feel like a purpose-built machine console, not a generic website reskinned green.

- Allow a specialist to understand the machine in seconds, yet keep advanced tuning and diagnostics one tap away.

- Use text and icons together. No important action is icon-only.

- Use live data and WebSocket subscriptions so the display feels alive without excessive polling.

- Expose only capabilities that actually exist on the connected Moonraker/Klipper system.

- Never silently alter printer.cfg, Moonraker configuration, heater safety, stepper current or persistent calibration values.

- Support touch-first operation on an x86-connected display as well as desktop/mouse use and normal browser access.

- Keep the whole app inside the viewport. The shell itself should not require browser-page scrolling; individual panels and lists may scroll internally.

- Scale from compact 800x480/1024x600 class panels to 1280x800, 1920x1080 and ultrawide operator displays.

- Support multiple printers without turning the interface into a fleet-management product. The currently selected printer is always obvious.



## 2. Non-negotiable UX principles

- Normal/active = emerald green, information = cyan, attention = amber, destructive/fault = red, unavailable = gray. Always pair color with text/icon state.

- Primary operational numbers use tabular numerals and are visually larger than labels.

- Dangerous operations are visually isolated. Cancel, delete, power-off, reboot and shutdown never sit next to ordinary navigation without separation.

- Emergency Stop remains globally reachable and is immediate. It does not use a delayed G-code queue path.

- A disconnected UI becomes read-only until live state is trustworthy again.

- Optional features disappear or explain their missing capability; the UI must never present a fake control that does nothing.

- Advanced pages can be dense, but controls still meet the minimum touch target.

- Every wizard has Cancel/Abort and a visible current step. Persistent writes show exactly what will change.



## 3. Global shell and navigation

The application shell is persistent. Only the control plane changes. This gives the interface the feeling of a physical console with selectable planes rather than a conventional website.

- Top status rail: product name, current printer selector, connection state, Klippy state, active print mini-status, warning count and clock.

- Left control-plane rail grouped as STATUS, CONTROL, CALIBRATE, AUTOMATE, OBSERVE and SYSTEM.

- Expanded sidebar shows icon + text. Compact mode shows a large glyph and short tooltip/long-press label.

- Selected plane has an illuminated emerald edge, slightly brighter panel background and an active glyph. Do not use a huge glow that reduces text contrast.

- Page header contains title, one-sentence purpose and local sub-tabs.

- Global quick drawer can be opened from top bar for Emergency Stop, Pause/Resume, Park, Home and Cooldown. It must not obscure an active critical alert.

- Persistent fault rail appears above page content when Klipper is shutdown/error, Moonraker reports failed components, or a high-priority announcement requires attention.



## 4. Visual language

The intended look is dark, cybernetic and machine-like. It should remind a viewer of a sophisticated collective/biomechanical computer without using protected franchise marks. The visual treatment must remain subordinate to operational clarity.

- Background: near-black green/graphite with extremely subtle grid/circuit texture.

- Panels: dark green-black with 1 px green structural border, cut/segmented corners where practical, and restrained inner glow.

- Accent: #00F28A emerald. Bright accent: #68FFC0. Cyan reserved for secondary sensor/information channels.

- Amber and red are reserved for state semantics, not decoration.

- Charts use thin luminous lines on quiet grids. Avoid filled neon areas behind dense text.

- Use ambient trace animations at low opacity. Reduced Motion turns them off.

- No blinking normal-state LEDs. Flashing is reserved for a user-configurable critical alarm and must stop when acknowledged.

- Icons are simple original line glyphs. Pair every important icon with text.

- Minimum normal touch target 48x48 px; preferred kiosk target 56x56 px.

- All numerical control widgets support direct keypad entry as well as sliders/chips where appropriate.



## 5. Responsive behavior

- 800-1023 px width: compact sidebar, one or two content columns, larger modal sheets, fewer simultaneous chart labels.

- 1024-1279 px: compact or expanded sidebar user choice, two content columns.

- 1280-1599 px: standard three-column dashboard grid.

- 1600+ px: three/four-column grid with camera/toolpath hero panels allowed to span two columns.

- Ultrawide: never stretch text lines excessively; increase columns/panel grouping instead.

- Viewport height is authoritative. The top rail and sidebar stay fixed. Data-heavy lists, terminal output and file lists scroll inside their own panel.

- Landscape is the primary control-panel orientation. Portrait remains functional but is not the primary visual target.



## 6. Live-data architecture

- Use Moonraker HTTP for discovery, one-off commands and transfers; use WebSocket JSON-RPC subscriptions for ongoing printer state.

- On connect: read server info, printer info, loaded printer objects, then build the subscription dynamically.

- Normalize partial WebSocket updates into one typed state store. Do not replace missing fields with zero; absence and zero are different states.

- Every state field tracks received timestamp and stale status.

- After disconnect: mark live values stale, stop controls that can change the printer, show RECONNECTING, then exponential backoff 1/2/4/8/16/30 seconds.

- If a limited polling fallback is needed, use a 1-2 second cadence for core print state rather than aggressive sub-second polling.

- Charts maintain a bounded client-side ring buffer. Long-term analytics use Moonraker history or an optional external data source rather than unbounded browser memory.

- Capability discovery is repeated after Klipper restart, firmware restart, config reload or version/config fingerprint change.



## 7. Control planes - complete specification

### 7.1 Dashboard

The landing plane. A user should understand printer state, active job, temperatures, camera, urgent warnings and the next useful action within two seconds.

Primary sub-tabs: Overview, Quick Controls, Alerts.

#### Layout

- Top-left: printer state and circular print progress.

- Top-center: current G-code model/toolpath preview and file identity.

- Top-right: selected live camera.

- Middle row: nozzle, bed, chamber, fan, speed and flow cards.

- Bottom-left: condensed movement widget.

- Bottom-center: favorite macros / quick actions.

- Bottom-right: Klipper, Moonraker, host, network and uptime health.



#### Options and controls

- Printer selector for multi-printer installations.

- Connection indicator with Connected / Reconnecting / Offline / Stale states.

- Printer state badge: ready, printing, paused, complete, error, shutdown, startup.

- Print progress with percentage, current layer, total layer when metadata exists, elapsed time and estimated remaining time.

- Current file name, folder, thumbnail and slicer metadata.

- Optional 2D/3D toolpath preview.

- Camera card with user-selected default camera, full-screen button and snapshot button.

- Nozzle cards for every detected extruder, not only extruder0.

- Bed heater card when heater_bed exists.

- Chamber / ambient / MCU / host temperature cards when those sensors exist.

- Part fan and optional auxiliary fan quick controls.

- Speed factor and flow factor readouts with one-tap reset.

- Quick pause/resume/cancel controls while a job is active.

- Quick Home All, Park, Load, Unload, Bed Mesh and Z Offset actions when valid.

- Favorite macros chosen by the user.

- Warning rail for Klipper errors, Moonraker warnings, sensor faults and high-priority announcements.

- System health card: Klipper state, Moonraker state, host CPU, host memory, host temperature, network activity, storage warning, uptime.

- Optional spool card showing active Spoolman spool and remaining material.

- Widget edit mode: reorder, hide, resize and restore defaults.

- Kiosk mode can hide editing affordances and expand live controls.



#### Data / capability sources

- printer.info / server.info

- printer objects: webhooks, print_stats, virtual_sdcard, display_status, toolhead, gcode_move, extruder*, heater_bed, fan*, temperature_sensor*, system_stats where available

- Moonraker process-stat notifications

- webcam list

- announcements

- Spoolman when configured



#### Safety and behavior

- Cancel requires confirmation.

- Emergency stop is globally accessible but visually separated from normal print controls.

- All action buttons disable when connection is stale or required Klipper state is not ready.



Visual reference: `images/01_dashboard.png` and editable vector `images/01_dashboard.svg`.

### 7.2 Print Job

The detailed active-job plane. It provides print progression, per-object control, live overrides, queue context and safe intervention.

Primary sub-tabs: Active Job, Objects, Overrides, Queue, Preflight.

#### Layout

- Hero progress block on the left.

- Large object/toolpath visualization in the center.

- Metadata and object list on the right.

- Lower panels for speed/flow/fan overrides, print actions, queue and preflight.



#### Options and controls

- Start selected file.

- Pause active job.

- Resume paused job.

- Cancel active job with confirmation.

- Reprint last completed file if it still exists.

- Show progress, elapsed, print duration, total duration, estimated remaining, layer, Z height and active object.

- Show G-code metadata: slicer, layer height, first layer, nozzle diameter, filament estimate, object bounds, estimated duration, thumbnails and modified date when available.

- Object list from Klipper exclude_object definitions.

- Highlight current object.

- Exclude a single object with confirmation and clear explanation that skipped geometry cannot be recovered later.

- Show already excluded objects in red/gray rather than removing them.

- Speed factor slider plus numeric keypad and reset.

- Flow factor slider plus numeric keypad and reset.

- Part cooling fan override and reset to slicer control.

- Pause-at-layer helper implemented through a safe macro / command strategy, not by pretending Klipper has a generic native scheduling UI.

- Filament-change action mapped to configured macro when available.

- Park action mapped to configured macro or explicit configured park coordinates.

- Live temperature mini-cards while printing.

- Queue preview and “add current file again” repeat action.

- Preflight summary before start: Klippy ready, homing policy, configured tool/nozzle, known filament, file fit metadata, file existence, relevant warnings.

- Optional one-time “Start anyway” only for non-critical preflight warnings.

- Current command / macro banner during a user-initiated operation.

- Job user identity when Moonraker history provides it.

- Object thumbnail click opens object details.

- Print notes / tags stored in UI database namespace, never injected into G-code.



#### Data / capability sources

- Moonraker print start/pause/resume/cancel APIs

- print_stats, virtual_sdcard, display_status, toolhead, gcode_move

- exclude_object object

- file metadata / thumbnails

- job queue and history



#### Safety and behavior

- M112 entered in console must be intercepted and sent through /printer/emergency_stop for immediate halt.

- Print controls are state-aware; Start only when the printer/file is valid, Resume only when paused, Pause/Cancel only when printing or paused as appropriate.



Visual reference: `images/02_print.png` and editable vector `images/02_print.svg`.

### 7.3 Movement

Manual positioning that feels like a physical machine console while preventing accidental long or unsafe moves.

Primary sub-tabs: Jog, Coordinates, Homing, Parking, Advanced.

#### Layout

- Large XY directional pad.

- Independent Z up/down column.

- Position and homing status.

- Step-size and jog-speed controls.

- Home, park and motor actions.



#### Options and controls

- XY jog in eight directions or cardinal-only preference.

- Z up and Z down.

- Jog increments: 0.01, 0.05, 0.1, 1, 5, 10, 25, 50, 100 mm; user can choose which chips appear.

- Separate Z increment set with smaller defaults.

- Jog speed selector, with separate XY and Z defaults.

- Hold-to-repeat as an opt-in touch feature with acceleration disabled by default.

- Home All, Home X, Home Y and Home Z.

- Safe-home macro button when configured.

- Display X/Y/Z/E positions and homed_axes.

- Toggle G-code coordinates vs machine coordinates when data supports it.

- Absolute/relative mode indicator; do not silently switch modes for console state.

- Configurable park positions with names, icons and safe-Z requirements.

- Disable steppers with confirmation when Z could fall under gravity; warning text can be printer-profile specific.

- Stepper buzz diagnostic action only under Advanced.

- Endstop status drawer / QUERY_ENDSTOPS.

- Probe state indicator when a probe exists.

- Soft-limit visualization based on config limits.

- Optional bed/nozzle miniature map showing current XY location.

- User-defined “service position” and “camera position.”



#### Data / capability sources

- toolhead, gcode_move, stepper_enable where available

- printer.endstops.status or QUERY_ENDSTOPS

- G-code scripts for G28 and controlled G0/G1 jogging



#### Safety and behavior

- Large moves require homed axes unless user explicitly uses a configured recovery profile.

- Z-down controls may show a near-bed caution zone.

- Disable motors never appears as a bright primary action.



Visual reference: `images/03_movement.png` and editable vector `images/03_movement.svg`.

### 7.4 Thermal

A unified heater, sensor and fan plane with excellent trend visibility and no attempt to replace Klipper thermal protection.

Primary sub-tabs: Overview, Heaters, Fans, Sensors, Presets, PID.

#### Layout

- Large multi-series temperature chart.

- Heater cards.

- Fan cards.

- Sensor list.

- Preset and PID tabs.



#### Options and controls

- Live chart for every detected heater and selected temperature sensors.

- Chart windows: 5 min, 30 min, 2 h, current job and custom.

- Target lines and optional heater-power overlay.

- Nozzle target entry for each extruder.

- Bed target entry.

- Chamber heater target if configured.

- Cooldown all heaters.

- Temperature presets: PLA, PETG, ABS, ASA, Nylon, TPU plus user-defined profiles.

- Preset profile can contain nozzle, bed, chamber and fan values.

- Part fan slider, controller fan state, heater-fan state, temperature-fan target/state and generic-fan control only when those are controllable.

- Tachometer RPM shown only when provided.

- Sensor min/max since connection, current reading and stale timestamp.

- Host and MCU temperature cards if available.

- Heater power 0–100% visualization.

- Heat-up timer and rate-of-change indicator.

- PID tuning entry point, with target temperature, cycles / command details and a result review workflow.

- Pinned sensors for dashboard.

- Chart export to CSV for diagnostic sessions.

- Optional °F display conversion; all commands and persisted Klipper values remain in °C.



#### Data / capability sources

- extruder*, heater_bed, heaters, temperature_sensor*, temperature_fan*, fan/heater_fan/controller_fan/generic_fan

- Moonraker sensor component when configured

- proc-stat CPU temperature



#### Safety and behavior

- Never expose a client-side switch that disables verify_heater or other Klipper protections.

- Numeric targets enforce configured min/max bounds where available and require confirmation for unusually high user-defined thresholds.



Visual reference: `images/04_thermal.png` and editable vector `images/04_thermal.svg`.

### 7.5 Extrusion

Filament handling, tool selection, runout/motion sensor visibility and normal extrusion overrides.

Primary sub-tabs: Extrude, Filament, Spools, Sensors, Tools.

#### Layout

- Large extrude/retract control.

- Load/unload/purge actions.

- Active tool and spool panels.

- Filament sensor cards.

- Flow and pressure-advance summaries.



#### Options and controls

- Extrude and retract buttons.

- Selectable extrusion length chips.

- Selectable extrusion speed.

- Custom numeric length/speed keypad.

- Load Filament and Unload Filament macro discovery / mapping.

- Purge and tip-form actions through configured macros.

- Filament Change action through configured M600-equivalent macro if present.

- Cold-extrusion guard: UI checks hotend state and relies on Klipper min_extrude_temp.

- Flow factor control.

- Active extruder/tool selector for multi-extruder systems.

- Per-extruder target temperature and current temperature.

- Nozzle diameter informational field from printer profile / file metadata.

- Pressure Advance current value and jump to tuning wizard.

- Filament switch sensor states.

- Filament motion sensor states.

- Runout-pause macro association shown when known.

- Optional Spoolman active spool selection, remaining weight/length, vendor, material, color and lot.

- Spool low-material warning based on file estimate plus user safety margin.

- Manual spool override when Spoolman is not present.

- Extrusion command history for current session.



#### Data / capability sources

- extruder objects, gcode_move, filament_switch_sensor*, filament_motion_sensor*

- gcode_macro discovery

- Spoolman integration when present



#### Safety and behavior

- Large purge requires hold-to-confirm.

- Never change rotation_distance or gear_ratio from the normal extrusion page. Those belong in an explicit calibration workflow with config diff review.



Visual reference: `images/05_extrusion.png` and editable vector `images/05_extrusion.svg`.

### 7.6 Bed & Z

One calibration plane for the entire first-layer geometry stack: bed surface, probe, Z offset, screws, gantry and axis twist.

Primary sub-tabs: Bed Mesh, Z Offset, Screws, Gantry, Probe, Axis Twist.

#### Layout

- Large 3D/topographic bed visualization.

- Mesh actions and profiles.

- Z-offset wizard.

- Screw-tilt diagram.

- Gantry/probe tools.



#### Options and controls

- 3D mesh view.

- 2D topographic heat map.

- Numeric point grid.

- Display mesh range, min, max, mean and center deviation.

- BED_MESH_CALIBRATE full automatic.

- Adaptive mesh toggle and margin.

- Scan and rapid_scan methods only when applicable.

- Manual method where applicable.

- Mesh bounds and probe count shown from active config; Advanced users may override for one run.

- Save named mesh profile.

- Load named profile.

- Remove profile with confirmation.

- Clear active mesh.

- Z Offset wizard using PROBE_CALIBRATE or the applicable calibration command.

- Coarse/fine microstep buttons and numeric feedback.

- Accept / Abort controls for manual_probe state.

- SAVE_CONFIG is a separate final review step and never automatic.

- SCREWS_TILT_CALCULATE with diagram, CW/CCW direction and turn amount.

- BED_SCREWS_ADJUST for manual bed-screw workflow when configured.

- Z_TILT_ADJUST when z_tilt exists.

- QUAD_GANTRY_LEVEL when quad_gantry_level exists.

- Probe accuracy test and standard deviation.

- Probe query state.

- BLTouch / eddy-current specific status only if detected.

- Axis twist compensation calibration entry point when configured/supported.

- First-layer assisted test print with live babystep adjustment.

- Store material/nozzle-specific first-layer notes in UI settings.



#### Data / capability sources

- bed_mesh status object and Klipper bed mesh commands

- manual_probe, probe, configfile

- feature-gated G-code commands: BED_MESH_*, PROBE_CALIBRATE, Z_ENDSTOP_CALIBRATE, SCREWS_TILT_CALCULATE, BED_SCREWS_ADJUST, Z_TILT_ADJUST, QUAD_GANTRY_LEVEL, PROBE_ACCURACY, axis twist commands when available



#### Safety and behavior

- Every calibration that can write printer.cfg shows a config diff / values-to-save confirmation.

- Do not show buttons for modules not loaded in printer.objects.list / gcode help.



Visual reference: `images/06_bedz.png` and editable vector `images/06_bedz.svg`.

### 7.7 Tuning

Advanced tuning wizards that collect evidence, show recommendations, apply temporary values first and require review before persistence.

Primary sub-tabs: Input Shaper, Pressure Advance, PID, Motion, Extrusion, Test Patterns.

#### Layout

- Resonance spectrum hero chart.

- Input-shaper recommendation.

- Pressure Advance, PID and motion panels.

- Calibration history.



#### Options and controls

- Accelerometer / resonance capability test.

- Measure X resonance.

- Measure Y resonance.

- Measure both axes.

- Render PSD / resonance curves when data pipeline is available.

- Show current input_shaper values.

- Compare candidate shapers such as ZV, MZV, EI, 2HUMP_EI, 3HUMP_EI when Klipper tooling reports them.

- Apply input shaper temporarily.

- Review exact config values before SAVE_CONFIG / file edit.

- Pressure Advance tower workflow.

- Line-pattern workflow as an optional custom implementation.

- Record PA result by extruder/nozzle/material profile.

- PID autotune for hotend, bed and chamber heater when configured.

- Live PID temperature graph.

- Apply temporary PID parameters only if valid approach supported; otherwise show generated config values for review.

- Motion limits: max_velocity, max_accel, square_corner_velocity and currently applied overrides.

- Temporary velocity/accel limits through SET_VELOCITY_LIMIT.

- Reset temporary limits to configuration baseline.

- Extrusion rotation-distance calibration calculator in a separate wizard that never writes automatically.

- Flow/extrusion multiplier test assistant.

- Temperature tower launcher via user-configured macro or prepared file.

- Retraction test launcher.

- Calibration session history with time, firmware/config fingerprint, values, notes and result.

- Export calibration session JSON/CSV.



#### Data / capability sources

- input_shaper config/status where available

- resonance tester / accelerometer commands and generated data files when configured

- extruder pressure_advance fields

- SET_PRESSURE_ADVANCE, SET_INPUT_SHAPER, SET_VELOCITY_LIMIT and tuning commands

- file manager for generated data where applicable



#### Safety and behavior

- No automatic permanent config mutation. Always temporary → compare → explicit config diff → user acceptance.

- During resonance tests show a warning that the machine will move rapidly and require a clear build area.



Visual reference: `images/07_tuning.png` and editable vector `images/07_tuning.svg`.

### 7.8 Macros

Turn Klipper macros into a discoverable, touch-safe command library rather than a wall of anonymous buttons.

Primary sub-tabs: Favorites, All Macros, Sequences, Parameters, History.

#### Layout

- Favorite macro grid.

- Macro catalog with categories/search.

- Parameter form.

- Sequence builder.

- Run history.



#### Options and controls

- Discover gcode_macro objects automatically.

- Friendly-name aliases stored in UI settings.

- Description field stored in UI metadata.

- Categories: Print, Filament, Calibration, Maintenance, Lighting, Custom.

- Favorite/pin macros.

- Search macros.

- Hide internal macros beginning with underscore by default; Advanced can reveal.

- Parameter form definitions stored in UI metadata: text, number, select, boolean and temperature.

- Default parameter values.

- Parameter min/max validation.

- Macro safety tags: heater, motion, homing, destructive, long-running.

- Per-macro confirmation policy.

- Per-macro required state policy, such as “must be homed” or “must be idle.”

- Run macro.

- Dry-run only where a macro-specific simulator exists; never fake dry-run execution.

- Open source config file / jump to macro definition.

- Sequence builder that chains macros with optional delays and user prompts.

- Sequence abort button.

- Session macro history and result.

- Favorite macro quick bar on dashboard.

- Import/export UI macro metadata.



#### Data / capability sources

- gcode_macro* printer objects, configfile object, printer.gcode.script, Moonraker database namespace for UI metadata



#### Safety and behavior

- Unknown macros default to normal confirmation if they contain obvious restart/power keywords; user can explicitly classify.

- Never parse arbitrary macro Jinja and claim certainty about side effects.



Visual reference: `images/08_macros.png` and editable vector `images/08_macros.svg`.

### 7.9 Files & Queue

A visual file manager and job queue designed for touch, with rich metadata and clear permission boundaries.

Primary sub-tabs: G-code Files, Queue, Config Files, Uploads, Search.

#### Layout

- File list/grid.

- Selected-file preview.

- Metadata/preflight.

- Queue.

- Upload and config-root tabs.



#### Options and controls

- Browse gcodes root and subfolders.

- List or card view.

- Search filename.

- Sort by name, modified date, size, estimated duration and last print.

- Filter by material/nozzle tags when metadata exists.

- Upload G-code.

- Drag-and-drop upload on desktop.

- Start after upload.

- Queue after upload.

- Create folder.

- Rename file.

- Move file.

- Duplicate file.

- Delete file with confirmation.

- Download file.

- Show thumbnail(s).

- Show metadata and object dimensions.

- Preview toolpath / object outline.

- Start print.

- Add one or multiple files to Moonraker job queue.

- Reorder queue in UI by remove/re-add if native queue ordering does not support direct arbitrary reorder; preserve documented semantics.

- Remove queued item.

- Pause/ready queue state.

- Repeat a job by allowing duplicate queue entries.

- Config Files tab for config root with read/write permission badge.

- Read-only roots such as logs/docs/config_examples rendered accordingly.

- Config file editing belongs to an editor modal with diff, syntax display, backup and explicit save.

- Create support zip using Moonraker file ZIP API where applicable.

- Refresh metadata.



#### Data / capability sources

- Moonraker file manager roots, metadata and transfer APIs

- job_queue APIs

- history to show last print / outcome

- Moonraker permissions



#### Safety and behavior

- Never offer write/delete on a read-only root.

- Deleting a file used by an active job is blocked or clearly warned according to current server behavior.

- Config save has diff + backup policy.



Visual reference: `images/09_files.png` and editable vector `images/09_files.svg`.

### 7.10 History

Make printer use measurable: job outcomes, time, material, interruptions and annotations.

Primary sub-tabs: Jobs, Analytics, Materials, Failures, Totals.

#### Layout

- 14/30/90-day trend chart.

- Success-rate and material cards.

- Recent jobs.

- Job detail.

- Filters/exports.



#### Options and controls

- List Moonraker job history with pagination.

- Statuses: completed, error, cancelled, interrupted and in-progress.

- Show user that started job when present.

- Show start/end time, print_duration and total_duration.

- Show filament_used and metadata snapshot.

- Open linked G-code only if exists=true.

- Filter date range, filename, status, material and user.

- Totals: jobs, print hours, filament used.

- Success rate as a UI-derived statistic with clear denominator.

- Daily/weekly print time trend.

- Material consumption by material when spool/file metadata allows it.

- Failure annotations stored in UI namespace.

- Failure cause tags: adhesion, filament, thermal, mechanical, power, user cancel, unknown.

- Attach local UI note; optional snapshot reference.

- Compare repeated runs of the same file.

- Export CSV/JSON.

- Reset Moonraker totals only under Admin/Advanced with strong confirmation; normal History never resets server history.



#### Data / capability sources

- Moonraker history API and auxiliary history fields

- file metadata

- optional Spoolman data



#### Safety and behavior

- Analytics must label estimates and missing data. Never invent filament/material details when metadata is absent.



Visual reference: `images/10_history.png` and editable vector `images/10_history.svg`.

### 7.11 Camera

A multi-camera operator view with minimal latency, touch-friendly full screen and optional overlays.

Primary sub-tabs: Live View, Multi-Cam, Snapshots, Timelapse, Settings.

#### Layout

- Primary camera hero.

- Secondary camera cards.

- View controls.

- Camera configuration summary.

- Optional timelapse area.



#### Options and controls

- List all Moonraker webcam entries.

- Select primary camera.

- Single-camera full-screen.

- Multi-camera grid.

- Snapshot.

- Flip horizontal.

- Flip vertical.

- Rotation 0/90/180/270.

- Aspect ratio display.

- Target FPS and idle FPS display.

- Overlay print progress, temperatures, filename and time; user can disable each overlay.

- Crosshair / nozzle-zone overlay as a UI-only aid.

- Camera health: last frame time / unavailable banner.

- Auto reduce non-primary camera frame rate on constrained devices.

- Timelapse controls only when a detected integration/extension provides them.

- Snapshot gallery in UI storage only if explicitly implemented; otherwise download snapshot directly.



#### Data / capability sources

- Moonraker webcam list/item APIs; actual streams supplied by configured camera service such as crowsnest

- optional third-party timelapse extension



#### Safety and behavior

- Do not claim Moonraker itself controls camera hardware; it stores/shares camera configuration while an external camera service supplies the stream.



Visual reference: `images/11_camera.png` and editable vector `images/11_camera.svg`.

### 7.12 Console

The expert command plane plus a human-readable event and diagnostics center.

Primary sub-tabs: G-code Console, Events, Klippy Log, Moonraker Log, Diagnostics.

#### Layout

- Large G-code terminal.

- Command tools.

- Live event stream.

- Warnings.

- Diagnostic bundle actions.



#### Options and controls

- Send one or multiple G-code commands.

- Command history.

- Autocomplete from /printer/gcode/help plus discovered macros.

- Favorite snippets.

- Clear display without clearing server logs.

- Pause auto-scroll.

- Copy selection.

- Filter response lines by info/warning/error.

- Timestamp responses.

- Event stream for WebSocket connection, object-state changes, announcements and sensor notifications.

- Klippy log viewer.

- Moonraker log viewer.

- Search logs.

- Download logs.

- Create support ZIP containing selected config/log files.

- Copy system info.

- Refresh server/printer info.

- Reconnect WebSocket.

- Clear UI cache / last-known state.

- Display server warnings and failed components prominently.

- Developer pane with last JSON-RPC request/response only when Developer Mode is enabled.



#### Data / capability sources

- printer.gcode.script, printer.gcode.help, server/printer info, file roots/logs, JSON-RPC notifications



#### Safety and behavior

- Intercept exact emergency-stop intent/M112 and invoke /printer/emergency_stop immediately.

- Console warns but does not attempt to understand all arbitrary G-code side effects.



Visual reference: `images/12_console.png` and editable vector `images/12_console.svg`.

### 7.13 Hardware

A capability-driven inventory of the machine: MCUs, sensors, fans, power devices, drivers and peripherals.

Primary sub-tabs: Overview, MCUs, Sensors, Fans, Power, Drivers, Peripherals.

#### Layout

- MCU/host health.

- Sensor inventory.

- Fan inventory.

- Power devices.

- Advanced TMC/peripheral diagnostics.



#### Options and controls

- List Klipper MCUs and versions where available.

- MCU frequency/temperature/restart stats where exposed.

- Host process/CPU/memory/temperature/network summary.

- List probe and endstop state.

- List filament sensors.

- List temperature sensors.

- List fans and RPM where configured.

- List accelerometers / resonance capability if detectable.

- List Moonraker power devices, type, state, locked_while_printing and error state.

- Turn power device on/off/toggle only when permitted.

- Batch power actions only under explicit user selection.

- Home Assistant / MQTT / HTTP / smart plug device types shown using friendly generic device cards.

- TMC driver diagnostic actions such as DUMP_TMC only for configured drivers.

- Display configured run current / hold current from config when parseable.

- Driver current editing is Advanced-only, temporary-first, and not offered when command support cannot be proven.

- List LEDs / output pins as controls only if explicitly mapped in UI metadata; do not expose arbitrary pins.

- Peripheral notes / custom labels stored in UI database.



#### Data / capability sources

- printer.objects.list/query

- Moonraker power device and sensor endpoints

- proc-stat notifications

- configfile

- G-code help for diagnostics



#### Safety and behavior

- Respect locked_while_printing from Moonraker power devices.

- Printer power-off during an active job uses a destructive confirmation and can be blocked by policy.

- Raw GPIO/pin controls are never auto-generated.



Visual reference: `images/13_hardware.png` and editable vector `images/13_hardware.svg`.

### 7.14 System

One place for services, host health, updates, announcements, restart/shutdown and backup/support tasks.

Primary sub-tabs: Status, Updates, Services, Announcements, Storage, Backups.

#### Layout

- Service state.

- Host performance.

- Update cards.

- Announcements.

- Storage/backup.

- Dangerous service actions separated at the bottom.



#### Options and controls

- Klipper connected/state/version.

- Moonraker server status/components/warnings/failed_components.

- Host CPU usage, memory, CPU temp, network and uptime.

- Storage usage if obtainable from Moonraker machine APIs / extension.

- Update-manager status for each configured updater.

- Manual refresh updates.

- Upgrade one component.

- Upgrade all supported components only when idle.

- Show current/reported versions, channel, dirty state and warnings where provided.

- Announcements list, priority badge, open link and dismiss.

- Restart Klipper application.

- Firmware Restart.

- Restart Moonraker/system service when supported by machine APIs.

- Reboot host.

- Shutdown host.

- Emergency Stop.

- Back up config folder.

- Moonraker database backup.

- Generate support zip.

- Export UI settings.

- Restore UI settings from validated JSON.

- Show update progress/events.



#### Data / capability sources

- server.info, printer.info, process-stat notifications

- update manager

- announcements

- system/machine APIs

- database backup APIs where configured

- file manager ZIP



#### Safety and behavior

- Update controls disabled during a print in accordance with Moonraker behavior.

- Reboot/shutdown use hold-to-confirm + second text confirmation.

- Emergency stop remains immediate, not delayed behind a normal G-code queue.



Visual reference: `images/14_system.png` and editable vector `images/14_system.svg`.

### 7.15 Settings

All persistent UI preferences, connection profiles, appearance, dashboard customization, notifications and safety policy.

Primary sub-tabs: Appearance, Layout, Touch, Safety, Connections, Units, Notifications.

#### Layout

- Appearance and accessibility.

- Layout/widget settings.

- Touch behavior.

- Safety confirmations.

- Printer connection profiles.

- Units/localization.

- Notifications and advanced/developer preferences.



#### Options and controls

- Theme preset: NEXUS Green default.

- Accent choices while preserving state colors.

- Glow intensity 0–100%.

- Circuit-grid intensity 0–100%.

- Panel contrast low/normal/high.

- High Contrast mode.

- Reduced Motion mode.

- Large Text mode.

- UI density: comfortable / compact / expert-dense.

- Sidebar: expanded / compact / auto.

- Top status bar: full / compact.

- Dashboard edit mode and restore default widgets.

- Default landing page.

- Quick-action bar location.

- Touch target size: standard 48px or large 56/64px.

- Hold-to-confirm duration for selected dangerous actions.

- On-screen numeric keypad enable.

- Sound effects master toggle.

- Job-complete tone.

- Warning tone.

- Critical error tone.

- Quiet hours for UI sound.

- Kiosk mode.

- Auto full-screen preference.

- Screen dim timeout; optional wake-on-printer-event if platform supports it.

- Temperature display °C/°F.

- Distance display mm/inches while all machine commands remain mm-native.

- 12/24-hour clock.

- Locale/date format.

- Decimal precision preference for temperatures, Z offset and coordinates.

- Multi-printer connection profiles with name, endpoint and color label.

- Auto-connect last printer.

- Auto-reconnect with exponential backoff.

- Authentication/token storage through platform-appropriate secure storage.

- TLS certificate error handling with explicit user warning; no silent insecure downgrade.

- Per-printer capability cache invalidated on reconnect/version change.

- Confirmation policy for cancel, config write, power-off, reboot and shutdown.

- Emergency stop visibility: always visible / top bar + hardware-friendly mode.

- Favorite macros and metadata.

- Park positions.

- Temperature presets.

- Dashboard pinned sensors.

- Camera default and layout.

- Notification preferences.

- Developer Mode toggle.

- Raw JSON/object inspector only in Developer Mode.

- Export all UI settings JSON.

- Import UI settings with schema validation and preview.

- Reset UI settings only, never printer.cfg.

- About page with UI version, Moonraker/Klipper versions and documentation links.



#### Data / capability sources

- Moonraker database namespace recommended for server-associated UI settings, plus local secure storage for secrets

- server/printer info



#### Safety and behavior

- Never store plaintext credentials in export files.

- A UI reset must never reset or edit printer firmware configuration.



Visual reference: `images/15_settings.png` and editable vector `images/15_settings.svg`.

### 7.16 UI Kit

Developer-only visual contract. This is not required as a normal operator page in production, but it is included in the package so the implementation AI can reproduce the visual language consistently.

Primary sub-tabs: Tokens, Buttons, Cards, Charts, Dialogs, States.

#### Layout

- Color tokens.

- Button states.

- Typography.

- Panels and charts.

- Dialog states.

- Animation rules.



#### Options and controls

- Primary, secondary, active, warning, destructive and disabled buttons.

- Normal, information, attention, fault and unavailable state badges.

- Metric cards with tabular numbers.

- List cards.

- Chart card.

- Camera card.

- Modal and confirmation sheet.

- Toast / banner / persistent fault rail.

- Sidebar expanded and compact components.

- Numeric keypad component.

- On-screen keyboard only for filename/search/editing needs.

- Loading skeleton, reconnect overlay and stale-data watermark.

- Tooltip / long-press help.

- Reduced-motion equivalents for every animated effect.



#### Data / capability sources

- No machine data. Static design-system page.



#### Safety and behavior

- State must never be communicated by color alone; use icon + text + color.



Visual reference: `images/16_components.png` and editable vector `images/16_components.svg`.

## 8. Global dialogs, drawers and overlays

- Numeric keypad: large digits, decimal, sign only when valid, Clear, Backspace, Cancel and Apply. Shows allowed min/max and current value.

- Confirmation sheet: action name, exact target, consequence, optional hold-to-confirm, Cancel as the visually dominant safe escape.

- Config diff review: before/after values, source file, line/section when known, backup checkbox, Apply and Restart requirements.

- Connection overlay: never blocks reading last-known status, but clearly watermarks values STALE and disables machine-changing controls.

- Critical fault overlay: fault message, timestamp, relevant service, Copy Details, Open Console and Emergency Stop if applicable.

- Notification center: unread announcement/warning count, filter by printer/system/job, acknowledge/dismiss where server API supports it.

- Command palette: searchable pages, macros and safe navigation actions. Destructive actions require an additional confirmation and never execute directly from fuzzy search.

- Full-screen camera: overlay controls auto-hide after a delay but a visible way to exit remains.

- Help overlay: long-press or ? explains a control in plain language without sending commands.



## 9. Capability gating rules

- Bed Mesh plane always exists as a navigation concept only if bed_mesh or relevant commands are present; otherwise Settings can show “Not configured.”

- Exclude Object controls require the exclude_object object and actual defined objects in the running file.

- Screws Tilt requires the configured module / command. Quad Gantry and Z Tilt are mutually independent capability cards.

- Input-shaper tuning requires the relevant Klipper commands and usually a configured accelerometer/resonance setup. Static current values may still display if available without an accelerometer.

- Spoolman sections appear only when Moonraker reports the integration.

- Webcam plane can remain available with an “Add/configure camera” empty state if Moonraker webcam component is available but no cameras exist.

- Power controls require Moonraker power devices. Never infer a relay from an arbitrary output_pin.

- Timelapse is optional and must be driven by an actual integration/extension, not an assumed Moonraker core feature.

- Update plane shows only configured update-manager entries. Upgrade buttons obey busy/printing restrictions returned by Moonraker.

- TMC advanced cards are diagnostic unless the implementation can prove supported commands/configuration for the driver.



## 10. Safety model

- Class A - immediate emergency: Emergency Stop. One tap/click executes the emergency endpoint immediately; optional physical-style red button UI. No second confirmation that delays the halt.

- Class B - destructive job actions: Cancel print, exclude object after printing has started, delete G-code. Confirm once with target-specific text.

- Class C - machine/service actions: firmware restart, service restart, reboot, shutdown, power off. Hold + confirm or two-step confirmation.

- Class D - persistent calibration/config writes: show temporary/test result first, then config diff, then explicit save. Create backup where possible.

- Class E - normal controls: jog, heater targets within allowed ranges, fan, macros classified as safe. Execute directly when machine state is valid.

- Disconnected/stale state disables Class B-E machine mutations. Emergency Stop remains available only if the request transport is actually reachable; otherwise show that the console cannot deliver the command.

- Do not suppress Klipper/Moonraker errors. The UI may translate them to clearer wording, but preserve raw details in an expandable section.



## 11. Persistence and user settings

- Use a namespaced schema such as `nexus_control` in Moonraker database for non-secret UI metadata that should follow the server: dashboard layout, macro labels, presets, park positions, UI tags and schema version.

- Use local secure storage / OS credential storage for secrets or authentication tokens when this is packaged as a desktop/kiosk application.

- Every persisted object includes a schema version and migration path.

- Export settings intentionally excludes secrets and connection tokens.

- Per-printer settings are keyed by a stable printer profile ID, not only hostname, so renamed hosts can be repaired without data collision.



## 12. Recommended implementation architecture

- Frontend: Vue 3 + TypeScript + Vite is the recommended baseline, though React/Svelte are acceptable if the existing project already uses them. Do not rewrite a working project merely to change frameworks.

- State: Pinia (Vue) or an equivalent typed store, split into connection, printer objects, files/jobs, UI settings and notifications.

- Routing: client-side routes for each control plane with the shell mounted once.

- Charts: a lightweight canvas/SVG library capable of streaming series. Avoid re-rendering the whole page for every temperature update.

- 3D bed mesh/toolpath: Three.js or a small custom WebGL/canvas renderer; provide a 2D fallback for low-power panels.

- API layer: one Moonraker client module supporting HTTP, WebSocket JSON-RPC, capability discovery, typed error normalization and command cancellation/timeouts.

- No direct filesystem assumptions from the browser. All server files go through Moonraker APIs.

- Optional desktop wrapper: Tauri or Electron only if true kiosk/system integration is needed. The core UI should remain web-deployable.



## 13. Suggested source tree

```text

src/
  app/
    router.ts
    shell/
  api/
    moonraker-http.ts
    moonraker-ws.ts
    capabilities.ts
    commands.ts
  stores/
    connection.ts
    printer.ts
    jobs.ts
    files.ts
    cameras.ts
    system.ts
    settings.ts
  pages/
    Dashboard/ PrintJob/ Movement/ Thermal/ Extrusion/
    BedZ/ Tuning/ Macros/ FilesQueue/ History/ Camera/
    Console/ Hardware/ System/ Settings/
  components/
    nexus/ MetricCard.vue ControlButton.vue StatusBadge.vue
    NumericKeypad.vue ConfirmSheet.vue ConfigDiff.vue TrendChart.vue
    BedMeshView.vue CameraView.vue Terminal.vue FaultRail.vue
  domain/
    state-normalizer.ts
    safety-policy.ts
    feature-gates.ts
    units.ts
  styles/
    tokens.css
    nexus-shell.css
    components.css
```


## 14. Implementation phases

- Phase 0 - Inventory existing code. Do not code until the AI identifies framework, existing Moonraker client, routes, reusable components and gaps.

- Phase 1 - Build shell, tokens, responsive layout, routing, feature-gate service and reconnect/stale-state behavior.

- Phase 2 - Implement read-only live Dashboard using real server/printer/object subscriptions.

- Phase 3 - Add Print Job, Movement, Thermal and Extrusion control actions with safety policy.

- Phase 4 - Add Bed & Z and Tuning wizards. Persistent writes remain review-gated.

- Phase 5 - Add Macros, Files/Queue and History.

- Phase 6 - Add Cameras, Console/Diagnostics, Hardware and System/Updates.

- Phase 7 - Add Settings, multi-printer profiles, accessibility/reduced-motion and dashboard customization.

- Phase 8 - Performance hardening, kiosk/full-screen, reconnection torture tests, responsive QA and release packaging.



## 15. Acceptance criteria

- No browser-page vertical scroll at the reference 1920x1080 layout; data-heavy child panels scroll internally.

- All normal touch controls are at least 48x48 px at standard density.

- UI connects to a real Moonraker instance and the Dashboard updates without manual refresh.

- Removing an optional Klipper module from configuration removes or disables the corresponding feature cleanly after reconnect/restart.

- WebSocket disconnect produces a visible stale/reconnecting state and prevents unsafe stale-state commands.

- Pause, Resume, Cancel and Start use Moonraker print APIs and display success/error feedback.

- Emergency Stop uses the immediate Moonraker emergency-stop endpoint.

- Object exclusion works only when actual exclude_object definitions exist.

- Bed mesh renders real matrix values and supports the configured calibration methods without inventing unsupported modes.

- Config-changing wizards never persist automatically. A user must review and explicitly save.

- Power devices respect locked_while_printing.

- Updates are not offered while printing when Moonraker disallows them.

- Camera transforms and multiple cameras honor Moonraker webcam configuration.

- Screen remains readable with glow intensity at 0%.

- Reduced Motion eliminates ambient effects.

- High Contrast remains usable without relying on green/red discrimination.

- At 800x480 the same pages remain usable with compact navigation and internal scrolling.

- Every API error can be expanded to raw server detail for diagnosis.

- No copied Star Trek/Borg logos, screenshots or exact interface artwork ship with the product.



## 16. Package assets

- `images/00_concept_art_dashboard.png` - high-fidelity visual concept art.

- `images/01_dashboard.png` through `16_components.png` - implementation-oriented page mockups.

- Matching `.svg` files - editable vector page references.

- `prototype/index.html` - static browser prototype for style/layout exploration.

- `specs/design_tokens.json` - machine-readable colors, spacing, touch sizes and breakpoints.

- `specs/page_manifest.json` - machine-readable page/option/capability contract.

- `specs/API_MAP.md` - integration map and current official documentation links.

- `specs/SWE2_IMPLEMENTATION_PROMPT.md` - direct handoff prompt.



## 17. Upstream technical basis

The package was checked against current Moonraker/Klipper documentation. Moonraker provides printer status/control, file management, queue/history, webcam configuration, devices/sensors, announcements, updates, database storage and JSON-RPC notifications. Klipper exposes optional modules through printer objects and G-code commands; therefore NEXUS must discover capabilities instead of assuming them.

- https://moonraker.readthedocs.io/en/latest/external_api/printer/

- https://moonraker.readthedocs.io/en/latest/external_api/server/

- https://moonraker.readthedocs.io/en/latest/external_api/file_manager/

- https://moonraker.readthedocs.io/en/latest/external_api/job_queue/

- https://moonraker.readthedocs.io/en/latest/external_api/history/

- https://moonraker.readthedocs.io/en/latest/external_api/webcams/

- https://moonraker.readthedocs.io/en/latest/external_api/devices/

- https://moonraker.readthedocs.io/en/latest/external_api/update_manager/

- https://moonraker.readthedocs.io/en/latest/external_api/announcements/

- https://moonraker.readthedocs.io/en/latest/external_api/database/

- https://moonraker.readthedocs.io/en/latest/external_api/jsonrpc_notifications/

- https://www.klipper3d.org/Status_Reference.html

- https://www.klipper3d.org/G-Codes.html

- https://www.klipper3d.org/Bed_Mesh.html

- https://www.klipper3d.org/Exclude_Object.html

- https://www.klipper3d.org/Resonance_Compensation.html


