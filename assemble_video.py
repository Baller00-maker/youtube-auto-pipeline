"""
Étape 5 du pipeline : montage final
- Lit visuals.json (manifeste images/vidéos par segment)
- Génère un clip de durée exacte pour chaque visuel :
  - image -> effet Ken Burns (zoom lent) via ffmpeg zoompan
  - vidéo -> recadrée/bouclée à la bonne durée
- Concatène tous les clips en une seule vidéo silencieuse
- Ajoute narration.mp3 comme piste audio
- Incruste subtitles.srt directement dans l'image (sous-titres "burned-in")
- Sauvegarde final_video.mp4

Prérequis : ffmpeg installé et accessible dans le PATH (vérifié à l'étape transcribe.py).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

VISUALS_FILE = Path("visuals.json")
AUDIO_FILE = Path("narration.mp3")
SUBTITLES_FILE = Path("subtitles.srt")
WORKDIR = Path("clips")
OUTPUT_FILE = Path("final_video.mp4")

WIDTH, HEIGHT = 1920, 1080
FPS = 25


def run_ffmpeg(args, description):
    print(f"  ffmpeg: {description}")
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"    ! Erreur ffmpeg : {result.stderr[-800:]}", file=sys.stderr)
        return False
    return True


def fill_gaps(manifest, total_blocks):
    """Si un segment n'a pas de visuel (index manquant), le visuel précédent est
    prolongé pour couvrir le trou, afin de ne jamais laisser d'écran noir."""
    by_index = {v["index"]: v for v in manifest}
    filled = []
    last_valid = None

    for i in range(total_blocks):
        if i in by_index:
            entry = dict(by_index[i])
            last_valid = entry
            filled.append(entry)
        elif last_valid is not None:
            # Prolonge le précédent : on additionne juste la durée, le clip sera généré plus long
            last_valid["duration"] += 7  # approx. durée d'un bloc manqué
        # si last_valid est encore None (premier bloc manquant), on ignore -- cas rare

    return filled


def make_image_clip(image_path, duration, output_path):
    """Crée un clip vidéo à partir d'une image fixe, avec effet Ken Burns (zoom lent)."""
    frames = max(1, int(duration * FPS))
    zoompan = (
        f"scale={WIDTH * 2}:{HEIGHT * 2},"
        f"zoompan=z='min(zoom+0.0006,1.15)':d={frames}:s={WIDTH}x{HEIGHT}:fps={FPS}"
    )
    args = [
        "-loop", "1",
        "-i", str(image_path),
        "-t", str(duration),
        "-vf", zoompan,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    return run_ffmpeg(args, f"image -> clip ({duration:.1f}s)")


def make_video_clip(video_path, duration, output_path):
    """Recadre/boucle un clip vidéo stock pour correspondre exactement à la durée voulue."""
    vf = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},fps={FPS}"
    args = [
        "-stream_loop", "-1",
        "-i", str(video_path),
        "-t", str(duration),
        "-vf", vf,
        "-an",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    return run_ffmpeg(args, f"vidéo -> clip ({duration:.1f}s)")


def main():
    for required in (VISUALS_FILE, AUDIO_FILE, SUBTITLES_FILE):
        if not required.exists():
            print(f"Erreur : {required} introuvable.", file=sys.stderr)
            sys.exit(1)

    if shutil.which("ffmpeg") is None:
        print("Erreur : ffmpeg n'est pas trouvé dans le PATH.", file=sys.stderr)
        sys.exit(1)

    with open(VISUALS_FILE, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    total_blocks = max(v["index"] for v in manifest) + 1
    manifest = fill_gaps(manifest, total_blocks)
    print(f"{len(manifest)} clips à générer (gaps comblés automatiquement).")

    WORKDIR.mkdir(exist_ok=True)
    clip_paths = []

    for entry in manifest:
        clip_path = WORKDIR / f"clip_{entry['index']:03d}.mp4"
        print(f"[{entry['index'] + 1}/{len(manifest)}] {entry['type']} | {entry['query']} | {entry['duration']:.1f}s")

        ok = (
            make_image_clip(entry["path"], entry["duration"], clip_path)
            if entry["type"] == "image"
            else make_video_clip(entry["path"], entry["duration"], clip_path)
        )
        if ok and clip_path.exists():
            clip_paths.append(clip_path)
        else:
            print(f"    ! Clip {entry['index']} ignoré (échec génération).", file=sys.stderr)

    if not clip_paths:
        print("Erreur : aucun clip généré, montage impossible.", file=sys.stderr)
        sys.exit(1)

    # Liste pour le concat demuxer ffmpeg
    concat_list_path = WORKDIR / "concat_list.txt"
    with open(concat_list_path, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve().as_posix()}'\n")

    silent_video = WORKDIR / "silent_full.mp4"
    print("\nConcaténation de tous les clips...")
    ok = run_ffmpeg(
        ["-f", "concat", "-safe", "0", "-i", str(concat_list_path), "-c", "copy", str(silent_video)],
        "concat des clips",
    )
    if not ok:
        print("Erreur lors de la concaténation.", file=sys.stderr)
        sys.exit(1)

    print("Ajout de la narration audio + incrustation des sous-titres...")
    srt_escaped = str(SUBTITLES_FILE.resolve().as_posix()).replace(":", "\\:")
    args = [
        "-i", str(silent_video),
        "-i", str(AUDIO_FILE),
        "-vf", f"subtitles='{srt_escaped}':force_style='FontSize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=3'",
        "-c:v", "libx264",
        "-c:a", "aac",
        "-shortest",
        str(OUTPUT_FILE),
    ]
    ok = run_ffmpeg(args, "fusion finale audio + sous-titres")
    if not ok:
        print("Erreur lors de la fusion finale.", file=sys.stderr)
        sys.exit(1)

    print(f"\nVidéo finale sauvegardée : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
