"""
Pipeline Quiz TikTok -- Rendu vidéo VERSION 2 (design pro)

Design :
- Fond sombre dégradé (bleu nuit → violet profond)
- Police Bebas Neue (téléchargée dans le workflow)
- Countdown animé avec cercle de progression
- Les choix slide-in depuis la droite (animés)
- Son de chronomètre pendant la réflexion
- La voix LIT SEULEMENT la question, PAS les choix
- Hook percutant en ouverture
- Reveal de réponse avec effet flash + ding
- Call to action dynamique
"""

import asyncio
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

QUIZ_FILE = Path("quiz_data.json")
OUTPUT_FILE = Path("quiz_final.mp4")
CLIPS_DIR = Path("quiz_clips")
AUDIO_DIR = Path("quiz_audio")
FONTS_DIR = Path("fonts")

WIDTH, HEIGHT = 1080, 1920
FPS = 24

# Palette de couleurs
BG_TOP    = (8, 8, 35)
BG_BOT    = (28, 8, 55)
ACCENT    = (99, 120, 255)
GOLD      = (255, 210, 0)
CORRECT   = (30, 220, 120)
WRONG_COL = (255, 65, 80)
CARD_BG   = (20, 20, 55)
WHITE     = (255, 255, 255)
GRAY      = (160, 160, 180)
TIMER_BG  = (35, 35, 70)

# Timing (secondes)
HOOK_DUR     = 4
Q_REVEAL_DUR = 2     # la voix lit la question
Q_THINK_DUR  = 8     # countdown silencieux avec tic
ANS_DUR      = 4
CTA_DUR      = 7

# Voix : masculin posé/philosophe, proche du style TikTok FR
VOICE = "fr-FR-HenriNeural"


# ─── POLICES ────────────────────────────────────────────────────────────────

def load_font(name, size, bold=False):
    candidates = [
        FONTS_DIR / f"{name}.ttf",
        FONTS_DIR / "BebasNeue.ttf",
        Path(f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'Bold' if bold else ''}.ttf"),
        Path(f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else ''}.ttf"),
    ]
    for p in candidates:
        if p.exists():
            try:
                return ImageFont.truetype(str(p), size)
            except Exception:
                pass
    return ImageFont.load_default()


def bebas(size):
    return load_font("BebasNeue", size)


def sans(size, bold=False):
    return load_font("Bold" if bold else "Regular", size, bold=bold)


# ─── UTILITAIRES DESSIN ─────────────────────────────────────────────────────

