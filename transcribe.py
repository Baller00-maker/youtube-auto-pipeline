"""
Étape 4b du pipeline : sous-titres + timing précis
- Lit narration.mp3 (généré à l'étape précédente)
- Utilise Whisper (local, gratuit, open source) pour transcrire avec timestamps précis
- Sauvegarde :
  - subtitles.srt   -> sous-titres au format standard, utilisables directement par ffmpeg
  - timing.json     -> liste de segments avec texte + start/end, utilisée pour caler
                       les changements d'images sur le montage vidéo
"""

import json
import sys
from pathlib import Path

import whisper

AUDIO_FILE = Path("narration.mp3")
SRT_OUTPUT = Path("subtitles.srt")
TIMING_OUTPUT = Path("timing.json")

# "base" = rapide et suffisant pour de l'anglais clair en voix de synthèse.
# Options plus précises mais plus lentes : "small", "medium".
WHISPER_MODEL_SIZE = "base"


def format_srt_timestamp(seconds):
    """Convertit des secondes en format SRT : HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(segments, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(f"{i}\n")
            f.write(f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n")
            f.write(f"{seg['text'].strip()}\n\n")


def main():
    if not AUDIO_FILE.exists():
        print(f"Erreur : {AUDIO_FILE} introuvable. Lance d'abord produce_audio.py.", file=sys.stderr)
        sys.exit(1)

    print(f"Chargement du modèle Whisper ({WHISPER_MODEL_SIZE})...")
    model = whisper.load_model(WHISPER_MODEL_SIZE)

    print(f"Transcription de {AUDIO_FILE} avec timestamps (peut prendre 1-3 minutes)...")
    result = model.transcribe(str(AUDIO_FILE), language="en", verbose=False)

    segments = result["segments"]
    print(f"{len(segments)} segments détectés.")

    write_srt(segments, SRT_OUTPUT)
    print(f"Sous-titres sauvegardés : {SRT_OUTPUT}")

    timing = [
        {"start": seg["start"], "end": seg["end"], "text": seg["text"].strip()}
        for seg in segments
    ]
    with open(TIMING_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)
    print(f"Timing sauvegardé : {TIMING_OUTPUT}")

    total_duration = segments[-1]["end"] if segments else 0
    print(f"Durée totale détectée : {total_duration:.1f}s (~{total_duration / 60:.1f} min)")


if __name__ == "__main__":
    main()
