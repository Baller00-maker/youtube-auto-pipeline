"""
Étape 4a du pipeline : génération de la narration audio
- Lit script.json (script généré à l'étape précédente)
- Convertit le texte en voix via Edge-TTS (gratuit, voix masculine grave/sérieuse)
- Sauvegarde narration.mp3

Note : les timestamps mot par mot seront générés séparément via Whisper à l'étape
des sous-titres (plus fiable que les WordBoundary d'edge-tts, dont le format change
régulièrement entre versions).
"""

import asyncio
import json
import sys
from pathlib import Path

import edge_tts

SCRIPT_FILE = Path("script.json")
AUDIO_OUTPUT = Path("narration.mp3")

# Voix grave/sérieuse, adaptée à un ton documentaire/militaire -- validée par l'utilisateur
VOICE = "en-US-ChristopherNeural"
RATE = "+0%"   # vitesse de narration, ex: "-10%" pour plus lent
PITCH = "+0Hz"


async def generate_audio(text, voice, rate, pitch, audio_path):
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    await communicate.save(str(audio_path))


def main():
    if not SCRIPT_FILE.exists():
        print(f"Erreur : {SCRIPT_FILE} introuvable. Lance d'abord generate_script.py.", file=sys.stderr)
        sys.exit(1)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    script_text = data["script"]
    print(f"Texte à narrer : {len(script_text.split())} mots")
    print(f"Voix utilisée : {VOICE}")

    print("Génération de la narration audio (peut prendre une minute)...")
    asyncio.run(generate_audio(script_text, VOICE, RATE, PITCH, AUDIO_OUTPUT))

    print(f"\nAudio sauvegardé : {AUDIO_OUTPUT}")


if __name__ == "__main__":
    main()
