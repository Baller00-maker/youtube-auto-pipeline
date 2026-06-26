"""
Étape 1 du pipeline : collecte de la vidéo de référence
- Récupère les 10 dernières vidéos de la chaîne cible
- Sélectionne celle qui a le plus de vues
- Extrait sa transcription (sous-titres auto)
- Sauvegarde le résultat dans reference.json pour l'étape suivante (analyse de style)
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

CHANNEL_URL = "https://www.youtube.com/@TheMilitaryShow/videos"
NUM_VIDEOS_TO_CHECK = 10


YT_DLP_CMD = [sys.executable, "-m", "yt_dlp"]
TMP_DIR = tempfile.gettempdir()


def run_yt_dlp_json(url, extra_args=None):
    """Exécute yt-dlp et retourne la sortie JSON (une ligne JSON par vidéo en mode flat)."""
    cmd = YT_DLP_CMD + ["--flat-playlist", "-J", url]
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_recent_video_ids(channel_url, limit):
    """Liste les IDs des dernières vidéos de la chaîne (sans télécharger)."""
    cmd = YT_DLP_CMD + [
        "--flat-playlist",
        "--playlist-end", str(limit),
        "-J",
        channel_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    entries = data.get("entries", [])
    return [entry["id"] for entry in entries if entry.get("id")]


def get_video_details(video_id):
    """Récupère les métadonnées complètes (dont view_count) pour une vidéo donnée."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = YT_DLP_CMD + ["-J", "--no-warnings", url]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def get_transcript(video_id):
    """Télécharge les sous-titres auto (anglais) en VTT, les lit, et nettoie le texte."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_template = str(Path(TMP_DIR) / f"{video_id}.%(ext)s")
    cmd = YT_DLP_CMD + [
        "--write-auto-sub",
        "--sub-lang", "en",
        "--skip-download",
        "--sub-format", "vtt",
        "-o", out_template,
        url,
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)

    vtt_path = str(Path(TMP_DIR) / f"{video_id}.en.vtt")
    try:
        with open(vtt_path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        return None

    # Nettoyage basique du VTT : on garde uniquement les lignes de texte (pas les timecodes)
    lines = raw.splitlines()
    text_lines = []
    seen = set()
    for line in lines:
        line = line.strip()
        if not line or "-->" in line or line.startswith("WEBVTT") or line.isdigit():
            continue
        # Supprime les tags type <c> et les doublons consécutifs (fréquents dans les auto-sub)
        cleaned = line.replace("<c>", "").replace("</c>", "")
        if cleaned and cleaned not in seen:
            text_lines.append(cleaned)
            seen.add(cleaned)

    return " ".join(text_lines)


def main():
    print(f"Récupération des {NUM_VIDEOS_TO_CHECK} dernières vidéos de {CHANNEL_URL}...")
    video_ids = get_recent_video_ids(CHANNEL_URL, NUM_VIDEOS_TO_CHECK)
    print(f"IDs trouvés : {video_ids}")

    candidates = []
    for vid in video_ids:
        try:
            details = get_video_details(vid)
            candidates.append({
                "id": vid,
                "title": details.get("title"),
                "view_count": details.get("view_count", 0),
                "duration": details.get("duration"),
            })
            print(f"  - {vid} | {details.get('title')} | vues: {details.get('view_count')}")
        except subprocess.CalledProcessError as e:
            print(f"  ! Erreur sur {vid}, ignorée : {e.stderr.strip()[-500:]}", file=sys.stderr)

    if not candidates:
        print("Aucune vidéo récupérée, arrêt.", file=sys.stderr)
        sys.exit(1)

    best = max(candidates, key=lambda c: c["view_count"])
    print(f"\nVidéo retenue (la plus vue) : {best['title']} ({best['view_count']} vues)")

    transcript = get_transcript(best["id"])
    if not transcript:
        print("Transcription introuvable pour cette vidéo, arrêt.", file=sys.stderr)
        sys.exit(1)

    output = {
        "video_id": best["id"],
        "title": best["title"],
        "view_count": best["view_count"],
        "duration": best["duration"],
        "transcript": transcript,
    }

    with open("reference.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nTranscription sauvegardée dans reference.json ({len(transcript)} caractères).")


if __name__ == "__main__":
    main()
