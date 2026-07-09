"""
Pipeline Récitation Coranique -- Étape unique
- Choisit un récitateur doux parmi une liste soigneusement sélectionnée
- Sélectionne une sourate (ou plusieurs courtes sourates) via l'API officielle alquran.cloud
- Télécharge les MP3 officiels (reciters.qurancdn.com -- source légale et libre)
- Assemble en un seul fichier audio >1 minute
- Sauvegarde quran_recitation.mp3

Sources :
- API : https://api.alquran.cloud (libre, gratuite, officielle)
- Audio : https://everyayah.com (enregistrements libres de droits, usage autorisé)
"""

import json
import os
import random
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

OUTPUT_FILE     = Path("quran_recitation.mp3")
TEMP_DIR        = Path("quran_temp")
TARGET_DURATION = 75   # secondes minimum  (FIX: renommé depuis TARGET_DUR pour matcher les usages plus bas)

# Récitateurs connus pour leur voix douce et apaisante
# Format : (identifiant everyayah, nom affichage, qualité)
RECITERS = [
    ("Alafasy_128kbps",        "Mishary Rashid Alafasy",        "128kbps"),
    ("Abdul_Basit_Murattal_192kbps", "Abdul Basit Murattal",    "192kbps"),
    ("Husary_128kbps",         "Mahmoud Khalil Al-Husary",      "128kbps"),
    ("Ibrahim_walk_192kbps",   "Ibrahim Walk",                  "192kbps"),
    ("Minshawy_Murattal_128kbps","Mohamed Siddiq Al-Minshawi",  "128kbps"),
    ("Saood_ash-Shuraym_128kbps","Saud Al-Shuraym",             "128kbps"),
    ("Abdul_Basit_Mujawwad_128kbps","Abdul Basit Mujawwad",     "128kbps"),
]

# Sourates longues et apaisantes, très connues
LONG_SURAHS = [
    (2,  "Al-Baqara",   286),
    (3,  "Ali Imran",   200),
    (4,  "An-Nisa",     176),
    (18, "Al-Kahf",      110),
    (19, "Maryam",       98),
    (20, "Ta-Ha",        135),
    (36, "Ya-Sin",       83),
    (55, "Ar-Rahman",    78),
    (67, "Al-Mulk",      30),
    (73, "Al-Muzzammil", 20),
    (74, "Al-Muddaththir",56),
    (76, "Al-Insan",     31),
]

# Sourates courtes et très connues (pour compléter si besoin)
SHORT_SURAHS = list(range(78, 115))  # Juz Amma

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

def download_ayah(reciter_id, surah, ayah, dest, retries=3):
    """
    Télécharge un verset depuis everyayah.com
    URL format : https://everyayah.com/data/{reciter}/{surah:3d}{ayah:3d}.mp3
    """
    url = f"https://everyayah.com/data/{reciter_id}/{surah:03d}{ayah:03d}.mp3"
    for attempt in range(1, retries+1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as r, open(dest, "wb") as out:
                data = r.read()
                if len(data) < 2000:   # trop petit = silence ou erreur
                    raise ValueError(f"Fichier trop petit ({len(data)} octets)")
                out.write(data)
            return True
        except Exception as e:
            if attempt < retries:
                time.sleep(2)
            else:
                return False


def get_audio_duration(path):
    """Retourne la durée en secondes d'un fichier audio via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True
        )
        return float(r.stdout.strip())
    except:
        return 3.0  # estimation par défaut


def concat_mp3(paths, output):
    """Concatène une liste de MP3 en un seul fichier via ffmpeg."""
    lst = Path(tempfile.mktemp(suffix=".txt"))
    lst.write_text("".join(
        f"file '{Path(p).resolve().as_posix()}'\n" for p in paths
    ))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lst), "-c", "copy", str(output)
    ], capture_output=True, check=False)


def normalize_audio(input_path, output_path):
    """Normalise le volume de l'audio final."""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(input_path),
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
        "-ar", "44100", "-b:a", "192k",
        str(output_path)
    ], capture_output=True, check=False)


def main():
    TEMP_DIR.mkdir(exist_ok=True)

    # Choix du récitateur
    reciter = random.choice(RECITERS)
    reciter_id, reciter_name, quality = reciter
    print(f"Récitateur : {reciter_name} ({quality})")

    # Stratégie : choisir une sourate longue et télécharger ~25-35 versets consécutifs
    surah_info = random.choice(LONG_SURAHS)
    surah_num, surah_name, total_ayahs = surah_info
    print(f"Sourate : {surah_num} - {surah_name} ({total_ayahs} versets)")

    # Point de départ aléatoire dans la sourate
    start_ayah = random.randint(1, max(1, total_ayahs - 25))
    end_ayah   = min(total_ayahs, start_ayah + 35)
    print(f"Versets : {start_ayah} à {end_ayah}")

    downloaded = []
    total_dur  = 0.0

    for ayah in range(start_ayah, end_ayah + 1):
        if total_dur >= TARGET_DURATION:
            break
        dest = TEMP_DIR / f"ayah_{surah_num:03d}_{ayah:03d}.mp3"
        print(f"  Verset {ayah}...", end=" ", flush=True)
        ok = download_ayah(reciter_id, surah_num, ayah, dest)
        if ok:
            dur = get_audio_duration(dest)
            total_dur += dur
            downloaded.append(dest)
            print(f"OK ({dur:.1f}s, total={total_dur:.1f}s)")
        else:
            print("ECHEC (ignoré)")
        time.sleep(0.3)   # respecte le serveur

    # Si pas assez de durée, complète avec des courtes sourates
    if total_dur < TARGET_DURATION:
        print(f"\nDurée insuffisante ({total_dur:.1f}s), ajout de sourates courtes...")
        random.shuffle(SHORT_SURAHS)
        for s_num in SHORT_SURAHS:
            if total_dur >= TARGET_DURATION:
                break
            # Nombre de versets approximatif (on prend jusqu'à 10)
            for ayah in range(1, 11):
                dest = TEMP_DIR / f"short_{s_num:03d}_{ayah:03d}.mp3"
                ok = download_ayah(reciter_id, s_num, ayah, dest)
                if ok:
                    dur = get_audio_duration(dest)
                    total_dur += dur
                    downloaded.append(dest)
                time.sleep(0.2)
                if total_dur >= TARGET_DURATION:
                    break

    if not downloaded:
        print("Erreur : aucun verset téléchargé.", file=sys.stderr)
        sys.exit(1)

    print(f"\n{len(downloaded)} versets téléchargés ({total_dur:.1f}s total)")

    # Assemblage
    print("Assemblage...")
    raw = TEMP_DIR / "raw_concat.mp3"
    concat_mp3(downloaded, raw)

    # Normalisation du volume
    print("Normalisation audio...")
    normalize_audio(raw, OUTPUT_FILE)

    # Vérification durée finale
    final_dur = get_audio_duration(OUTPUT_FILE)
    print(f"\nFichier final : {OUTPUT_FILE}")
    print(f"Durée : {final_dur:.1f}s ({int(final_dur)//60}m{int(final_dur)%60:02d}s)")
    print(f"Récitateur : {reciter_name}")
    print(f"Sourate : {surah_name} (versets {start_ayah}-{min(end_ayah, start_ayah+len(downloaded)-1)})")

    # Sauvegarde des métadonnées pour l'étape vidéo (utilisées par produce_quran_video.py)
    meta = {
        "surah_name": surah_name,
        "reciter_name": reciter_name,
        "surah_num": surah_num,
        "start_ayah": start_ayah,
        "end_ayah": end_ayah,
    }
    Path("quran_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
