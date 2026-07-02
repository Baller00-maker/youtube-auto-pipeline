"""
Pipeline "Histoires dramatiques" -- Étape 5 : montage final vertical (1080x1920)
- Répartit la durée audio entre les scènes (proportionnel à la longueur du texte)
- Images : effet Ken Burns vertical + zoom dramatique
- Vidéos : recadrées en portrait avec focus central
- Sous-titres anglais incrustés en bas de l'écran (zone safe TikTok)
- Sauvegarde story_final.mp4
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

VISUALS_FILE = Path("story_visuals.json")
AUDIO_FILE = Path("story_narration.mp3")
SUBTITLES_FILE = Path("story_subtitles.srt")
TIMING_FILE = Path("story_timing.json")
WORKDIR = Path("story_clips")
OUTPUT_FILE = Path("story_final.mp4")

WIDTH, HEIGHT = 1080, 1920
FPS = 25


def run_ffmpeg(args, description):
    print(f"  ffmpeg: {description}")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ! Erreur : {result.stderr[-800:]}", file=sys.stderr)
        return False
    return True


def make_image_clip(image_path, duration, output_path):
    frames = max(1, int(duration * FPS))
    zoompan = (
        f"scale={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+0.0008,1.2)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    args = [
        "-loop", "1", "-i", str(image_path),
        "-t", str(duration),
        "-vf", zoompan,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    return run_ffmpeg(args, f"image Ken Burns ({duration:.1f}s)")


def make_video_clip(video_path, duration, output_path):
    vf = (
        f"scale=-1:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"fps={FPS}"
    )
    args = [
        "-stream_loop", "-1", "-i", str(video_path),
        "-t", str(duration),
        "-vf", vf, "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    return run_ffmpeg(args, f"vidéo portrait ({duration:.1f}s)")


def main():
    for f in (VISUALS_FILE, AUDIO_FILE, SUBTITLES_FILE, TIMING_FILE):
        if not f.exists():
            print(f"Erreur : {f} introuvable.", file=sys.stderr)
            sys.exit(1)

    if shutil.which("ffmpeg") is None:
        print("Erreur : ffmpeg introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(VISUALS_FILE) as f:
        manifest = json.load(f)
    with open(TIMING_FILE) as f:
        timing = json.load(f)

    total_duration = timing[-1]["end"] if timing else 90.0
    print(f"Durée audio : {total_duration:.1f}s | {len(manifest)} scènes")

    text_lengths = [len(e["narration_fr"]) for e in manifest]
    total_chars = sum(text_lengths) or 1

    WORKDIR.mkdir(exist_ok=True)
    clip_paths = []

    for entry, char_len in zip(manifest, text_lengths):
        duration = max(2.0, total_duration * (char_len / total_chars))
        clip_path = WORKDIR / f"story_clip_{entry['index']:03d}.mp4"
        print(f"[{entry['index']+1}/{len(manifest)}] {entry['type']} | {entry['query']} | {duration:.1f}s")

        ok = (make_image_clip(entry["path"], duration, clip_path)
              if entry["type"] == "image"
              else make_video_clip(entry["path"], duration, clip_path))
        if ok and clip_path.exists():
            clip_paths.append(clip_path)

    if not clip_paths:
        print("Erreur : aucun clip généré.", file=sys.stderr)
        sys.exit(1)

    concat_list = WORKDIR / "story_concat.txt"
    with open(concat_list, "w") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    silent_video = WORKDIR / "story_silent.mp4"
    if not run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent_video)],
        "concat"
    ):
        sys.exit(1)

    srt_escaped = str(SUBTITLES_FILE.resolve().as_posix()).replace(":", "\\:")
    subtitle_style = (
        "FontName=Arial,FontSize=18,Bold=1,"
        "PrimaryColour=&HFFFFFF,OutlineColour=&H000000,"
        "BorderStyle=3,Alignment=2,MarginV=150"
    )
    args = [
        "-i", str(silent_video),
        "-i", str(AUDIO_FILE),
        "-vf", f"subtitles='{srt_escaped}':force_style='{subtitle_style}'",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        str(OUTPUT_FILE),
    ]
    if not run_ffmpeg(args, "fusion finale"):
        sys.exit(1)

    print(f"\nVidéo finale : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
