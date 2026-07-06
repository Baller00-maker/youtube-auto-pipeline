"""
Pipeline Quiz TikTok -- VERSION 3
- Toutes les questions lues par la voix
- Réponses lues après chaque question
- Fond dynamique avec emojis thématiques semi-transparents
- Durée cible : ~2 minutes
- Police Bebas Neue
- Son chronomètre pendant la réflexion
- Une seule session asyncio pour tout le TTS (corrige le bug voix)
"""

import asyncio
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

QUIZ_FILE   = Path("quiz_data.json")
OUTPUT_FILE = Path("quiz_final.mp4")
CLIPS_DIR   = Path("quiz_clips")
AUDIO_DIR   = Path("quiz_audio")
FONTS_DIR   = Path("fonts")

WIDTH, HEIGHT = 1080, 1920
FPS = 24

# Palette
BG_TOP    = (8,   8,  35)
BG_BOT    = (28,  8,  55)
ACCENT    = (99, 120, 255)
GOLD      = (255, 210,  0)
CORRECT   = (30,  220, 120)
WRONG_COL = (255,  65,  80)
CARD_BG   = (20,  20,  55)
WHITE     = (255, 255, 255)
GRAY      = (160, 160, 180)
TIMER_BG  = (35,  35,  70)

# Timing
HOOK_DUR  = 3
Q_TTS_DUR = 3   # voix lit la question
Q_TICK_DUR= 5   # chrono (réduit pour garder <2min)
ANS_DUR   = 4   # voix lit la réponse
CTA_DUR   = 6

VOICE = "fr-FR-HenriNeural"

# Emojis par catégorie (fond dynamique)
CATEGORY_EMOJIS = {
    "géographie":    ["🌍","🗺️","🏔️","🌊","🧭"],
    "histoire":      ["⚔️","🏰","📜","🎖️","👑"],
    "sciences":      ["🔬","⚗️","🧬","🔭","💡"],
    "animaux":       ["🦁","🐘","🦋","🐬","🦅"],
    "sport":         ["⚽","🏆","🎾","🏊","🥇"],
    "cinéma":        ["🎬","🎭","🍿","🎞️","⭐"],
    "musique":       ["🎵","🎸","🎹","🎤","🎺"],
    "gastronomie":   ["🍕","🥗","🍰","👨‍🍳","🌶️"],
    "technologies":  ["💻","🤖","📱","🚀","⚡"],
    "insolite":      ["🤔","❓","💫","🎲","🔮"],
    "default":       ["❓","🧠","💡","⭐","🎯"],
}


# ─── POLICES ────────────────────────────────────────────────────────────────

def bebas(size):
    p = FONTS_DIR / "BebasNeue.ttf"
    if p.exists():
        try: return ImageFont.truetype(str(p), size)
        except: pass
    for fb in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if Path(fb).exists():
            try: return ImageFont.truetype(fb, size)
            except: pass
    return ImageFont.load_default()


def sans(size):
    for fb in ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans.ttf"]:
        if Path(fb).exists():
            try: return ImageFont.truetype(fb, size)
            except: pass
    return ImageFont.load_default()


# ─── DESSIN ─────────────────────────────────────────────────────────────────

def make_gradient():
    img = Image.new("RGB", (WIDTH, HEIGHT))
    for y in range(HEIGHT):
        t = y / HEIGHT
        r = int(BG_TOP[0]*(1-t) + BG_BOT[0]*t)
        g = int(BG_TOP[1]*(1-t) + BG_BOT[1]*t)
        b = int(BG_TOP[2]*(1-t) + BG_BOT[2]*t)
        for x in range(WIDTH):
            img.putpixel((x, y), (r, g, b))
    return img

_BG = None
def get_bg():
    global _BG
    if _BG is None: _BG = make_gradient()
    return _BG.copy()


def get_category_emojis(category):
    cat = category.lower()
    for key, emojis in CATEGORY_EMOJIS.items():
        if key in cat:
            return emojis
    return CATEGORY_EMOJIS["default"]


