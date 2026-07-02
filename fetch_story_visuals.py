"""
Pipeline "Histoires dramatiques" -- Étape 3 : visuels Pexels
- Lit story_script.json (scènes avec pexels_query)
- Alterne images fixes et clips vidéo Pexels (mélange cinématographique)
- Format vertical prioritaire, recadrage automatique si besoin
- Sauvegarde story_assets/ + story_visuals.json
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_FILE = Path("story_script.json")
ASSETS_DIR = Path("story_assets")
OUTPUT_FILE = Path("story_visuals.json")

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY") if "os" in dir() else None

import os
PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")

PEXELS_PHOTO_SEARCH = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def pexels_request(url):
    req = urllib.request.Request(
        url,
        headers={"Authorization": PEXELS_API_KEY, "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def search_photo(query):
    data = pexels_request(f"{PEXELS_PHOTO_SEARCH}?query={urllib.parse.quote(query)}&per_page=3&orientation=portrait")
    photos = data.get("photos", [])
    return photos[0]["src"]["large2x"] if photos else None


def search_video(query):
    data = pexels_request(f"{PEXELS_VIDEO_SEARCH}?query={urllib.parse.quote(query)}&per_page=3&orientation=portrait")
    videos = data.get("videos", [])
    if not videos:
        return None
    files = sorted(videos[0]["video_files"], key=lambda f: abs((f.get("height") or 0) - 1920))
    return files[0]["link"] if files else None


def download_file(url, dest_path):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out:
        out.write(resp.read())


def main():
    if not PEXELS_API_KEY:
        print("Erreur : PEXELS_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)
    if not SCRIPT_FILE.exists():
        print(f"Erreur : {SCRIPT_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        story = json.load(f)

    ASSETS_DIR.mkdir(exist_ok=True)
    scenes = story["scenes"]
    manifest = []

    for i, scene in enumerate(scenes):
        query = scene["pexels_query"]
        use_video = (i % 2 == 1)
        asset_type = "video" if use_video else "image"
        print(f"[{i+1}/{len(scenes)}] {asset_type} : {query}")

        url = None
        try:
            url = search_video(query) if use_video else search_photo(query)
        except Exception as e:
            print(f"  ! Erreur recherche : {e}", file=sys.stderr)

        if not url:
            try:
                url = search_photo(query) if use_video else search_video(query)
                asset_type = "image" if use_video else "video"
            except Exception:
                pass

        if not url:
            print(f"  ! Aucun résultat pour '{query}', scène ignorée.", file=sys.stderr)
            continue

        ext = "mp4" if asset_type == "video" else "jpg"
        dest = ASSETS_DIR / f"story_scene_{i:02d}.{ext}"
        try:
            download_file(url, dest)
        except Exception as e:
            print(f"  ! Erreur téléchargement : {e}", file=sys.stderr)
            continue

        manifest.append({
            "index": i,
            "narration_fr": scene["narration_fr"],
            "query": query,
            "type": asset_type,
            "path": str(dest),
        })
        time.sleep(0.5)

    if not manifest:
        print("Erreur : aucun visuel téléchargé.", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\n{len(manifest)}/{len(scenes)} visuels téléchargés.")
    print(f"Manifeste : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
