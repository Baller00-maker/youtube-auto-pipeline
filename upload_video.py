"""
Étape 6 du pipeline : upload YouTube
- Lit script.json (pour le titre/sujet) et final_video.mp4 (vidéo montée)
- Authentifie via OAuth (refresh token déjà généré une fois en local)
- Upload la vidéo en visibilité "unlisted" (non répertorié) -- PAS public --
  pour permettre une validation humaine rapide avant publication réelle.
  L'utilisateur passe ensuite la vidéo en "Public" manuellement sur YouTube Studio
  une fois le contenu vérifié (précision historique notamment).
"""

import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCRIPT_FILE = Path("script.json")
VIDEO_FILE = Path("final_video.mp4")

CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN")

# Visibilité par défaut : "unlisted" tant que la validation manuelle n'est pas
# pleinement automatisée -- décision volontaire pour protéger la chaîne et
# vérifier la précision historique avant publication réelle.
PRIVACY_STATUS = "unlisted"


def get_credentials():
    return Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
    )


def build_metadata(data):
    topic = data["topic"]
    title = topic if len(topic) <= 95 else topic[:92] + "..."

    description = (
        f"{topic}\n\n"
        "A look back at one of history's defining military events.\n\n"
        "#history #militaryhistory #documentary"
    )

    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["military history", "history documentary", "war history"],
            "categoryId": "27",  # Education
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }


def main():
    missing = [name for name, val in [
        ("YOUTUBE_CLIENT_ID", CLIENT_ID),
        ("YOUTUBE_CLIENT_SECRET", CLIENT_SECRET),
        ("YOUTUBE_REFRESH_TOKEN", REFRESH_TOKEN),
    ] if not val]
    if missing:
        print(f"Erreur : variables manquantes : {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    for required in (SCRIPT_FILE, VIDEO_FILE):
        if not required.exists():
            print(f"Erreur : {required} introuvable.", file=sys.stderr)
            sys.exit(1)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("Authentification YouTube...")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    metadata = build_metadata(data)
    print(f"Titre : {metadata['snippet']['title']}")
    print(f"Visibilité : {PRIVACY_STATUS} (validation manuelle requise avant publication)")

    print(f"\nUpload de {VIDEO_FILE} en cours (peut prendre plusieurs minutes selon ta connexion)...")
    media = MediaFileUpload(str(VIDEO_FILE), chunksize=-1, resumable=True, mimetype="video/mp4")

    request = youtube.videos().insert(
        part="snippet,status",
        body=metadata,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Progression : {int(status.progress() * 100)}%")

    video_id = response["id"]
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    print(f"\nUpload terminé !")
    print(f"URL (non répertorié, à valider) : {video_url}")
    print("Va sur YouTube Studio pour vérifier le contenu, puis passe la vidéo en 'Public' manuellement.")


if __name__ == "__main__":
    main()
