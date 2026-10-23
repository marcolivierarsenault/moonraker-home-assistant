import json

PHRASES = {
    # static announcements
    "voice_test": "Nexus control voice alert test",
    "print_resumed": "Print resumed",
    "print_paused": "Print paused",
    "filament_runout": "Filament runout detected",
    # announcement prefixes (colon keeps the natural pause prosody)
    "pfx_print_started": "Print started:",
    "pfx_print_complete": "Print complete:",
    "pfx_print_completed": "Print completed:",
    "pfx_print_cancelled": "Print cancelled:",
    "pfx_print_error": "Print error:",
    "pfx_vision_alert": "Print problem detected:",
    "pfx_printer_fault": "Printer fault: Klippy reports",
    "pfx_progress": "Print is",
    "sfx_percent": "percent complete",
    # printcast
    "pfx_printcast": "Printcast",
    "sfx_out_of_100": "out of 100",
    "verdict_clear": "clear",
    "verdict_caution": "caution",
    "verdict_poor": "poor",
    "verdict_no_go": "no go",
    # klippy states
    "klippy_ready": "ready",
    "klippy_error": "error",
    "klippy_shutdown": "shutdown",
    "klippy_startup": "startup",
    "klippy_disconnected": "disconnected",
}
for n in range(101):
    PHRASES[f"num_{n}"] = str(n)

ORDER = list(PHRASES)

with open("tts_phrases.json", "w") as f:
    json.dump({"order": ORDER, "phrases": PHRASES}, f, indent=1)
print(len(ORDER), "phrases")
