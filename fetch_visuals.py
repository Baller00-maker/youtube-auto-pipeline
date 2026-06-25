"""
Étape 4c du pipeline : récupération des visuels
- Lit timing.json (segments avec texte + start/end, généré par transcribe.py)
- Appel LLM : génère une requête de recherche visuelle courte et pertinente pour CHAQUE segment
- Pour chaque segment, alterne entre Pexels Photos et Pexels Videos (mélange demandé)
- Télécharge les assets dans le dossier assets/
- Sauvegarde visuals.json : manifeste reliant chaque segment à son asset (type, chemin, durée)
  -> utilisé ensuite par l'étape de montage (assemble_video.py)
"""

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from openai import OpenAI

TIMING_FILE = Path("timing.json")
ASSETS_DIR = Path("assets")
OUTPUT_FILE = Path("visuals.json")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = "meta/llama-3.1-70b-instruct"

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY")
PEXELS_PHOTO_SEARCH = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"

# Regroupe les segments Whisper (souvent courts, ~3-6s) par paquets pour avoir
# une image/clip toutes les ~6-10 secondes plutôt qu'à chaque micro-segment.
SECONDS_PER_VISUAL = 7


def group_segments(segments, seconds_per_visual):
    """Fusionne les segments Whisper en blocs visuels d'environ N secondes."""
    if not segments:
        return []

    groups = []
    current = {"start": segments[0]["start"], "end": segments[0]["end"], "text": segments[0]["text"]}

    for seg in segments[1:]:
        if seg["end"] - current["start"] <= seconds_per_visual:
            current["end"] = seg["end"]
            current["text"] += " " + seg["text"]
        else:
            groups.append(current)
            current = {"start": seg["start"], "end": seg["end"], "text": seg["text"]}

    groups.append(current)
    return groups


def generate_visual_queries(client, groups):
    """Un seul appel LLM pour générer toutes les requêtes de recherche d'un coup
    (plus rapide et moins coûteux que N appels séparés)."""
    numbered_texts = "\n".join(f"{i}: {g['text'].strip()}" for i, g in enumerate(groups))

    prompt = f"""You are selecting stock footage/photo search queries for a military history documentary video.

Below is a numbered list of narration segments. For EACH numbered segment, give a short,
visually concrete search query (2-5 words) suitable for searching stock photo/video sites
like Pexels. Focus on concrete visual nouns (soldiers, tanks, explosions, maps, ruined city,
military aircraft, etc.), not abstract concepts.

SEGMENTS:
{numbered_texts}

Return ONLY a valid JSON array of strings, one query per segment, in the same order, same length
as the number of segments ({len(groups)}). No explanation, no markdown."""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5,
        max_tokens=2048,
    )
    text = response.choices[0].message.content.strip()
    text = re.sub(r"^```json\s*|\s*```$", "", text.strip())
    queries = json.loads(text)

    # Garde-fou : si le LLM ne renvoie pas exactement le bon nombre, on complète/tronque
    if len(queries) < len(groups):
        queries += ["military history"] * (len(groups) - len(queries))
    return queries[:len(groups)]


def search_pexels_photo(query):
    req = urllib.request.Request(
        f"{PEXELS_PHOTO_SEARCH}?query={urllib.parse.quote(query)}&per_page=1&orientation=landscape",
        headers={
            "Authorization": PEXELS_API_KEY,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    photos = data.get("photos", [])
    if not photos:
        return None
    return photos[0]["src"]["large2x"]


def search_pexels_video(query):
    req = urllib.request.Request(
        f"{PEXELS_VIDEO_SEARCH}?query={urllib.parse.quote(query)}&per_page=1&orientation=landscape",
        headers={
            "Authorization": PEXELS_API_KEY,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
    )
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())
    videos = data.get("videos", [])
    if not videos:
        return None
    # Choisit le fichier HD le plus proche de 1920x1080 disponible
    files = sorted(videos[0]["video_files"], key=lambda f: abs((f.get("width") or 0) - 1920))
    return files[0]["link"] if files else None


def download_file(url, dest_path):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
    )
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        out.write(resp.read())


def main():
    if not NVIDIA_API_KEY:
        print("Erreur : NVIDIA_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)
    if not PEXELS_API_KEY:
        print("Erreur : PEXELS_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)
    if not TIMING_FILE.exists():
        print(f"Erreur : {TIMING_FILE} introuvable. Lance d'abord transcribe.py.", file=sys.stderr)
        sys.exit(1)

    ASSETS_DIR.mkdir(exist_ok=True)

    with open(TIMING_FILE, "r", encoding="utf-8") as f:
        segments = json.load(f)

    groups = group_segments(segments, SECONDS_PER_VISUAL)
    print(f"{len(segments)} segments Whisper regroupés en {len(groups)} blocs visuels (~{SECONDS_PER_VISUAL}s chacun).")

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)
    print("Génération des requêtes de recherche visuelle (1 appel LLM)...")
    queries = generate_visual_queries(client, groups)

    manifest = []
    for i, (group, query) in enumerate(zip(groups, queries)):
        # Mélange demandé : on alterne image / vidéo (pair = image, impair = vidéo)
        use_video = (i % 2 == 1)
        asset_type = "video" if use_video else "image"
        print(f"  [{i + 1}/{len(groups)}] \"{query}\" ({asset_type})...")

        url = None
        try:
            url = search_pexels_video(query) if use_video else search_pexels_photo(query)
        except Exception as e:
            print(f"    ! Erreur de recherche : {e}", file=sys.stderr)

        # Repli : si rien trouvé dans le type choisi, on essaie l'autre type
        if not url:
            try:
                url = search_pexels_photo(query) if use_video else search_pexels_video(query)
                asset_type = "image" if use_video else "video"
            except Exception:
                pass

        if not url:
            print(f"    ! Aucun résultat pour \"{query}\", segment ignoré visuellement.", file=sys.stderr)
            continue

        ext = "mp4" if asset_type == "video" else "jpg"
        dest = ASSETS_DIR / f"segment_{i:03d}.{ext}"
        try:
            download_file(url, dest)
        except Exception as e:
            print(f"    ! Erreur de téléchargement : {e}", file=sys.stderr)
            continue

        manifest.append({
            "index": i,
            "start": group["start"],
            "end": group["end"],
            "duration": group["end"] - group["start"],
            "query": query,
            "type": asset_type,
            "path": str(dest),
        })

        time.sleep(0.5)  # ménage l'API gratuite Pexels (rate limit)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{len(manifest)} visuels téléchargés sur {len(groups)} blocs.")
    print(f"Manifeste sauvegardé : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
