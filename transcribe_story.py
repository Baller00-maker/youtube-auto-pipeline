"""
Pipeline "Histoires dramatiques" -- Étape 4 : sous-titres anglais
- Transcrit story_narration.mp3 (français) ET traduit en anglais (Whisper task=translate)
- Sauvegarde story_subtitles.srt + story_timing.json
"""

import json
import sys
from pathlib import Path

import whisper

AUDIO_FILE = Path("story_narration.mp3")
SRT_OUTPUT = Path("story_subtitles.srt")
TIMING_OUTPUT = Path("story_timing.json")
WHISPER_MODEL_SIZE = "base"


def format_srt_timestamp(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_srt(segments, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(f"{i}\n")
            f.write(f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n")
            f.write(f"{seg['text'].strip()}\n\n")


def main():
    if not AUDIO_FILE.exists():
        print(f"Erreur : {AUDIO_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    print(f"Chargement Whisper ({WHISPER_MODEL_SIZE})...")
    model = whisper.load_model(WHISPER_MODEL_SIZE)

    print("Transcription + traduction FR→EN...")
    result = model.transcribe(str(AUDIO_FILE), language="fr", task="translate", verbose=False)
    segments = result["segments"]
    print(f"{len(segments)} segments traduits.")

    write_srt(segments, SRT_OUTPUT)
    timing = [{"start": s["start"], "end": s["end"], "text": s["text"].strip()} for s in segments]
    with open(TIMING_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)

    total = segments[-1]["end"] if segments else 0
    print(f"Durée : {total:.1f}s (~{total/60:.1f} min)")
    print(f"SRT : {SRT_OUTPUT} | Timing : {TIMING_OUTPUT}")


if __name__ == "__main__":
    main()
