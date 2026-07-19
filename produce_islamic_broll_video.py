"""
Pipeline B-roll Islamique Silencieux -- Production vidéo (qualité pro)

But : produire une vidéo verticale (TikTok/Reels/Shorts) SANS AUCUN SON,
composée uniquement de rush islamiques esthétiques (mosquées, calligraphie,
Kaaba, désert, ciel étoilé...), pensée pour être utilisée comme habillage
d'une vidéo de récital de Coran (l'audio de récitation sera ajouté à part,
au montage, par la personne qui poste).

RÈGLES D'OR :
  1. AUCUN SON. La vidéo est encodée sans piste audio (-an). Aucune musique,
     aucune voix, aucun bruit ajouté.
  2. AUCUN TEXTE / BANDEAU. Pas de titre, pas de sous-titre : la vidéo doit
     rester un rush pur, prêt à être réutilisé tel quel.
  3. Durée minimale d'une minute (configurable), avec une légère variation
     aléatoire à chaque génération pour éviter que toutes les vidéos aient
     exactement la même longueur.
  4. Anti-répétition : les clips utilisés sont mémorisés (islamic_broll_history.json)
     pour éviter de retomber sur les mêmes rush trop souvent d'une génération
     à l'autre.
  5. Rendu soigné, jamais "bizarre" : mêmes réglages cinéma que le pipeline
     de récitation (color grade chaud/doré, vignette légère, grain de film
     très subtil, coupes nettes entre les plans -- pas de zoompan/Ken Burns,
     qui a provoqué des écrans noirs sur certaines sources en framerate
     variable, donc volontairement écarté).

Format : vertical 1080x1920 (TikTok/Reels/Shorts)
"""

import json
import os
import random
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUTPUT_FILE  = Path("islamic_broll_video.mp4")
WORK_DIR     = Path("islamic_broll_work")
HISTORY_FILE = Path("islamic_broll_history.json")

PEXELS_API_KEY  = os.environ.get("PEXELS_API_KEY")
PEXELS_VIDEO    = "https://api.pexels.com/videos/search"
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")  # optionnel
PIXABAY_VIDEO   = "https://pixabay.com/api/videos/"
USER_AGENT      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

W, H = 1080, 1920
FPS  = 30

# Durée cible : minimum 60s, avec une variation aléatoire jusqu'à MAX pour
# que les vidéos générées ne soient pas toutes identiques en longueur.
MIN_DURATION = float(os.environ.get("MIN_DURATION_SECONDS", "60"))
MAX_DURATION = float(os.environ.get("MAX_DURATION_SECONDS", "90"))

# Nombre de générations sur lesquelles on évite de réutiliser un même clip
HISTORY_WINDOW = 25

# Requêtes pensées spécifiquement pour l'esthétique "récital de Coran" --
# mosquées, calligraphie, Kaaba, désert, lumière -- pas de rush générique
# hors sujet, pour éviter tout rendu "bizarre".
QUERIES = [
    # Mosquées / architecture islamique
    "mosque architecture islamic dome",
    "islamic architecture interior",
    "mosque minaret sunset",
    "mosque courtyard sunset",
    "medina mosque green dome",
    "mecca kaaba aerial",
    "grand mosque interior columns",
    "mosque dome sunlight",
    "islamic geometric pattern",
    "islamic geometric mandala pattern",
    "arabesque pattern gold",
    # Calligraphie / objets spirituels
    "quran book pages close up",
    "islamic calligraphy art",
    "prayer beads tasbih",
    "hands open dua prayer",
    "candle light peaceful",
    # Lumière / ciel
    "crescent moon night sky",
    "ramadan lantern night",
    "sunlight through window rays",
    "sunbeams through clouds",
    "golden hour light trees",
    # Nature contemplative (déserts/paysages spirituels)
    "desert golden sunset landscape",
    "desert dunes sunrise slow",
    "sand dunes desert wind",
    "clouds aerial drone above",
    # Espace et univers
    "stars milky way night timelapse",
    "galaxy nebula space",
    "moon night sky",
    "stars night sky timelapse",
]


# ─── UTILS ──────────────────────────────────────────────────────────────────

