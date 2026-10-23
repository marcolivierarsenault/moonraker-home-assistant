import json
import os
import shutil
import time
import threading

import appdaemon.plugins.hass.hassapi as hass

TTS_DIR = "/homeassistant/tts"
OUT_DIR = "/homeassistant/tts_playback"
PHRASE_FILE = "/config/apps/tts_phrases.json"
ENGINE = "tts.azure_expressive"
PLAYER = "media_player.office_speaker"
WAIT_FILE = 25.0
GAP = 5.0


class TtsCache(hass.Hass):

    def initialize(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        with open(PHRASE_FILE) as f:
            data = json.load(f)
        os.makedirs(OUT_DIR, exist_ok=True)
        order, phrases = data["order"], data["phrases"]
        manifest = {}
        for i, name in enumerate(order):
            text = phrases[name]
            before = set(os.listdir(TTS_DIR))
            self.call_service(
                "tts/speak",
                entity_id=ENGINE,
                media_player_entity_id=PLAYER,
                message=text,
                cache=True,
            )
            deadline = time.time() + WAIT_FILE
            new_file = None
            while time.time() < deadline:
                diff = set(os.listdir(TTS_DIR)) - before
                if diff:
                    new_file = sorted(diff)[0]
                    break
                time.sleep(0.5)
            if new_file:
                src = os.path.join(TTS_DIR, new_file)
                dst = os.path.join(OUT_DIR, f"{name}.mp3")
                try:
                    shutil.copyfile(src, dst)
                    manifest[name] = {"text": text, "file": f"{name}.mp3"}
                    self.log(f"CACHE [{i+1}/{len(order)}] {name} <- {new_file}")
                except Exception as e:
                    self.log(f"CACHE FAIL {name}: {e}")
            else:
                manifest[name] = {"text": text, "file": None}
                self.log(f"CACHE MISS {name}")
            time.sleep(GAP)
        with open(os.path.join(OUT_DIR, "manifest.json"), "w") as f:
            json.dump(manifest, f, indent=1)
        self.log("TTS CACHE BUILD COMPLETE")
