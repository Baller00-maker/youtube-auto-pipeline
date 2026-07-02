"""
Pipeline "Histoires dramatiques" -- Étape 2 : narration audio française
- Voix masculine dramatique : fr-FR-HenriNeural
- Sauvegarde story_narration.mp3
"""

import asyncio
import json
import sys
from pathlib import Path

import edge_tts

SCRIPT_FILE = Path("story_script.json")
AUDIO_OUTPUT = Path("story_narration.mp3")

VOICE = "fr-FR-DeniseNeural"  # voix féminine française, très expressive et émotionnelle
RATE = "-10%"  # légèrement plus lent pour maximiser l'impact dramatique
PITCH = "+0Hz"


async def generate_audio(text, voice, rate, pitch, audio_path):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(audio_path))


def main():
    if not SCRIPT_FILE.exists():
        print(f"Erreur : {SCRIPT_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    script_text = data["full_script_fr"]
    print(f"Narration ({len(script_text.split())} mots, voix {VOICE})...")
    asyncio.run(generate_audio(script_text, VOICE, RATE, PITCH, AUDIO_OUTPUT))
    print(f"Audio sauvegardé : {AUDIO_OUTPUT}")


if __name__ == "__main__":
    main()