def run(cmd, desc="", check=True):
    if desc:
        print(f"  {desc}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 and check:
        print(f"  ! Erreur : {r.stderr[-500:]}", file=sys.stderr)
    return r.returncode == 0


def get_duration(path):
    r = subprocess.run([
        "ffprobe", "-v", "quiet", "-show_entries", "format=duration",
        "-of", "csv=p=0", str(path)
    ], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ─── HISTORIQUE ANTI-RÉPÉTITION ─────────────────────────────────────────────

def load_history():
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            return []
    return []


def save_history(history, used_urls):
    history.append({"urls": used_urls})
    history = history[-HISTORY_WINDOW:]
    HISTORY_FILE.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def recently_used_urls(history):
    used = set()
    for entry in history:
        used.update(entry.get("urls", []))
    return used


# ─── VIDEO CLIPS ────────────────────────────────────────────────────────────

def pexels_candidates(query, per_page=5):
    out = []
    try:
        url = (f"{PEXELS_VIDEO}?query={urllib.parse.quote(query)}"
               f"&per_page={per_page}&orientation=landscape")
        req = urllib.request.Request(url, headers={
            "Authorization": PEXELS_API_KEY, "User-Agent": USER_AGENT
        })
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        for video in data.get("videos", []):
            dur_v = video.get("duration", 0)
            if dur_v < 5:
                continue
            vfiles = video.get("video_files", [])
            landscape = [f for f in vfiles if f.get("width", 0) > f.get("height", 0)]
            pool = landscape if landscape else vfiles
            hd = [f for f in pool if f.get("width", 0) >= 1280]
            pool = hd if hd else pool
            if not pool:
                continue
            best = min(pool, key=lambda f: abs(f.get("width", 0) - 1920))
            link = best.get("link", "")
            if link:
                out.append((link, min(dur_v, 10)))
    except Exception as e:
        print(f"  ! Pexels erreur pour '{query}' : {e}", file=sys.stderr)
    return out


def pixabay_candidates(query, per_page=5):
    if not PIXABAY_API_KEY:
        return []
    out = []
    try:
        url = (f"{PIXABAY_VIDEO}?key={PIXABAY_API_KEY}"
               f"&q={urllib.parse.quote(query)}&per_page={per_page}"
               f"&video_type=film&safesearch=true")
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        for video in data.get("hits", []):
            dur_v = video.get("duration", 0)
            if dur_v < 5:
                continue
            videos = video.get("videos", {})
            for size in ["large", "medium", "small"]:
                v = videos.get(size)
                if v and v.get("width", 0) > v.get("height", 0) and v.get("url"):
                    out.append((v["url"], min(dur_v, 10)))
                    break
    except Exception as e:
        print(f"  ! Pixabay erreur pour '{query}' : {e}", file=sys.stderr)
    return out


def download_video(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as out:
        out.write(r.read())


def process_clip(src, dest, duration, idx):
    """
    Traitement cinématique d'un clip (identique au pipeline de récitation) :
    1. Scale/crop portrait 1080x1920
    2. Color grade chaud (dorés/spirituels)
    3. Vignette + grain film subtil
    4. Fade-in/out
    Pas de zoompan/Ken Burns : source de bug (écran noir) sur certains rush
    en framerate variable, volontairement écarté ici aussi.
    """
    color_grade = (
        "curves=r='0/0.03 0.5/0.52 1/1':"
        "g='0/0.02 0.5/0.50 1/0.97':"
        "b='0/0.01 0.5/0.47 1/0.88',"
        "hue=s=1.15,"
        "colorbalance=rs=0.05:gs=-0.02:bs=-0.08"
    )

    fade_out_start = max(duration - 0.4, 0.1)
    vf = (
        f"fps={FPS},"
        f"scale=-2:{H}:flags=lanczos,"
        f"crop={W}:{H}:(iw-{W})/2:0,"
        f"setsar=1,"
        f"{color_grade},"
        f"vignette=PI/5:mode=backward,"
        f"noise=alls=2:allf=t+u,"
        f"fade=t=in:st=0:d=0.4,"
        f"fade=t=out:st={fade_out_start:.2f}:d=0.4"
    )

    return run([
        "ffmpeg", "-y",
        "-i", str(src),
        "-t", str(duration),
        "-vf", vf,
        "-r", str(FPS),
        "-an",
        "-c:v", "libx264",
        "-preset", "slow",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(dest)
    ], f"Clip {idx} → color grade + vignette")


def build_silent_video(clip_paths, output):
    """Concatène tous les clips (coupes nettes) SANS aucune piste audio."""
    if len(clip_paths) == 1:
        return run(["ffmpeg", "-y", "-i", str(clip_paths[0]), "-an", "-c:v", "copy", str(output)],
                    "Piste vidéo (clip unique)")

    inputs = []
    for p in clip_paths:
        inputs += ["-i", str(p)]

    n = len(clip_paths)
    concat_inputs = "".join(f"[{i}:v]" for i in range(n))
    filter_str = f"{concat_inputs}concat=n={n}:v=1:a=0[vout]"

    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_str,
        "-map", "[vout]",
        "-an",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(output)
    ]
    return run(cmd, "Assemblage vidéo silencieuse (concat, coupes nettes)")


def trim_to_duration(src, dest, target_duration):
    """Coupe la vidéo pile à la durée cible (au cas où on aurait un peu trop de matière)."""
    return run([
        "ffmpeg", "-y", "-i", str(src),
        "-t", f"{target_duration:.2f}",
        "-c", "copy",
        str(dest)
    ], f"Coupe finale à {target_duration:.1f}s")


# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    if not PEXELS_API_KEY:
        print("Erreur : PEXELS_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)

    WORK_DIR.mkdir(exist_ok=True)

    target_duration = random.uniform(MIN_DURATION, MAX_DURATION)
    print(f"Durée cible : {target_duration:.1f}s (min {MIN_DURATION:.0f}s / max {MAX_DURATION:.0f}s)")

    history = load_history()
    excluded_urls = recently_used_urls(history)
    print(f"Historique : {len(excluded_urls)} clip(s) récemment utilisés, à éviter si possible")

    # 1. Recherche des rush -- marge 1.4x pour ne jamais manquer de matière
    print("\n[1/4] Recherche des rush islamiques (Pexels + Pixabay)...")
    needed = target_duration * 1.4
    clips_info = []      # (url, duration)
    used_urls = []
    idx = 0

    queries = QUERIES.copy()
    random.shuffle(queries)

    def collect(allow_reuse):
        nonlocal idx
        for query in queries:
            if sum(d for _, d in clips_info) >= needed:
                break
            candidates = pexels_candidates(query, per_page=4) + pixabay_candidates(query, per_page=4)
            random.shuffle(candidates)
            for url, dur_v in candidates:
                if sum(d for _, d in clips_info) >= needed:
                    break
                if not allow_reuse and url in excluded_urls:
                    continue
                if url in used_urls:
                    continue
                dest = WORK_DIR / f"raw_{idx:03d}.mp4"
                try:
                    print(f"    Téléchargement clip {idx} ({dur_v:.0f}s) -- '{query}'")
                    download_video(url, dest)
                    clips_info.append((dest, dur_v))
                    used_urls.append(url)
                    idx += 1
                except Exception as e:
                    print(f"    ! {e}", file=sys.stderr)
                time.sleep(0.3)

    collect(allow_reuse=False)
    if sum(d for _, d in clips_info) < needed:
        print("  Matière insuffisante en évitant l'historique -- on autorise la réutilisation.")
        collect(allow_reuse=True)

    if not clips_info:
        print("Erreur : aucun clip visuel téléchargé.", file=sys.stderr)
        sys.exit(1)

    # 2. Traitement cinématique
    print(f"\n[2/4] Traitement cinématique ({len(clips_info)} clips)...")
    processed_clips, processed_durs = [], []
    for i, (src, dur) in enumerate(clips_info):
        dest = WORK_DIR / f"proc_{i:03d}.mp4"
        if process_clip(src, dest, dur, i) and dest.exists() and dest.stat().st_size > 5000:
            processed_clips.append(dest)
            processed_durs.append(dur)
            print(f"    Clip {i} OK ({dur:.0f}s)")

    if not processed_clips:
        print("Erreur : aucun clip traité.", file=sys.stderr)
        sys.exit(1)

    # Si le total est encore trop court, on boucle sur les clips déjà traités
    i = 0
    while sum(processed_durs) < target_duration + 1.0:
        processed_clips.append(processed_clips[i % len(processed_clips)])
        processed_durs.append(processed_durs[i % len(processed_durs)])
        i += 1

    # 3. Assemblage silencieux
    print(f"\n[3/4] Assemblage vidéo silencieuse ({len(processed_clips)} clips, coupes nettes)...")
    silent_video = WORK_DIR / "silent_video.mp4"
    if not build_silent_video(processed_clips, silent_video):
        print("Erreur lors de l'assemblage vidéo.", file=sys.stderr)
        sys.exit(1)

    # 4. Coupe finale pile à la durée cible
    print("\n[4/4] Coupe finale...")
    total_dur = get_duration(silent_video)
    if total_dur > target_duration + 0.5:
        if not trim_to_duration(silent_video, OUTPUT_FILE, target_duration):
            OUTPUT_FILE.write_bytes(silent_video.read_bytes())
    else:
        OUTPUT_FILE.write_bytes(silent_video.read_bytes())

    save_history(history, used_urls)

    final_dur = get_duration(OUTPUT_FILE)
    print(f"\n✅ Vidéo finale : {OUTPUT_FILE}")
    print(f"   Durée : {final_dur:.1f}s ({int(final_dur)//60}m{int(final_dur)%60:02d}s)")
    print(f"   Résolution : {W}x{H} | FPS : {FPS} | CRF : 18 (haute qualité)")
    print(f"   Audio : AUCUN (vidéo silencieuse)")
    print(f"   Effets vidéo : color grade doré + coupes nettes + vignette + grain")
    print(f"   Clips utilisés : {len(used_urls)}")


if __name__ == "__main__":
    main()