def draw_dynamic_bg(category):
    """Fond avec emojis thématiques semi-transparents."""
    img = get_bg()
    emojis = get_category_emojis(category)
    # Positions fixes pour les emojis de fond
    positions = [
        (80, 120), (900, 200), (150, 500), (850, 600),
        (50, 900), (950, 1000), (200, 1300), (800, 1400),
        (100, 1700), (900, 1750), (500, 300), (500, 1100),
        (300, 700), (700, 800), (400, 1500),
    ]
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw_o = ImageDraw.Draw(overlay)
    ef = bebas(90)
    for i, (x, y) in enumerate(positions):
        emoji = emojis[i % len(emojis)]
        draw_o.text((x, y), emoji, font=ef, fill=(255, 255, 255, 28))
    # Convertit overlay et compose
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    return img_rgba.convert("RGB")


def centered(draw, text, y, font, color, max_w=960, gap=10):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur+" "+w).strip()
        bb = draw.textbbox((0,0), test, font=font)
        if bb[2]-bb[0] <= max_w: cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    lh = font.size + gap
    for i, line in enumerate(lines):
        bb = draw.textbbox((0,0), line, font=font)
        x = (WIDTH-(bb[2]-bb[0]))//2
        draw.text((x, y+i*lh), line, font=font, fill=color)
    return len(lines)*lh


