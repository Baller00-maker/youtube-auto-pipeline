"""
Pipeline "Histoires dramatiques" -- Étape 6 : upload YouTube Shorts
- Upload story_final.mp4 sur le compte YouTube dédié aux histoires
- Utilise des secrets séparés : STORY_YOUTUBE_CLIENT_ID, STORY_YOUTUBE_CLIENT_SECRET,
  STORY_YOUTUBE_REFRESH_TOKEN (pour ne pas mélanger avec la chaîne Military)
- Visibilité : unlisted (validation manuelle avant publication)
"""

import json
import os
import sys
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCRIPT_FILE = Path("story_script.json")
VIDEO_FILE = Path("story_final.mp4")

CLIENT_ID = os.environ.get("STORY_YOUTUBE_CLIENT_ID")
CLIENT_SECRET = os.environ.get("STORY_YOUTUBE_CLIENT_SECRET")
REFRESH_TOKEN = os.environ.get("STORY_YOUTUBE_REFRESH_TOKEN")

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
    title = data.get("title", data.get("topic", "Histoire"))
    title = f"{title} #Shorts"[:95]
    description = (
        f"{data.get('title', '')}\n\n"
        "Une histoire vraie de famille, de trahison et de secrets.\n\n"
        "#shorts #histoire #famille #drame #storytime"
    )
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": ["histoire", "famille", "drame", "shorts", "storytime", "trahison"],
            "categoryId": "24",
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "selfDeclaredMadeForKids": False,
        },
    }


def main():
    missing = [n for n, v in [
        ("STORY_YOUTUBE_CLIENT_ID", CLIENT_ID),
        ("STORY_YOUTUBE_CLIENT_SECRET", CLIENT_SECRET),
        ("STORY_YOUTUBE_REFRESH_TOKEN", REFRESH_TOKEN),
    ] if not v]
    if missing:
        print(f"Erreur : secrets manquants : {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    for f in (SCRIPT_FILE, VIDEO_FILE):
        if not f.exists():
            print(f"Erreur : {f} introuvable.", file=sys.stderr)
            sys.exit(1)

    with open(SCRIPT_FILE, encoding="utf-8") as f:
        data = json.load(f)

    print("Authentification YouTube (compte histoires)...")
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)
    metadata = build_metadata(data)
    print(f"Titre : {metadata['snippet']['title']}")

    media = MediaFileUpload(str(VIDEO_FILE), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=metadata, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"  Progression : {int(status.progress() * 100)}%")

    print(f"\nUpload terminé ! https://www.youtube.com/watch?v={response['id']}")
    print(f"Valide sur YouTube Studio puis poste story_final.mp4 manuellement sur TikTok.")


if __name__ == "__main__":
    main()
