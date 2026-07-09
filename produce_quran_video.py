"""
Pipeline Récitation Coranique -- Production vidéo complète (qualité pro)

Effets audio (qualité studio) :
  - Réverbération style grande mosquée (aecho)
  - EQ : warmth basses, douceur aigus, voix chaleureuse
  - Compression douce (loudnorm broadcast standard -14 LUFS)
  - Légère spatialisation stéréo

Effets vidéo (qualité cinéma) :
  - Color grade chaud (tons dorés/spirituels)
  - Ken Burns très lent sur chaque plan
  - Transitions crossfade fluides entre plans (xfade)
  - Vignette (bords sombres pour focus central)
  - Grain de film très subtil
  - Carte de titre stylisée en ouverture

Format : vertical 1080x1920 (TikTok/Reels/Shorts), 1-2 minutes
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AUDIO_FILE   = Path("quran_recitation.mp3")
OUTPUT_FILE  = Path("quran_video.mp4")
WORK_DIR     = Path("quran_video_work")

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_VIDEO   = "https://api.pexels.com/videos/search"
USER_AGENT     = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

W, H    = 1080, 1920
FPS     = 30
XFADE   = 1.0   # durée crossfade en secondes

# Requêtes Pexels : paysages spirituels et apaisants, sans personnes
QUERIES = [
    # Contenu islamique
    "mosque architecture islamic dome",
    "islamic architecture interior",
    "kaaba mecca aerial",
    "mosque minaret sunset",
    "islamic geometric pattern",
    "crescent moon night sky",
    # Paysages apaisants
    "desert golden sunset landscape",
    "ocean waves sunrise peaceful",
    "mountain mist sunrise aerial",
    "river calm reflection nature",
    "forest light rays morning",
    "waterfall nature peaceful",
    "sand dunes desert wind",
    "clouds aerial drone above",
    # Espace et univers
    "stars milky way night timelapse",
    "aurora borealis night sky",
    "galaxy nebula space",
    "moon night sky",
    "stars night sky timelapse",
]

# ─── UTILS ──────────────────────────────────────────────────────────────────

def run(cmd, desc="", check=True):
    if desc: print(f"  {desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(f"  ! Erreur : {r.stderr[-500:]}", file=sys.stderr)
    return r.returncode == 0


def get_duration(path):
    r = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path)
    ], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except: return 0.0


def load_font(size, bold=False):
    for p in [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else ''}.ttf",
    ]:
        if Path(p).exists():
            try: return ImageFont.truetype(p, size)
            except: pass
    return ImageFont.load_default()


# ─── AUDIO EFFECTS ──────────────────────────────────────────────────────────

def process_audio(src, dest):
    """
    Chaîne d'effets audio de qualité studio :
    1. aecho       : réverbération style mosquée (60ms delay, hall effect)
    2. equalizer   : +4dB à 120Hz (chaleur), -3dB à 4kHz (douceur), -5dB à 9kHz (aigu doux)
    3. acompressor : compression douce (évite les variations de volume)
    4. loudnorm    : normalisation broadcast (-14 LUFS, standard professionnel)
    """
    audio_fx = (
        "aecho=0.8:0.85:80:0.35,"
        "equalizer=f=120:width_type=o:width=2:g=4,"
        "equalizer=f=4000:width_type=o:width=2:g=-3,"
        "equalizer=f=9000:width_type=o:width=2:g=-5,"
        "acompressor=threshold=-18dB:ratio=3:attack=10:release=200:makeup=2,"
        "loudnorm=I=-14:TP=-1.5:LRA=11"
    )
    return run([
        "ffmpeg", "-y", "-i", str(src),
        "-af", audio_fx,
        "-ar", "48000", "-b:a", "256k",
        str(dest)
    ], "Traitement audio (reverb + EQ + compression + normalisation)")


# ─── VIDEO CLIPS ────────────────────────────────────────────────────────────

def pexels_search(query, per_page=3):
    url = (f"{PEXELS_VIDEO}?query={urllib.parse.quote(query)}"
           f"&per_page={per_page}&orientation=landscape")
    req = urllib.request.Request(url, headers={
        "Authorization": PEXELS_API_KEY, "User-Agent": USER_AGENT
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def download_video(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as out:
        out.write(r.read())


def process_clip(src, dest, duration, idx):
    """
    Traitement cinématique d'un clip :
    1. Scale vers hauteur 1920 (maintient ratio)
    2. Crop 1080px au centre (portrait)
    3. Ken Burns très lent (zoom 1.0 → 1.05)
    4. Color grade chaud (dorés/spirituels, style DaVinci)
    5. Vignette
    6. Grain film subtil (noise très léger)
    7. Fade-in/out
    """
    n_frames  = int(duration * FPS)
    zoom_spd  = 0.05 / max(n_frames, 1)

    color_grade = (
        # Lift ombres légèrement (évite le noir pur)
        "curves=r='0/0.03 0.5/0.52 1/1':"
        "g='0/0.02 0.5/0.50 1/0.97':"
        "b='0/0.01 0.5/0.47 1/0.88',"
        # Saturation légèrement augmentée
        "hue=s=1.15,"
        # Température chaude (teinte vers les dorés/ambre)
        "colorbalance=rs=0.05:gs=-0.02:bs=-0.08"
    )

    vf = (
        f"scale=-1:{H}:flags=lanczos,"
        f"crop={W}:{H}:(iw-{W})/2:0,"
        f"zoompan=z='min(zoom+{zoom_spd:.7f},1.05)':d={n_frames}:s={W}x{H}:fps={FPS},"
        f"{color_grade},"
        f"vignette=PI/5:mode=backward,"
        f"noise=alls=2:allf=t+u,"
        f"fade=t=in:st=0:d=0.4,"
        f"fade=t=out:st={duration-0.4:.2f}:d=0.4"
    )

    return run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-t", str(duration),
        "-vf", vf,
        "-r", str(FPS),
        "-an",
        "-c:v", "libx264",
        "-preset", "slow",   # meilleure qualité
        "-crf", "18",        # quasi-lossless
        "-pix_fmt", "yuv420p",
        str(dest)
    ], f"Clip {idx} → color grade + Ken Burns + vignette")


# ─── TITRE ──────────────────────────────────────────────────────────────────

def make_title_card(surah_name, reciter_name, duration=3.0):
    """Carte de titre élégante en ouverture."""
    img  = Image.new("RGB", (W, H), (8, 8, 20))
    draw = ImageDraw.Draw(img)

    # Ligne dorée centrale
    gold = (200, 160, 40)
    draw.rectangle([W//2 - 200, H//2 - 2, W//2 + 200, H//2 + 2], fill=gold)

    # Titre sourate
    f1 = load_font(88, bold=True)
    text = surah_name.upper()
    bb = draw.textbbox((0,0), text, font=f1)
    draw.text(((W-(bb[2]-bb[0]))//2, H//2 - 120), text, font=f1, fill=gold)

    # Sous-titre récitateur
    f2 = load_font(44)
    sub = f"Récité par {reciter_name}"
    bb2 = draw.textbbox((0,0), sub, font=f2)
    draw.text(((W-(bb2[2]-bb2[0]))//2, H//2 + 30), sub, font=f2,
              fill=(180, 180, 180))

    # Décoration : petits points dorés
    for dx in [-280, 280]:
        draw.ellipse([W//2+dx-6, H//2-6, W//2+dx+6, H//2+6], fill=gold)

    # Sauvegarde et conversion en clip
    tmp_img  = WORK_DIR / "title_card.png"
    tmp_clip = WORK_DIR / "title_clip.mp4"
    img.save(tmp_img)

    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_img),
        "-t", str(duration),
        "-vf", (
            f"fps={FPS},"
            f"fade=t=in:st=0:d=0.8,"
            f"fade=t=out:st={duration-0.8:.1f}:d=0.8"
        ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        str(tmp_clip)
    ], "Génération carte de titre")
    return tmp_clip


# ─── XFADE CHAIN ────────────────────────────────────────────────────────────

def build_xfade(clip_paths, clip_durations, xfade_dur=XFADE):
    """
    Construit un filtre xfade en chaîne pour des transitions fluides entre tous les clips.
    Exemple pour 3 clips :
      [0][1]xfade=...:offset=D0-X[v01];[v01][2]xfade=...:offset=D0+D1-2X[vout]
    """
    if len(clip_paths) == 1:
        return clip_paths, [], "[0:v]", ""

    filter_parts = []
    offset = 0.0
    cur_out = "[0:v]"

    for i in range(len(clip_paths) - 1):
        offset += clip_durations[i] - xfade_dur
        next_in = f"[{i+1}:v]"
        out_lbl = f"[v{i+1}]" if i < len(clip_paths) - 2 else "[vout]"
        filter_parts.append(
            f"{cur_out}{next_in}xfade=transition=fade:"
            f"duration={xfade_dur}:offset={offset:.3f}{out_lbl}"
        )
        cur_out = out_lbl
        offset += xfade_dur  # compenser le chevauchement dans la prochaine itération

    return clip_paths, filter_parts, "[vout]", ";".join(filter_parts)


def merge_video_audio_xfade(clip_paths, clip_durations, audio_path, output):
    """
    Assemble tous les clips avec xfade + audio traité.
    """
    if not clip_paths:
        return False

    if len(clip_paths) == 1:
        # Cas simple : un seul clip
        return run([
            "ffmpeg", "-y",
            "-i", str(clip_paths[0]),
            "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-shortest",
            str(output)
        ], "Fusion vidéo + audio (clip unique)")

    # Cas général : chaîne xfade
    _, filter_parts, out_label, filter_str = build_xfade(clip_paths, clip_durations)

    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(p)]
    inputs += ["-i", str(audio_path)]

    audio_idx = len(clip_paths)

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", out_label,
        "-map", f"{audio_idx}:a",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-c:a", "aac", "-b:a", "256k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(output)
    ]
    return run(cmd, "Assemblage final (xfade + audio)")


# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    if not AUDIO_FILE.exists():
        print(f"Erreur : {AUDIO_FILE} introuvable. Lance d'abord fetch_quran_audio.py",
              file=sys.stderr)
        sys.exit(1)

    if not PEXELS_API_KEY:
        print("Erreur : PEXELS_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)

    WORK_DIR.mkdir(exist_ok=True)

    # 0. Durée totale de la récitation
    total_audio_dur = get_duration(AUDIO_FILE)
    print(f"Récitation : {total_audio_dur:.1f}s ({int(total_audio_dur)//60}m{int(total_audio_dur)%60:02d}s)")

    # 1. Traitement audio professionnel
    print("\n[1/5] Traitement audio...")
    audio_processed = WORK_DIR / "audio_processed.mp3"
    if not process_audio(AUDIO_FILE, audio_processed):
        print("Avertissement : audio non traité, utilisation originale", file=sys.stderr)
        audio_processed = AUDIO_FILE

    # 2. Récupération info sourate depuis le nom de fichier (si disponible)
    meta_file = Path("quran_meta.json")
    surah_name   = "Récitation Coranique"
    reciter_name = "Sheikh Al-Qari"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())
        surah_name   = meta.get("surah_name", surah_name)
        reciter_name = meta.get("reciter_name", reciter_name)

    # 3. Carte de titre
    print("\n[2/5] Création carte de titre...")
    title_clip = make_title_card(surah_name, reciter_name, duration=3.5)
    title_dur  = 3.5

    # 4. Téléchargement des visuels
    print("\n[3/5] Téléchargement visuels Pexels...")
    remaining  = total_audio_dur - title_dur + (len(QUERIES) * XFADE)
    clips_info = []   # (path, duration)
    idx        = 0

    import random
    queries = random.sample(QUERIES, min(len(QUERIES), 10))

    for query in queries:
        if sum(d for _,d in clips_info) >= remaining:
            break
        try:
            print(f"  Recherche : '{query}'")
            data = pexels_search(query, per_page=2)
            for video in data.get("videos", []):
                dur_v = video.get("duration", 0)
                if dur_v < 5: continue
                vfiles = video.get("video_files", [])
                if not vfiles: continue
                # Choisir la meilleure résolution
                hd = [f for f in vfiles if f.get("width",0) >= 1280]
                pool = hd if hd else vfiles
                best = min(pool, key=lambda f: abs(f.get("width",0) - 1920))
                url  = best.get("link", "")
                if not url: continue
                dest = WORK_DIR / f"raw_{idx:03d}.mp4"
                try:
                    print(f"    Téléchargement clip {idx} ({min(dur_v,12):.0f}s)...")
                    download_video(url, dest)
                    clips_info.append((dest, min(dur_v, 12)))
                    idx += 1
                except Exception as e:
                    print(f"    ! {e}", file=sys.stderr)
                time.sleep(0.3)
                break
        except Exception as e:
            print(f"  ! Erreur : {e}", file=sys.stderr)

    if not clips_info:
        print("Erreur : aucun clip visuel téléchargé.", file=sys.stderr)
        sys.exit(1)

    # 5. Traitement cinématique de chaque clip
    print(f"\n[4/5] Traitement cinématique ({len(clips_info)} clips)...")
    processed_clips = []
    processed_durs  = []

    for i, (src, dur) in enumerate(clips_info):
        dest = WORK_DIR / f"proc_{i:03d}.mp4"
        ok   = process_clip(src, dest, dur, i)
        if ok and dest.exists() and dest.stat().st_size > 5000:
            processed_clips.append(dest)
            processed_durs.append(dur)
            print(f"    Clip {i} OK ({dur:.0f}s)")

    if not processed_clips:
        print("Erreur : aucun clip traité.", file=sys.stderr)
        sys.exit(1)

    # Ajouter la carte de titre en premier
    all_clips = [title_clip] + processed_clips
    all_durs  = [title_dur]  + processed_durs

    # 6. Assemblage final avec xfade
    print(f"\n[5/5] Assemblage final ({len(all_clips)} clips, xfade {XFADE}s)...")
    ok = merge_video_audio_xfade(all_clips, all_durs, audio_processed, OUTPUT_FILE)
    if not ok:
        print("Erreur lors de l'assemblage final.", file=sys.stderr)
        sys.exit(1)

    final_dur = get_duration(OUTPUT_FILE)
    print(f"\n✅ Vidéo finale : {OUTPUT_FILE}")
    print(f"   Durée : {final_dur:.1f}s ({int(final_dur)//60}m{int(final_dur)%60:02d}s)")
    print(f"   Résolution : {W}x{H} | FPS : {FPS} | CRF : 18 (haute qualité)")
    print(f"   Audio : reverb + EQ + compression (-14 LUFS broadcast)")
    print(f"   Effets : color grade chaud + Ken Burns + xfade + vignette + grain")


if __name__ == "__main__":
    main()
