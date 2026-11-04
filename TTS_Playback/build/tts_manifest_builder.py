"""Build announcements.json — maps every system announcement to clip segments.

Each announcement lists the ordered clips to concatenate. Dynamic slots are
named placeholders; finite value sets (numbers, klippy states, verdicts,
progress marks) map to pre-rendered clips so announcements merge locally
instead of regenerating TTS.
"""

import json

ANNOUNCEMENTS = {
    # -- panel_client.js announce() calls ------------------------------------
    "voice_test": {
        "kind": "test",
        "segments": ["voice_test"],
    },
    "print_resumed": {
        "kind": "start",
        "segments": ["print_resumed"],
    },
    "print_started": {
        "kind": "start",
        "template": "Print started: {filename}",
        "segments": ["pfx_print_started", {"dynamic": "filename"}],
    },
    "print_paused": {
        "kind": "pause",
        "segments": ["print_paused"],
    },
    "print_complete": {
        "kind": "finish",
        "template": "Print complete: {filename}",
        "segments": ["pfx_print_complete", {"dynamic": "filename"}],
    },
    "print_cancelled": {
        "kind": "finish",
        "template": "Print cancelled: {filename}",
        "segments": ["pfx_print_cancelled", {"dynamic": "filename"}],
    },
    "print_error": {
        "kind": "error",
        "template": "Print error: {filename}",
        "segments": ["pfx_print_error", {"dynamic": "filename"}],
    },
    "print_progress": {
        "kind": "progress",
        "template": "Print is {mark} percent complete",
        "segments": ["pfx_progress", {"value_map": "mark"}, "sfx_percent"],
        "values": {"mark": {m: f"num_{m}" for m in (25, 50, 75, 90)}},
    },
    "filament_runout": {
        "kind": "runout",
        "segments": ["filament_runout"],
    },
    "printer_fault": {
        "kind": "error",
        "template": "Printer fault: Klippy reports {state}",
        "segments": ["pfx_printer_fault", {"value_map": "state"}],
        "values": {
            "state": {
                s: f"klippy_{s}"
                for s in ("ready", "error", "shutdown", "startup", "disconnected")
            }
        },
    },
    # -- analyzer.py _notify() titles (also used by notify services) ----------
    "vision_alert": {
        "kind": "error",
        "template": "Print problem detected: {filename}",
        "segments": ["pfx_vision_alert", {"dynamic": "filename"}],
    },
    # -- printcast.py forecast announcements ----------------------------------
    "printcast_forecast": {
        "kind": "forecast",
        "template": "Printcast {score} out of 100, verdict {verdict}",
        "segments": [
            "pfx_printcast",
            {"value_map": "score"},
            "sfx_out_of_100",
            {"value_map": "verdict"},
        ],
        "values": {
            "score": {n: f"num_{n}" for n in range(101)},
            "verdict": {
                "clear": "verdict_clear",
                "caution": "verdict_caution",
                "poor": "verdict_poor",
                "no-go": "verdict_no_go",
            },
        },
    },
}

# companion-app notify titles that differ from spoken forms
NOTIFY_TITLES = {
    "print_started": "Print started",
    "print_resumed": "Print resumed",
    "print_paused": "Print paused",
    "print_completed": "Print completed",
    "print_cancelled": "Print cancelled",
    "print_error": "Print error",
    "vision_alert": "Print problem detected",
}

if __name__ == "__main__":
    out = {"announcements": ANNOUNCEMENTS, "notify_titles": NOTIFY_TITLES}
    with open("TTS_Playback/announcements.json", "w") as f:
        json.dump(out, f, indent=1)
    print(f"{len(ANNOUNCEMENTS)} announcements -> TTS_Playback/announcements.json")
