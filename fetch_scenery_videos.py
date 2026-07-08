"""
Pipeline Paysages/Espace -- Étape 1 : téléchargement des vidéos
- Alterne aléatoirement entre thème "paysages" et thème "espace"
- Recherche Pexels avec des requêtes soigneusement choisies pour éviter les personnes
- Télécharge 14-16 clips (5-12s chacun) pour avoir >1 minute au total
- Sauvegarde les clips dans scenery_assets/ + scenery_manifest.json
"""

import json
import os
import random
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_VIDEO   = "https://api.pexels.com/videos/search"
ASSETS_DIR     = Path("scenery_assets")
MANIFEST_FILE  = Path("scenery_manifest.json")
USER_AGENT     = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

TARGET_DURATION = 75   # secondes minimum de contenu
MIN_CLIP        = 5    # durée minimale d'un clip (secondes)
MAX_CLIP        = 14   # durée maximale d'un clip

# Requêtes soigneusement sélectionnées — paysages et espace, jamais de personnes
LANDSCAPE_QUERIES = [
    "mountain lake reflection timelapse",
    "ocean waves sunset aerial",
    "waterfall forest nature",
    "desert sand dunes aerial drone",
    "northern lights aurora borealis",
    "volcano lava eruption",
    "canyon aerial view",
    "glacier arctic ice",
    "tropical underwater coral reef",
    "savanna wildlife sunset",
    "forest aerial drone",
    "river valley mist",
    "storm lightning nature",
    "snow mountain peak clouds",
    "tropical beach waves no people",
    "lake reflection mountains timelapse",
]

SPACE_QUERIES = [
    "galaxy milky way stars timelapse",
    "nebula space cosmos",
    "earth from space orbit",
    "aurora borealis night sky timelapse",
    "meteor shower night sky",
    "telescope stars space",
    "universe deep space",
    "moon crescent night",
    "starry night sky timelapse",
    "solar eclipse",
    "clouds earth aerial from above",
    "sunrise from space",
    "planet earth blue marble",
    "cosmic night sky stars",
    "space station orbit earth",
]

THEME_FILE = Path("scenery_last_theme.txt")


def pick_theme():
    """Alterne entre paysages et espace."""
    if THEME_FILE.exists():
        last = THEME_FILE.read_text().strip()
        theme = "space" if last == "landscape" else "landscape"
    else:
        theme = random.choice(["landscape", "space"])
    THEME_FILE.write_text(theme)
    return theme


def pexels_search(query, per_page=5):
    url = (f"{PEXELS_VIDEO}?query={urllib.parse.quote(query)}"
           f"&per_page={per_page}&orientation=landscape&size=medium")
    req = urllib.request.Request(url, headers={
        "Authorization": PEXELS_API_KEY,
        "User-Agent": USER_AGENT,
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def best_video_file(video_files):
    """Choisit le meilleur fichier : résolution proche de 1920x1080, pas trop lourd."""
    hd = [f for f in video_files if f.get("width", 0) >= 1280]
    pool = hd if hd else video_files
    return min(pool, key=lambda f: abs((f.get("width", 0)) - 1920))


def download(url, dest, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as out:
        out.write(r.read())


def main():
    if not PEXELS_API_KEY:
        print("Erreur : PEXELS_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)

    ASSETS_DIR.mkdir(exist_ok=True)

    theme = pick_theme()
    queries = LANDSCAPE_QUERIES if theme == "landscape" else SPACE_QUERIES
    print(f"Thème : {theme.upper()}")

    # Mélange les requêtes et en prend 10 pour varier
    selected = random.sample(queries, min(10, len(queries)))
    print(f"Requêtes sélectionnées : {selected}")

    clips = []
    total_dur = 0
    idx = 0

    for query in selected:
        if total_dur >= TARGET_DURATION:
            break
        print(f"  Recherche : '{query}'...")
        try:
            data = pexels_search(query, per_page=4)
            videos = data.get("videos", [])
        except Exception as e:
            print(f"  ! Erreur recherche : {e}", file=sys.stderr)
            continue

        for video in videos:
            dur = video.get("duration", 0)
            if dur < MIN_CLIP or dur > MAX_CLIP * 3:
                continue
            # Vérification : pas de tags "people", "person", "woman", "man", "girl", "boy"
            tags = [t.get("title","").lower() for t in video.get("tags", [])]
            excluded = {"people","person","woman","man","girl","boy","female","male","human","face"}
            if any(t in excluded for t in tags):
                print(f"    Skipped (personnes détectées)")
                continue

            vfiles = video.get("video_files", [])
            if not vfiles:
                continue
            best = best_video_file(vfiles)
            url  = best.get("link")
            if not url:
                continue

            dest = ASSETS_DIR / f"clip_{idx:03d}.mp4"
            try:
                print(f"    Téléchargement clip {idx} ({min(dur, MAX_CLIP)}s)...")
                download(url, dest)
                clip_dur = min(dur, MAX_CLIP)
                clips.append({
                    "index":    idx,
                    "path":     str(dest),
                    "duration": clip_dur,
                    "query":    query,
                    "pexels_id": video.get("id"),
                })
                total_dur += clip_dur
                idx += 1
            except Exception as e:
                print(f"    ! Erreur download : {e}", file=sys.stderr)

            time.sleep(0.4)
            if total_dur >= TARGET_DURATION:
                break

    if not clips:
        print("Erreur : aucun clip téléchargé.", file=sys.stderr)
        sys.exit(1)

    manifest = {"theme": theme, "clips": clips, "total_duration": total_dur}
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\n{len(clips)} clips ({total_dur:.0f}s). Manifeste : {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