def draw_card(draw, letter, text, x, y, w, h, state="normal"):
    c = {
        "normal":  (CARD_BG,       ACCENT,    ACCENT,    WHITE),
        "correct": ((15,60,35),    CORRECT,   CORRECT,   CORRECT),
        "wrong":   ((55,12,18),    WRONG_COL, WRONG_COL, GRAY),
    }.get(state, (CARD_BG, ACCENT, ACCENT, WHITE))
    bg, border, badge, txt = c
    draw.rounded_rectangle([x,y,x+w,y+h], radius=22, fill=bg)
    draw.rounded_rectangle([x,y,x+w,y+h], radius=22, outline=border, width=3)
    bs = h-16
    draw.rounded_rectangle([x+8,y+8,x+8+bs,y+h-8], radius=12, fill=badge)
    lf = bebas(46)
    lb = draw.textbbox((0,0), letter, font=lf)
    draw.text((x+8+(bs-(lb[2]-lb[0]))//2, y+8+(bs-(lb[3]-lb[1]))//2),
              letter, font=lf, fill=(10,10,30))
    tf = sans(34)
    tb = draw.textbbox((0,0), text, font=tf)
    draw.text((x+bs+24, y+(h-(tb[3]-tb[1]))//2), text, font=tf, fill=txt)


def draw_timer_arc(draw, cx, cy, r, progress, thick=12):
    draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=TIMER_BG, width=thick)
    if progress > 0.01:
        col = CORRECT if progress > 0.5 else (GOLD if progress > 0.25 else WRONG_COL)
        end = -90 + progress*360
        draw.arc([cx-r,cy-r,cx+r,cy+r], start=-90, end=end, fill=col, width=thick)


# ─── FRAMES ─────────────────────────────────────────────────────────────────

def hook_frame(title):
    img = get_bg()
    draw = ImageDraw.Draw(img)
    draw.rectangle([0,0,WIDTH,8], fill=ACCENT)
    centered(draw, "🧠", HEIGHT//2-320, bebas(130), WHITE)
    centered(draw, "SEULS 5% RÉUSSISSENT", HEIGHT//2-180, bebas(100), GOLD)
    centered(draw, "ces 10 questions !", HEIGHT//2-60, sans(52), WHITE)
    centered(draw, "Vas-tu y arriver ? 👇", HEIGHT//2+20, sans(46), GRAY)
    draw.rounded_rectangle([200,HEIGHT//2+140,WIDTH-200,HEIGHT//2+240], radius=28, fill=ACCENT)
    centered(draw, "C'EST PARTI ! 🚀", HEIGHT//2+158, bebas(62), WHITE)
    return img


def question_frame(n, q, countdown_prog):
    """Frame question avec fond dynamique thématique."""
    img = draw_dynamic_bg(q.get("category",""))
    draw = ImageDraw.Draw(img)
    # Header
    draw.rectangle([0,0,WIDTH,105], fill=(12,12,45,220))
    draw.text((45,22), f"QUESTION {n}/10", font=bebas(58), fill=ACCENT)
    # Timer cercle
    cx,cy,r = WIDTH-88, 58, 46
    draw_timer_arc(draw, cx, cy, r, countdown_prog, thick=10)
    secs = max(1, int(countdown_prog * Q_TICK_DUR)+1)
    nf = bebas(48)
    nb = draw.textbbox((0,0), str(secs), font=nf)
    draw.text((cx-(nb[2]-nb[0])//2, cy-(nb[3]-nb[1])//2), str(secs), font=nf, fill=WHITE)
    # Catégorie
    centered(draw, f"▸ {q.get('category','').upper()}", 120, sans(32), GOLD)
    # Question
    qf = bebas(82)
    qh = centered(draw, q["question"].upper(), 180, qf, WHITE, max_w=960)
    # Choix
    letters = ["A","B","C","D"]
    ch, cg = 108, 16
    sy = 200+qh
    for i,l in enumerate(letters):
        draw_card(draw, l, q["choices"][l], 44, sy+i*(ch+cg), WIDTH-88, ch)
    # Bas
    centered(draw, "⏱  Quelle est ta réponse ?", sy+4*(ch+cg)+18, sans(38), GRAY)
    return img


def answer_frame(n, q):
    img = draw_dynamic_bg(q.get("category",""))
    draw = ImageDraw.Draw(img)
    correct = q["correct"]
    draw.rectangle([0,0,WIDTH,105], fill=(12,50,28))
    draw.text((45,22), f"✅  RÉPONSE — Q{n}/10", font=bebas(58), fill=CORRECT)
    centered(draw, f"▸ {q.get('category','').upper()}", 120, sans(32), GOLD)
    qh = centered(draw, q["question"].upper(), 178, bebas(68), WHITE, max_w=960)
    letters = ["A","B","C","D"]
    ch, cg = 108, 14
    sy = 200+qh
    for i,l in enumerate(letters):
        state = "correct" if l==correct else "wrong"
        draw_card(draw, l, q["choices"][l], 44, sy+i*(ch+cg), WIDTH-88, ch, state)
    if q.get("explanation"):
        ey = sy+4*(ch+cg)+20
        draw.rounded_rectangle([40,ey,WIDTH-40,ey+100], radius=18, fill=(12,50,28))
        draw.rounded_rectangle([40,ey,WIDTH-40,ey+100], radius=18, outline=CORRECT, width=2)
        centered(draw, f"💡  {q['explanation']}", ey+16, sans(34), CORRECT, max_w=940)
    return img


def cta_frame():
    img = get_bg()
    draw = ImageDraw.Draw(img)
    centered(draw, "TU AS AIMÉ ? 🎉", 180, bebas(96), GOLD)
    centered(draw, "Soutiens-nous :", 300, sans(46), WHITE)
    items = [("❤️","Like la vidéo",WRONG_COL),("➕","Abonne-toi",ACCENT),
             ("↗️","Partage à tes amis",CORRECT),("💬","Ton score en commentaire",GOLD)]
    for i,(em,txt,col) in enumerate(items):
        y = 400+i*148
        draw.rounded_rectangle([50,y,WIDTH-50,y+122], radius=26, fill=col)
        draw.text((88,y+24), em, font=bebas(64), fill=WHITE)
        draw.text((190,y+30), txt, font=bebas(60), fill=WHITE)
    centered(draw, "🏆  Dis ton score /10 en commentaire !", HEIGHT-140, sans(42), GRAY)
    return img


# ─── AUDIO ──────────────────────────────────────────────────────────────────

async def generate_all_tts(quiz):
    """Génère TOUS les fichiers TTS en une seule session async — corrige le bug voix."""
    tasks = []

    async def save(text, path):
        comm = edge_tts.Communicate(text, VOICE, rate="+5%")
        await comm.save(str(path))

    # Hook
    tasks.append(save(
        "Attention ! Seuls 5% des gens répondent correctement à ces 10 questions. Peux-tu relever le défi ?",
        AUDIO_DIR/"hook.mp3"
    ))
    # CTA
    tasks.append(save(
        "Tu as aimé ce quiz ? Like la vidéo, abonne-toi, partage avec tes amis, et dis-nous ton score en commentaire !",
        AUDIO_DIR/"cta.mp3"
    ))
    # Questions et réponses
    for i, q in enumerate(quiz["questions"]):
        n = i+1
        tasks.append(save(q["question"], AUDIO_DIR/f"q{n:02d}_q.mp3"))
        correct_text = f"La réponse est {q['correct']} : {q['choices'][q['correct']]}. {q.get('explanation','')}"
        tasks.append(save(correct_text, AUDIO_DIR/f"q{n:02d}_ans.mp3"))

    await asyncio.gather(*tasks)
    print(f"  ✓ {len(tasks)} fichiers TTS générés")


def gen_tick(path, duration):
    tmp = Path(tempfile.mkdtemp())
    tick = tmp/"t.mp3"
    sil  = tmp/"s.mp3"
    cyc  = tmp/"c.mp3"
    # Tick court
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=900:duration=0.03",
                    "-af","volume=0.5",str(tick)], capture_output=True)
    # Silence
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
                    "-t","0.47",str(sil)], capture_output=True)
    # Cycle
    lst = tmp/"l.txt"
    lst.write_text(f"file '{tick.resolve()}'\nfile '{sil.resolve()}'\n")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),"-c","copy",str(cyc)],
                   capture_output=True)
    # Répéter
    n = int(duration/0.5)+3
    lst2 = tmp/"l2.txt"
    lst2.write_text(f"file '{cyc.resolve()}'\n"*n)
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst2),
                    "-t",str(duration),str(path)], capture_output=True)


def gen_ding(path):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=880:duration=0.5",
                    "-af","volume=0.8,afade=t=out:st=0.42:d=0.08",str(path)],
                   capture_output=True)


