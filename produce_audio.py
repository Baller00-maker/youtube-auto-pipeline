"""
Étape 4a du pipeline : génération de la narration audio
- Lit script.json (script généré à l'étape précédente)
- Convertit le texte en voix via Edge-TTS (gratuit, voix masculine grave/sérieuse)
- Sauvegarde narration.mp3 + les timestamps mot par mot (narration_timing.json)
  -> Les timestamps serviront à synchroniser sous-titres et visuels dans l'étape de montage
"""

import asyncio
import json
import sys
from pathlib import Path

import edge_tts

SCRIPT_FILE = Path("script.json")
AUDIO_OUTPUT = Path("narration.mp3")
TIMING_OUTPUT = Path("narration_timing.json")

# Voix grave/sérieuse, adaptée à un ton documentaire/militaire
VOICE = "en-US-ChristopherNeural"
RATE = "+0%"   # vitesse de narration, ex: "-10%" pour plus lent
PITCH = "+0Hz"


async def generate_audio(text, voice, rate, pitch, audio_path):
    """Génère l'audio et collecte les WordBoundary (timestamps) en une seule passe."""
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    word_boundaries = []

    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append({
                    "text": chunk["text"],
                    "offset_seconds": chunk["offset"] / 10_000_000,  # ticks -> secondes
                    "duration_seconds": chunk["duration"] / 10_000_000,
                })

    return word_boundaries


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
    word_boundaries = asyncio.run(
        generate_audio(script_text, VOICE, RATE, PITCH, AUDIO_OUTPUT)
    )

    with open(TIMING_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(word_boundaries, f, ensure_ascii=False, indent=2)

    total_duration = word_boundaries[-1]["offset_seconds"] + word_boundaries[-1]["duration_seconds"] if word_boundaries else 0
    print(f"\nAudio sauvegardé : {AUDIO_OUTPUT}")
    print(f"Timing sauvegardé : {TIMING_OUTPUT} ({len(word_boundaries)} mots avec timestamp)")
    print(f"Durée totale estimée : {total_duration:.1f} secondes (~{total_duration / 60:.1f} min)")


if __name__ == "__main__":
    main()
