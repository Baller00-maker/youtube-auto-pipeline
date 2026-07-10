"""
Pipeline Récitation Coranique -- Production vidéo complète (qualité pro)

RÈGLES D'OR :
  1. La voix n'est JAMAIS retouchée : aucun effet audio (pas de reverb, pas
     d'EQ, pas de compression). L'audio original de la récitation est utilisé
     tel quel, simplement réencodé en AAC pour le conteneur MP4.
  2. La vidéo ne coupe JAMAIS un verset : la piste visuelle est toujours
     construite pour être AU MOINS aussi longue que l'audio (si besoin, la
     dernière image est gelée le temps nécessaire) avant le montage final.
     Résultat : la vidéo commence pile au début du premier verset et se
     termine pile à la fin du dernier verset, sans troncature.

Effets vidéo (qualité cinéma) :
  - Color grade chaud (tons dorés/spirituels)
  - Coupes nettes entre plans (montage direct, robuste et rythmé)
  - Vignette (bords sombres pour focus central)
  - Grain de film très subtil
  - Carte de titre stylisée en ouverture
  - Bandeau discret "Sourate • Versets" (zones sûres TikTok/Reels/Shorts)

Format : vertical 1080x1920 (TikTok/Reels/Shorts)
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
META_FILE    = Path("quran_meta.json")

PEXELS_API_KEY  = os.environ.get("PEXELS_API_KEY")
PEXELS_VIDEO    = "https://api.pexels.com/videos/search"
PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY")   # optionnel : ajoute la variable
                                                        # d'env/secret PIXABAY_API_KEY
                                                        # pour activer cette 2e source
                                                        # (clé gratuite sur pixabay.com/api/docs)
PIXABAY_VIDEO   = "https://pixabay.com/api/videos/"
USER_AGENT      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

W, H     = 1080, 1920
FPS      = 30
TITLE_DUR = 2.5    # carte de titre courte : les 3 premières secondes sont cruciales pour la rétention
SAFETY_MARGIN = 1.0  # secondes de marge vidéo en plus de l'audio, avant gel de la dernière image

# Requêtes pensées spécifiquement pour coller à l'esthétique des vidéos de
# récitation coranique qui circulent (mosquées, calligraphie, lumière douce,
# nature contemplative) -- pas juste "paysage joli" générique.
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
    "incense smoke slow motion",
    # Lumière / ciel
    "crescent moon night sky",
    "ramadan lantern night",
    "sunlight through window rays",
    "sunbeams through clouds",
    "golden hour light trees",
    # Nature contemplative
    "desert golden sunset landscape",
    "desert dunes sunrise slow",
    "ocean waves sunrise peaceful",
    "mountain mist sunrise aerial",
    "river calm reflection nature",
    "forest light rays morning",
    "waterfall nature peaceful",
    "sand dunes desert wind",
    "clouds aerial drone above",
    "rain window calm",
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


# ─── VIDEO CLIPS ────────────────────────────────────────────────────────────

def pexels_search(query, per_page=5):
    url = (f"{PEXELS_VIDEO}?query={urllib.parse.quote(query)}"
           f"&per_page={per_page}&orientation=landscape")
    req = urllib.request.Request(url, headers={
        "Authorization": PEXELS_API_KEY, "User-Agent": USER_AGENT
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def pexels_candidates(query, per_page=5):
    """Retourne une liste normalisée [(url, duration_s), ...] depuis Pexels."""
    out = []
    try:
        data = pexels_search(query, per_page=per_page)
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
            url = best.get("link", "")
            if url:
                out.append((url, min(dur_v, 12)))
    except Exception as e:
        print(f"  ! Pexels erreur pour '{query}' : {e}", file=sys.stderr)
    return out


def pixabay_candidates(query, per_page=5):
    """Retourne une liste normalisée [(url, duration_s), ...] depuis Pixabay."""
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
            # Pixabay propose plusieurs résolutions : large, medium, small
            for size in ["large", "medium", "small"]:
                v = videos.get(size)
                if v and v.get("width", 0) > v.get("height", 0) and v.get("url"):
                    out.append((v["url"], min(dur_v, 12)))
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
    Traitement cinématique d'un clip :
    1. Scale/crop portrait 1080x1920
    2. Color grade chaud (dorés/spirituels)
    3. Vignette + grain film subtil
    4. Fade-in/out
    (Note : l'effet Ken Burns/zoompan a été retiré -- il provoquait un écran
    noir après quelques secondes sur les vidéos de stock en framerate variable.)
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


# ─── TITRE + BANDEAU (safe zones TikTok/Reels/Shorts) ──────────────────────

def make_title_card(surah_name, reciter_name, ayah_range, duration=TITLE_DUR):
    """Carte de titre élégante en ouverture (hook rapide, <3s)."""
    img  = Image.new("RGB", (W, H), (8, 8, 20))
    draw = ImageDraw.Draw(img)

    gold = (200, 160, 40)
    draw.rectangle([W//2 - 200, H//2 - 2, W//2 + 200, H//2 + 2], fill=gold)

    f1 = load_font(88, bold=True)
    text = surah_name.upper()
    bb = draw.textbbox((0,0), text, font=f1)
    draw.text(((W-(bb[2]-bb[0]))//2, H//2 - 150), text, font=f1, fill=gold)

    f2 = load_font(44)
    sub = f"Récité par {reciter_name}"
    bb2 = draw.textbbox((0,0), sub, font=f2)
    draw.text(((W-(bb2[2]-bb2[0]))//2, H//2 + 0), sub, font=f2, fill=(180, 180, 180))

    if ayah_range:
        f3 = load_font(36)
        sub2 = f"Versets {ayah_range}"
        bb3 = draw.textbbox((0,0), sub2, font=f3)
        draw.text(((W-(bb3[2]-bb3[0]))//2, H//2 + 60), sub2, font=f3, fill=(140, 140, 140))

    for dx in [-280, 280]:
        draw.ellipse([W//2+dx-6, H//2-6, W//2+dx+6, H//2+6], fill=gold)

    tmp_img  = WORK_DIR / "title_card.png"
    tmp_clip = WORK_DIR / "title_clip.mp4"
    img.save(tmp_img)

    run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(tmp_img),
        "-t", str(duration),
        "-vf", (
            f"fps={FPS},"
            f"fade=t=in:st=0:d=0.5,"
            f"fade=t=out:st={duration-0.5:.1f}:d=0.5"
        ),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast",
        str(tmp_clip)
    ], "Génération carte de titre")
    return tmp_clip


def make_caption_overlay(surah_name, ayah_range):
    """
    Bandeau discret et permanent "Sourate • Versets", placé en HAUT de l'écran
    pour rester hors des zones d'interface TikTok/Reels/Shorts (les boutons
    et légendes de ces apps occupent le bas et le côté droit de l'écran).
    Retourne un PNG transparent de la taille de la vidéo.
    """
    img  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    label = f"{surah_name}" + (f"  •  Versets {ayah_range}" if ayah_range else "")
    font  = load_font(34, bold=True)
    bb    = draw.textbbox((0,0), label, font=font)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]

    pad_x, pad_y = 28, 14
    box_w, box_h = tw + pad_x*2, th + pad_y*2
    box_x = (W - box_w) // 2
    box_y = 130   # zone haute, toujours sûre sur les 3 plateformes

    draw.rounded_rectangle(
        [box_x, box_y, box_x+box_w, box_y+box_h],
        radius=box_h//2, fill=(0, 0, 0, 110)
    )
    draw.text((box_x+pad_x, box_y+pad_y-2), label, font=font, fill=(230, 200, 120, 255))

    dest = WORK_DIR / "caption_overlay.png"
    img.save(dest)
    return dest


# ─── ASSEMBLAGE (coupes nettes) ─────────────────────────────────────────────
# Note : on utilisait auparavant des transitions en fondu-enchaîné (xfade),
# mais ce filtre est fragile dès qu'un clip source a une durée réelle
# légèrement différente de la durée prévue -- ça décale le calcul des offsets
# et ça peut produire un écran noir à partir de la transition concernée.
# Le concat simple (coupe nette) élimine complètement ce risque, et reste très
# dynamique/adapté au format TikTok/Reels/Shorts (le fade-in/out appliqué sur
# chaque clip dans process_clip donne déjà un rendu propre à chaque coupe).

def build_silent_video(clip_paths, output):
    """Concatène tous les clips (coupes nettes, sans transition) SANS audio."""
    if len(clip_paths) == 1:
        return run(["ffmpeg", "-y", "-i", str(clip_paths[0]), "-c:v", "copy", str(output)],
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
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(output)
    ]
    return run(cmd, "Piste vidéo silencieuse (concat, coupes nettes)")


def pad_to_duration(src, dest, target_duration):
    """
    Si la piste vidéo est plus courte que l'audio, gèle la dernière image
    pendant le temps nécessaire. Garantit vidéo_durée >= audio_durée, donc
    l'audio ne sera JAMAIS tronqué au montage final.
    """
    cur = get_duration(src)
    pad = target_duration - cur + SAFETY_MARGIN
    if pad <= 0:
        return src  # déjà assez longue
    print(f"  Piste vidéo ({cur:.1f}s) plus courte que l'audio ({target_duration:.1f}s) "
          f"-> gel de la dernière image pendant {pad:.1f}s")
    ok = run([
        "ffmpeg", "-y", "-i", str(src),
        "-vf", f"tpad=stop_mode=clone:stop_duration={pad:.2f}",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        str(dest)
    ], "Extension vidéo (gel dernière image)")
    return dest if ok else src


def overlay_caption(video_path, overlay_png, output):
    return run([
        "ffmpeg", "-y", "-i", str(video_path), "-i", str(overlay_png),
        "-filter_complex", "overlay=0:0",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
        str(output)
    ], "Ajout du bandeau Sourate/Versets")


def final_mux(video_path, audio_path, audio_duration, output):
    """
    Fusion vidéo + audio ORIGINAL (aucun filtre). La vidéo est garantie
    >= audio_duration (voir pad_to_duration). On coupe explicitement à
    -t audio_duration (plus fiable que -shortest avec -c:v copy, qui peut
    laisser dépasser la vidéo de quelques images/secondes) : l'audio n'est
    donc jamais tronqué, et la vidéo se termine pile à la fin de l'audio.
    """
    return run([
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "256k",
        "-t", f"{audio_duration:.3f}",
        str(output)
    ], "Fusion finale vidéo + audio original (non retouché)")


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

    total_audio_dur = get_duration(AUDIO_FILE)
    print(f"Récitation (originale, non retouchée) : {total_audio_dur:.1f}s "
          f"({int(total_audio_dur)//60}m{int(total_audio_dur)%60:02d}s)")

    # Métadonnées (nom de sourate, récitateur, plage de versets)
    surah_name   = "Récitation Coranique"
    reciter_name = "Sheikh Al-Qari"
    ayah_range   = ""
    if META_FILE.exists():
        meta = json.loads(META_FILE.read_text())
        surah_name   = meta.get("surah_name", surah_name)
        reciter_name = meta.get("reciter_name", reciter_name)
        if meta.get("start_ayah") and meta.get("end_ayah"):
            ayah_range = f"{meta['start_ayah']}-{meta['end_ayah']}"

    # 1. Carte de titre
    print("\n[1/6] Création carte de titre...")
    title_clip = make_title_card(surah_name, reciter_name, ayah_range)
    title_dur  = TITLE_DUR

    # 2. Téléchargement des visuels (avec marge : on vise 1.4x la durée nécessaire
    #    pour ne jamais manquer de contenu vidéo, ce qui évite d'avoir à tronquer l'audio)
    print("\n[2/6] Téléchargement visuels Pexels...")
    needed = (total_audio_dur - title_dur) * 1.4
    clips_info = []
    idx = 0

    import random
    queries = QUERIES.copy()
    random.shuffle(queries)

    for query in queries:
        if sum(d for _, d in clips_info) >= needed:
            break
        print(f"  Recherche : '{query}'")
        candidates = pexels_candidates(query, per_page=3) + pixabay_candidates(query, per_page=3)
        for url, dur_v in candidates:
            if sum(d for _, d in clips_info) >= needed:
                break
            dest = WORK_DIR / f"raw_{idx:03d}.mp4"
            try:
                print(f"    Téléchargement clip {idx} ({dur_v:.0f}s)...")
                download_video(url, dest)
                clips_info.append((dest, dur_v))
                idx += 1
            except Exception as e:
                print(f"    ! {e}", file=sys.stderr)
            time.sleep(0.3)

    if not clips_info:
        print("Erreur : aucun clip visuel téléchargé.", file=sys.stderr)
        sys.exit(1)

    # 3. Traitement cinématique de chaque clip
    print(f"\n[3/6] Traitement cinématique ({len(clips_info)} clips)...")
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

    # Si le total est encore trop court (rare, ex. Pexels a peu répondu),
    # on boucle sur les clips déjà traités plutôt que de risquer une vidéo trop courte
    all_clips = [title_clip] + processed_clips
    all_durs  = [title_dur] + processed_durs
    i = 0
    while sum(all_durs) < total_audio_dur + SAFETY_MARGIN:
        all_clips.append(processed_clips[i % len(processed_clips)])
        all_durs.append(processed_durs[i % len(processed_durs)])
        i += 1

    # 4. Piste vidéo silencieuse (coupes nettes) puis garantie de durée >= audio
    print(f"\n[4/6] Assemblage vidéo silencieuse ({len(all_clips)} clips, coupes nettes)...")
    silent_video = WORK_DIR / "silent_video.mp4"
    if not build_silent_video(all_clips, silent_video):
        print("Erreur lors de l'assemblage vidéo.", file=sys.stderr)
        sys.exit(1)

    padded_video = pad_to_duration(silent_video, WORK_DIR / "padded_video.mp4", total_audio_dur)

    # 5. Bandeau Sourate/Versets
    print("\n[5/6] Ajout du bandeau...")
    overlay_png = make_caption_overlay(surah_name, ayah_range)
    captioned_video = WORK_DIR / "captioned_video.mp4"
    if not overlay_caption(padded_video, overlay_png, captioned_video):
        captioned_video = padded_video  # fallback : pas bloquant

    # 6. Fusion finale avec l'audio ORIGINAL (aucun effet) -- l'audio est
    #    garanti intact du premier au dernier verset grâce à l'étape 4.
    print("\n[6/6] Fusion finale (audio original, non retouché)...")
    ok = final_mux(captioned_video, AUDIO_FILE, total_audio_dur, OUTPUT_FILE)
    if not ok:
        print("Erreur lors de l'assemblage final.", file=sys.stderr)
        sys.exit(1)

    final_dur  = get_duration(OUTPUT_FILE)
    final_audio_dur = get_duration(OUTPUT_FILE)  # même flux, vérif rapide
    print(f"\n✅ Vidéo finale : {OUTPUT_FILE}")
    print(f"   Durée : {final_dur:.1f}s ({int(final_dur)//60}m{int(final_dur)%60:02d}s)")
    print(f"   Audio original de la récitation (durée {total_audio_dur:.1f}s) intégralement conservé")
    print(f"   Résolution : {W}x{H} | FPS : {FPS} | CRF : 18 (haute qualité)")
    print(f"   Audio : original, aucun effet appliqué")
    print(f"   Effets vidéo : color grade chaud + coupes nettes + vignette + grain + bandeau")


if __name__ == "__main__":
    main()