def gen_silence(path, dur):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
                    "-t",str(dur),str(path)], capture_output=True)


def mix_ding_tts(ding, tts_a, output):
    subprocess.run([
        "ffmpeg","-y","-i",str(ding),"-i",str(tts_a),
        "-filter_complex","[0:a][1:a]amix=inputs=2:duration=longest[a]",
        "-map","[a]",str(output)
    ], capture_output=True)


# ─── CLIPS ──────────────────────────────────────────────────────────────────

def still_clip(frame, dur, out):
    tmp = Path(tempfile.mktemp(suffix=".png"))
    frame.save(tmp)
    subprocess.run(["ffmpeg","-y","-loop","1","-i",str(tmp),
                    "-t",str(dur),"-vf",f"fps={FPS}",
                    "-c:v","libx264","-pix_fmt","yuv420p",str(out)],
                   capture_output=True)


def animated_clip(frames, out):
    tmp = Path(tempfile.mkdtemp())
    for i,f in enumerate(frames): f.save(tmp/f"f{i:04d}.png")
    subprocess.run(["ffmpeg","-y","-framerate",str(FPS),"-i",str(tmp/"f%04d.png"),
                    "-c:v","libx264","-pix_fmt","yuv420p",str(out)],
                   capture_output=True)


def merge_va(video, audio, out, dur=None):
    args = ["ffmpeg","-y","-i",str(video),"-i",str(audio)]
    if dur: args += ["-t",str(dur)]
    args += ["-c:v","copy","-c:a","aac","-shortest",str(out)]
    subprocess.run(args, capture_output=True)


def concat(paths, out):
    lst = Path(tempfile.mktemp(suffix=".txt"))
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in paths))
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),
                    "-c","copy",str(out)], capture_output=True)


# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    if not QUIZ_FILE.exists():
        print(f"Erreur : {QUIZ_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(QUIZ_FILE, encoding="utf-8") as f:
        quiz = json.load(f)

    CLIPS_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)

    # 1. Générer TOUT le TTS en une seule session (corrige bug voix)
    print("Génération TTS (toutes questions + réponses)...")
    asyncio.run(generate_all_tts(quiz))

    # 2. Effets sonores
    print("Effets sonores...")
    ding = AUDIO_DIR/"ding.mp3"
    gen_ding(ding)
    tick = AUDIO_DIR/"tick_base.mp3"
    gen_tick(tick, Q_TICK_DUR)

    all_clips = []

    # 3. Hook
    print("Hook...")
    hv = CLIPS_DIR/"hook.mp4"
    still_clip(hook_frame(quiz["title"]), HOOK_DUR, hv)
    hf = CLIPS_DIR/"hook_final.mp4"
    merge_va(hv, AUDIO_DIR/"hook.mp3", hf, HOOK_DUR)
    all_clips.append(hf)

    # 4. Questions
    for i, q in enumerate(quiz["questions"]):
        n = i+1
        print(f"Q{n}/10 : {q['question'][:45]}...")

        # Phase A : TTS lit la question (fond statique, pas de timer)
        qa_frame = question_frame(n, q, 1.0)
        qa_v = CLIPS_DIR/f"q{n:02d}_a.mp4"
        still_clip(qa_frame, Q_TTS_DUR, qa_v)
        qa_f = CLIPS_DIR/f"q{n:02d}_a_final.mp4"
        merge_va(qa_v, AUDIO_DIR/f"q{n:02d}_q.mp3", qa_f, Q_TTS_DUR)

        # Phase B : countdown animé + tick (SILENCE — l'utilisateur réfléchit)
        total_f = int(Q_TICK_DUR * FPS)
        frames = []
        step = max(1, total_f // 30)  # max 30 frames uniques pour la vitesse
        for j in range(0, total_f, step):
            prog = 1.0 - (j / total_f)
            frames += [question_frame(n, q, prog)] * step
        frames = frames[:total_f]
        qb_v = CLIPS_DIR/f"q{n:02d}_b.mp4"
        animated_clip(frames, qb_v)
        qb_f = CLIPS_DIR/f"q{n:02d}_b_final.mp4"
        merge_va(qb_v, tick, qb_f, Q_TICK_DUR)

        # Phase C : réponse (ding + TTS lit la réponse)
        ans_f_img = answer_frame(n, q)
        qc_v = CLIPS_DIR/f"q{n:02d}_c.mp4"
        still_clip(ans_f_img, ANS_DUR, qc_v)
        qc_mixed = AUDIO_DIR/f"q{n:02d}_c_mixed.mp3"
        mix_ding_tts(ding, AUDIO_DIR/f"q{n:02d}_ans.mp3", qc_mixed)
        qc_f = CLIPS_DIR/f"q{n:02d}_c_final.mp4"
        merge_va(qc_v, qc_mixed, qc_f, ANS_DUR)

        # Assemblage question
        qfull = CLIPS_DIR/f"q{n:02d}_full.mp4"
        concat([qa_f, qb_f, qc_f], qfull)
        all_clips.append(qfull)
        print(f"  ✓ Q{n}")

    # 5. CTA
    print("CTA...")
    cv = CLIPS_DIR/"cta.mp4"
    still_clip(cta_frame(), CTA_DUR, cv)
    cf = CLIPS_DIR/"cta_final.mp4"
    merge_va(cv, AUDIO_DIR/"cta.mp3", cf, CTA_DUR)
    all_clips.append(cf)

    # 6. Final
    print("Assemblage final...")
    concat(all_clips, OUTPUT_FILE)
    total = HOOK_DUR + 10*(Q_TTS_DUR+Q_TICK_DUR+ANS_DUR) + CTA_DUR
    print(f"\n✅ {OUTPUT_FILE}")
    print(f"   Durée estimée : {total}s (~{total//60}m{total%60:02d}s)")


if __name__ == "__main__":
    main()