def gradient_bg():
    """Crée une image de fond dégradé vertical."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * t)
        for x in range(WIDTH):
            img.putpixel((x, y), (r, g, b))
    return img

# Cache le fond pour ne pas le recréer à chaque frame
_BG_CACHE = None
def get_bg():
    global _BG_CACHE
    if _BG_CACHE is None:
        _BG_CACHE = gradient_bg()
    return _BG_CACHE.copy()


def centered_text(draw, text, y, font, color, max_w=960, line_gap=8):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        bb = draw.textbbox((0,0), test, font=font)
        if bb[2]-bb[0] <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    lh = font.size + line_gap
    for i, line in enumerate(lines):
        bb = draw.textbbox((0,0), line, font=font)
        x = (WIDTH - (bb[2]-bb[0])) // 2
        draw.text((x, y + i*lh), line, font=font, fill=color)
    return len(lines) * lh


def draw_circle_progress(draw, cx, cy, r, progress, thick=14):
    """Cercle de progression (arc qui diminue)."""
    # Fond du cercle
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], outline=TIMER_BG, width=thick)
    # Arc de progression
    if progress > 0.01:
        end = -90 + progress * 360
        draw.arc([cx-r, cy-r, cx+r, cy+r], start=-90, end=end,
                 fill=GOLD if progress > 0.3 else WRONG_COL, width=thick)


def draw_pill(draw, x, y, w, h, color, radius=22):
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=color)


def draw_choice_card(draw, letter, text, x, y, w=980, h=120, state="normal", font_body=None):
    colors = {
        "normal":  {"bg": CARD_BG,          "border": ACCENT,      "letter_bg": ACCENT,      "text": WHITE},
        "correct": {"bg": (15, 60, 35),      "border": CORRECT,     "letter_bg": CORRECT,     "text": CORRECT},
        "wrong":   {"bg": (55, 12, 18),      "border": WRONG_COL,   "letter_bg": WRONG_COL,   "text": GRAY},
        "dim":     {"bg": (18, 18, 40),      "border": (50,50,80),  "letter_bg": (50,50,80),  "text": GRAY},
    }
    c = colors.get(state, colors["normal"])
    # Carte
    draw.rounded_rectangle([x, y, x+w, y+h], radius=24, fill=c["bg"])
    draw.rounded_rectangle([x, y, x+w, y+h], radius=24, outline=c["border"], width=3)
    # Badge lettre
    bsz = h - 20
    draw.rounded_rectangle([x+10, y+10, x+10+bsz, y+h-10], radius=14, fill=c["letter_bg"])
    lf = bebas(52)
    lb = draw.textbbox((0,0), letter, font=lf)
    lx = x + 10 + (bsz - (lb[2]-lb[0])) // 2
    ly = y + 10 + (h - 20 - (lb[3]-lb[1])) // 2
    draw.text((lx, ly), letter, font=lf, fill=(10,10,30))
    # Texte du choix
    tf = font_body or sans(36)
    tw = draw.textbbox((0,0), text, font=tf)
    ty = y + (h - (tw[3]-tw[1])) // 2
    draw.text((x + bsz + 30, ty), text, font=tf, fill=c["text"])


# ─── GÉNÉRATION AUDIO ───────────────────────────────────────────────────────

async def tts(text, path):
    comm = edge_tts.Communicate(text, VOICE, rate="+0%")
    await comm.save(str(path))


def gen_ding(path, freq=880, dur=0.5):
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={dur}",
        "-af", f"volume=0.8,afade=t=out:st={dur-0.08}:d=0.08",
        str(path)
    ], capture_output=True)


def gen_ticking(path, duration):
    """Son de chronomètre : tick toutes les 0.5s."""
    tmp = Path(tempfile.mkdtemp())
    # Un tick = court beep 800Hz 25ms
    tick = tmp / "tick.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "sine=frequency=800:duration=0.025",
        "-af", "volume=0.4",
        str(tick)
    ], capture_output=True)
    # Silence 475ms
    sil = tmp / "sil.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "0.475",
        str(sil)
    ], capture_output=True)
    # Cycle = tick + silence
    cycle = tmp / "cycle.mp3"
    lst = tmp / "lst.txt"
    lst.write_text(f"file '{tick.resolve()}'\nfile '{sil.resolve()}'\n")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lst), "-c", "copy", str(cycle)
    ], capture_output=True)
    # Répéter le cycle
    n = int(duration / 0.5) + 3
    lst2 = tmp / "lst2.txt"
    lst2.write_text("".join(f"file '{cycle.resolve()}'\n" for _ in range(n)))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lst2), "-t", str(duration), str(path)
    ], capture_output=True)


def gen_silence(path, duration):
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", str(duration), str(path)
    ], capture_output=True)


def mix_audio(a1, a2, output, delay_a2=0.0):
    """Mixe deux pistes audio (a2 commence après delay_a2 secondes)."""
    subprocess.run([
        "ffmpeg", "-y", "-i", str(a1), "-i", str(a2),
        "-filter_complex",
        f"[1:a]adelay={int(delay_a2*1000)}|{int(delay_a2*1000)}[a2];[0:a][a2]amix=inputs=2:duration=longest[out]",
        "-map", "[out]", str(output)
    ], capture_output=True)


def merge_va(video, audio, output, duration=None):
    args = ["ffmpeg", "-y", "-i", str(video), "-i", str(audio)]
    if duration:
        args += ["-t", str(duration)]
    args += ["-c:v", "copy", "-c:a", "aac", "-shortest", str(output)]
    subprocess.run(args, capture_output=True)


def concat_clips(paths, output):
    lst = Path(tempfile.mktemp(suffix=".txt"))
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in paths))
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(lst), "-c", "copy", str(output)
    ], capture_output=True)


# ─── FRAMES PIL ─────────────────────────────────────────────────────────────

def make_hook_frame(title, stat_pct=5):
    img = get_bg()
    draw = ImageDraw.Draw(img)
    # Bande accent top
    draw.rectangle([0, 0, WIDTH, 10], fill=ACCENT)
    # Emoji
    ef = bebas(140)
    centered_text(draw, "🧠", HEIGHT//2 - 380, ef, WHITE)
    # Texte principal
    hf = bebas(110)
    centered_text(draw, f"SEULS {stat_pct}% DES GENS", HEIGHT//2 - 220, hf, GOLD)
    centered_text(draw, "RÉPONDENT CORRECTEMENT", HEIGHT//2 - 100, hf, GOLD)
    # Sous-titre
    sf = sans(48)
    centered_text(draw, "à ces 10 questions !", HEIGHT//2 + 50, sf, WHITE)
    centered_text(draw, "Testez-vous maintenant 👇", HEIGHT//2 + 120, sf, GRAY)
    # Bouton
    draw_pill(draw, 180, HEIGHT//2 + 240, 720, 100, ACCENT)
    bf = bebas(64)
    centered_text(draw, "C'EST PARTI ! 🚀", HEIGHT//2 + 256, bf, WHITE)
    return img


def make_question_frame(q_num, q_data, countdown_progress, choices_visible=4, show_category=True):
    """
    countdown_progress : 1.0 = début, 0.0 = fin
    choices_visible : nombre de choix affichés (animation slide-in)
    """
    img = get_bg()
    draw = ImageDraw.Draw(img)

    # Barre de statut top
    draw.rectangle([0, 0, WIDTH, 100], fill=(15, 15, 45))
    nf = bebas(58)
    draw.text((50, 22), f"QUESTION {q_num}/10", font=nf, fill=ACCENT)

    # Catégorie
    if show_category:
        cf = sans(34)
        cat = q_data.get("category", "").upper()
        centered_text(draw, f"▸ {cat}", 118, cf, GOLD)

    # Countdown cercle + chiffre (à droite en haut)
    seconds_left = int(countdown_progress * Q_THINK_DUR) + 1
    cx, cy, r = WIDTH - 90, 55, 48
    draw_circle_progress(draw, cx, cy, r, countdown_progress, thick=10)
    num_f = bebas(52)
    nb = draw.textbbox((0,0), str(seconds_left), font=num_f)
    draw.text((cx - (nb[2]-nb[0])//2, cy - (nb[3]-nb[1])//2), str(seconds_left), font=num_f, fill=WHITE)

    # Question
    qf = bebas(86)
    q_y = 170
    q_h = centered_text(draw, q_data["question"].upper(), q_y, qf, WHITE, max_w=940)

    # Choices
    letters = ["A", "B", "C", "D"]
    texts = [q_data["choices"][l] for l in letters]
    card_h = 115
    card_gap = 18
    start_y = q_y + q_h + 40
    bf = sans(38, bold=False)
    for i in range(min(choices_visible, 4)):
        draw_choice_card(draw, letters[i], texts[i], 50, start_y + i*(card_h+card_gap),
                         w=WIDTH-100, h=card_h, state="normal", font_body=bf)

    # Bas de l'écran : "⏱ Réfléchis !"
    if choices_visible == 4:
        tf = sans(40)
        centered_text(draw, "⏱  Réfléchis... quelle est ta réponse ?", start_y + 4*(card_h+card_gap) + 20, tf, GRAY)

    return img


def make_answer_frame(q_num, q_data, with_explanation=True):
    img = get_bg()
    draw = ImageDraw.Draw(img)
    correct = q_data["correct"]

    # Barre top verte
    draw.rectangle([0, 0, WIDTH, 100], fill=(15, 60, 35))
    nf = bebas(58)
    draw.text((50, 22), f"✅  RÉPONSE — QUESTION {q_num}/10", font=nf, fill=CORRECT)

    # Catégorie
    cf = sans(34)
    centered_text(draw, f"▸ {q_data.get('category','').upper()}", 118, cf, GOLD)

    # Question (plus petite)
    qf = bebas(66)
    q_h = centered_text(draw, q_data["question"].upper(), 175, qf, WHITE, max_w=940)

    # Choices
    letters = ["A", "B", "C", "D"]
    card_h = 112
    card_gap = 16
    start_y = 175 + q_h + 36
    bf = sans(38)
    for i, l in enumerate(letters):
        state = "correct" if l == correct else "wrong"
        draw_choice_card(draw, l, q_data["choices"][l], 50, start_y + i*(card_h+card_gap),
                         w=WIDTH-100, h=card_h, state=state, font_body=bf)

    # Explication
    if with_explanation and q_data.get("explanation"):
        exp_y = start_y + 4*(card_h+card_gap) + 24
        draw.rounded_rectangle([40, exp_y, WIDTH-40, exp_y+110], radius=20, fill=(15,60,35))
        draw.rounded_rectangle([40, exp_y, WIDTH-40, exp_y+110], radius=20, outline=CORRECT, width=2)
        ef = sans(36)
        centered_text(draw, f"💡  {q_data['explanation']}", exp_y + 18, ef, CORRECT, max_w=940)

    return img


def make_cta_frame():
    img = get_bg()
    draw = ImageDraw.Draw(img)
    # Titre
    tf = bebas(100)
    centered_text(draw, "TU AS AIMÉ CE QUIZ ?", 160, tf, GOLD)
    sf = sans(46)
    centered_text(draw, "Aide-nous à continuer :", 290, sf, WHITE)
    # Actions
    items = [
        ("❤️", "Like la vidéo",          WRONG_COL),
        ("➕", "Abonne-toi",              ACCENT),
        ("↗️", "Partage à tes amis",      CORRECT),
        ("💬", "Dis ton score en comment.", GOLD),
    ]
    for i, (emoji, text, color) in enumerate(items):
        y = 380 + i * 155
        draw.rounded_rectangle([50, y, WIDTH-50, y+130], radius=28, fill=color)
        ef = bebas(68)
        draw.text((90, y+22), emoji, font=ef, fill=WHITE)
        tf2 = bebas(64)
        tb = draw.textbbox((0,0), text, font=tf2)
        draw.text((200, y + (130-(tb[3]-tb[1]))//2), text, font=tf2, fill=WHITE)
    # Score
    sc = sans(44)
    centered_text(draw, "🏆  Score /10 dans les commentaires !", HEIGHT-130, sc, GRAY)
    return img


# ─── GÉNÉRATION CLIPS ───────────────────────────────────────────────────────

def frames_to_clip(frames, fps, output):
    tmp = Path(tempfile.mkdtemp())
    for i, f in enumerate(frames):
        f.save(tmp / f"f{i:04d}.png")
    if len(frames) == 1:
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(tmp/"f0000.png"),
               "-t", str(1/fps * 1), "-vf", f"fps={fps}",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)]
    else:
        cmd = ["ffmpeg", "-y", "-framerate", str(fps),
               "-i", str(tmp/"f%04d.png"),
               "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)]
    subprocess.run(cmd, capture_output=True)


def still_to_clip(frame, duration, output, fps=FPS):
    tmp = Path(tempfile.mktemp(suffix=".png"))
    frame.save(tmp)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(tmp),
        "-t", str(duration), "-vf", f"fps={fps}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(output)
    ], capture_output=True)


def animated_countdown_clip(q_num, q_data, duration, fps=FPS, choices_visible=4):
    """Génère la séquence animée du countdown (plusieurs frames)."""
    total = int(duration * fps)
    frames = []
    for i in range(total):
        progress = 1.0 - (i / total)
        frames.append(make_question_frame(q_num, q_data, progress, choices_visible=choices_visible))
    return frames


def slide_in_frames(q_num, q_data, fps=FPS):
    """Animation d'entrée des choix (slide depuis droite, ~1.5s)."""
    steps = int(1.5 * fps)
    frames = []
    for step in range(steps):
        # On réutilise make_question_frame avec choices_visible progressif
        visible = min(4, 1 + (step * 4) // steps)
        progress = 1.0  # timer plein
        frames.append(make_question_frame(q_num, q_data, progress, choices_visible=visible))
    return frames


# ─── PIPELINE PRINCIPAL ─────────────────────────────────────────────────────

def main():
    if not QUIZ_FILE.exists():
        print(f"Erreur : {QUIZ_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(QUIZ_FILE, encoding="utf-8") as f:
        quiz = json.load(f)

    CLIPS_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)

    print("Génération effets sonores...")
    ding = AUDIO_DIR / "ding.mp3"
    gen_ding(ding, freq=880, dur=0.5)
    gen_ding(AUDIO_DIR / "start.mp3", freq=660, dur=0.4)

    all_clips = []

    # ── HOOK ──
    print("Hook...")
    hook_img = make_hook_frame(quiz["title"], stat_pct=5)
    hook_v = CLIPS_DIR / "hook.mp4"
    still_to_clip(hook_img, HOOK_DUR, hook_v)
    hook_a = AUDIO_DIR / "hook.mp3"
    asyncio.run(tts(
        f"Attention ! Seuls 5% des gens répondent correctement à ces 10 questions de culture générale. Peux-tu relever le défi ?",
        hook_a
    ))
    hook_final = CLIPS_DIR / "hook_final.mp4"
    merge_va(hook_v, hook_a, hook_final, HOOK_DUR)
    all_clips.append(hook_final)

    # ── QUESTIONS ──
    for i, q in enumerate(quiz["questions"]):
        n = i + 1
        print(f"Question {n}/10 : {q['question'][:50]}...")

        # --- Phase 1 : reveal de la question (voix lit la question) ---
        q_reveal_v = CLIPS_DIR / f"q{n:02d}_reveal.mp4"
        # Frame statique avec countdown à 1.0 et 0 choix visibles (suspense)
        reveal_frame = make_question_frame(n, q, 1.0, choices_visible=0)
        still_to_clip(reveal_frame, Q_REVEAL_DUR, q_reveal_v)

        q_tts = AUDIO_DIR / f"q{n:02d}_question.mp3"
        asyncio.run(tts(q["question"], q_tts))

        q_reveal_final = CLIPS_DIR / f"q{n:02d}_reveal_final.mp4"
        merge_va(q_reveal_v, q_tts, q_reveal_final, Q_REVEAL_DUR)

        # --- Phase 2 : slide-in des choix (1.5s, silencieux) ---
        slide_frames = slide_in_frames(n, q)
        slide_v = CLIPS_DIR / f"q{n:02d}_slide.mp4"
        frames_to_clip(slide_frames, FPS, slide_v)
        slide_sil = AUDIO_DIR / f"q{n:02d}_slide_sil.mp3"
        gen_silence(slide_sil, 1.5)
        slide_final = CLIPS_DIR / f"q{n:02d}_slide_final.mp4"
        merge_va(slide_v, slide_sil, slide_final, 1.5)

        # --- Phase 3 : countdown + tic tic (Q_THINK_DUR secondes) ---
        think_frames = animated_countdown_clip(n, q, Q_THINK_DUR, fps=FPS)
        think_v = CLIPS_DIR / f"q{n:02d}_think.mp4"
        frames_to_clip(think_frames, FPS, think_v)
        tick_a = AUDIO_DIR / f"q{n:02d}_tick.mp3"
        gen_ticking(tick_a, Q_THINK_DUR)
        think_final = CLIPS_DIR / f"q{n:02d}_think_final.mp4"
        merge_va(think_v, tick_a, think_final, Q_THINK_DUR)

        # --- Phase 4 : reveal réponse ---
        ans_frame_1 = make_answer_frame(n, q, with_explanation=False)
        ans_frame_2 = make_answer_frame(n, q, with_explanation=True)
        ans_v = CLIPS_DIR / f"q{n:02d}_ans.mp4"
        # Flash : 0.5s sans explication, puis avec
        flash_frames = [ans_frame_1] * int(0.5 * FPS) + [ans_frame_2] * int((ANS_DUR - 0.5) * FPS)
        frames_to_clip(flash_frames, FPS, ans_v)

        ans_tts = AUDIO_DIR / f"q{n:02d}_ans.mp3"
        correct_letter = q["correct"]
        asyncio.run(tts(
            f"La réponse est {correct_letter} : {q['choices'][correct_letter]}. {q.get('explanation', '')}",
            ans_tts
        ))
        ans_mixed = AUDIO_DIR / f"q{n:02d}_ans_mixed.mp3"
        mix_audio(ding, ans_tts, ans_mixed, delay_a2=0.3)
        ans_final = CLIPS_DIR / f"q{n:02d}_ans_final.mp4"
        merge_va(ans_v, ans_mixed, ans_final, ANS_DUR)

        # Concaténer les 4 phases
        q_full = CLIPS_DIR / f"q{n:02d}_full.mp4"
        concat_clips([q_reveal_final, slide_final, think_final, ans_final], q_full)
        all_clips.append(q_full)
        print(f"  ✓ Q{n} assemblée")

    # ── CTA ──
    print("Call to action...")
    cta_img = make_cta_frame()
    cta_v = CLIPS_DIR / "cta.mp4"
    still_to_clip(cta_img, CTA_DUR, cta_v)
    cta_tts = AUDIO_DIR / "cta.mp3"
    asyncio.run(tts(
        "Tu as aimé ce quiz ? Like la vidéo, abonne-toi pour en voir d'autres, partage avec tes amis, et dis-nous ton score en commentaire !",
        cta_tts
    ))
    cta_final = CLIPS_DIR / "cta_final.mp4"
    merge_va(cta_v, cta_tts, cta_final, CTA_DUR)
    all_clips.append(cta_final)

    # ── ASSEMBLAGE FINAL ──
    print("Assemblage final...")
    concat_clips(all_clips, OUTPUT_FILE)

    total = HOOK_DUR + 10*(Q_REVEAL_DUR + 1.5 + Q_THINK_DUR + ANS_DUR) + CTA_DUR
    print(f"\n✅ Vidéo finale : {OUTPUT_FILE}")
    print(f"   Durée estimée : {int(total)}s (~{int(total)//60}m{int(total)%60:02d}s)")


if __name__ == "__main__":
    main()
