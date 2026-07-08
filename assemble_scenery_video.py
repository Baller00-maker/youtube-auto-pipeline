"""
Pipeline Paysages/Espace -- Étape 2 : montage vidéo
- Lit scenery_manifest.json
- Pour chaque clip :
  - Coupe à MAX_CLIP secondes
  - Recadre en vertical 1080x1920 (crop centre depuis 1920x1080)
  - Ajoute un léger zoom cinématique (scale 1.0→1.05)
  - Fondu entrant (0.4s) et sortant (0.4s) sur chaque clip
- Concatène en une seule vidéo
- PAS de son
- Sauvegarde scenery_final.mp4
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST_FILE = Path("scenery_manifest.json")
WORK_DIR      = Path("scenery_clips_processed")
OUTPUT_FILE   = Path("scenery_final.mp4")

W, H  = 1080, 1920
FPS   = 30
MAX_CLIP = 12


def run(cmd, desc=""):
    if desc:
        print(f"  {desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ! ffmpeg erreur : {r.stderr[-600:]}", file=sys.stderr)
    return r.returncode == 0


def process_clip(src, dest, duration, idx):
    """
    - Coupe à `duration` secondes
    - Scale pour remplir 1080x1920 (crop centre depuis vidéo paysage)
    - Léger zoom cinématique
    - Fondu entrée/sortie
    - Aucun son
    """
    fade_d = 0.5
    # Le filtre :
    # 1. scale : hauteur forcée à 1920, largeur proportionnelle → ex: 3413px pour 16:9
    # 2. crop : découpe 1080px au centre
    # 3. zoompan : zoom très doux (1.0 à 1.04 sur la durée)
    # 4. fade in/out
    total_frames = int(duration * FPS)
    zoom_end   = 1.04
    zoom_speed = (zoom_end - 1.0) / total_frames

    vf = (
        f"scale=-1:{H}:flags=lanczos,"
        f"crop={W}:{H}:(iw-{W})/2:0,"
        f"zoompan=z='min(zoom+{zoom_speed:.6f},1.04)':d={total_frames}:s={W}x{H}:fps={FPS},"
        f"fade=t=in:st=0:d={fade_d},"
        f"fade=t=out:st={duration - fade_d}:d={fade_d}"
    )

    return run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-t", str(duration),
        "-vf", vf,
        "-an",                          # PAS de son
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "22",
        str(dest)
    ], f"Clip {idx} → vertical + zoom + fade")


def concat_clips(paths, output):
    lst = Path(tempfile.mktemp(suffix=".txt"))
    lst.write_text("".join(
        f"file '{Path(p).resolve().as_posix()}'\n" for p in paths
    ))
    return run([
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(lst),
        "-c", "copy",
        str(output)
    ], "Concatenation finale")


def main():
    if not MANIFEST_FILE.exists():
        print(f"Erreur : {MANIFEST_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    manifest = json.loads(MANIFEST_FILE.read_text())
    clips    = manifest["clips"]
    theme    = manifest.get("theme", "landscape")
    print(f"Thème : {theme.upper()} | {len(clips)} clips à traiter")

    WORK_DIR.mkdir(exist_ok=True)
    processed = []

    for clip in clips:
        src  = Path(clip["path"])
        if not src.exists():
            print(f"  ! {src} introuvable, ignoré")
            continue
        dur  = min(clip["duration"], MAX_CLIP)
        dest = WORK_DIR / f"proc_{clip['index']:03d}.mp4"
        ok   = process_clip(src, dest, dur, clip["index"])
        if ok and dest.exists() and dest.stat().st_size > 10_000:
            processed.append(dest)
            print(f"    OK ({dur}s)")
        else:
            print(f"    ! Clip {clip['index']} échoué")

    if not processed:
        print("Erreur : aucun clip traité.", file=sys.stderr)
        sys.exit(1)

    # Calcul durée totale
    total = sum(min(c["duration"], MAX_CLIP) for c in clips[:len(processed)])
    print(f"\n{len(processed)} clips traités, durée ~{total:.0f}s")

    if total < 60:
        print("Attention : vidéo < 60s", file=sys.stderr)

    print("Assemblage final...")
    ok = concat_clips(processed, OUTPUT_FILE)
    if not ok:
        sys.exit(1)

    print(f"\nDone : {OUTPUT_FILE} (~{total:.0f}s, format {W}x{H}, sans son)")


if __name__ == "__main__":
    main()
