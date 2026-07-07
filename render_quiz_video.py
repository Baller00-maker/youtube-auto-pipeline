"""
Pipeline Quiz TikTok -- VERSION 4 (production-ready)
Corrections :
- Hook textes sans overlap (y-coords fixes)
- Pas d'emoji dans PIL (→ rectangles sur Linux) : remplacé par formes géométriques
- Durée ~1min35s : hook=3 + 10*(2+4+3) + 5 = 98s
- Cards hauteur dynamique selon longueur du texte
- Grand countdown centré visible pendant la réflexion
- Fond avec motifs "?" semi-transparents (fiables, pas emoji)
- Bebas Neue depuis URL fiable, fallback robuste
- Toutes les questions ET réponses lues (asyncio.gather corrigé)
- merge_va avec -t explicite pour durée exacte
"""

import asyncio, json, math, subprocess, sys, tempfile
from pathlib import Path

import edge_tts
from PIL import Image, ImageDraw, ImageFont

QUIZ_FILE   = Path("quiz_data.json")
OUTPUT_FILE = Path("quiz_final.mp4")
CLIPS_DIR   = Path("quiz_clips")
AUDIO_DIR   = Path("quiz_audio")
FONTS_DIR   = Path("fonts")

W, H  = 1080, 1920
FPS   = 24

# Palette
BG1   = (8,   8,  35)   # top gradient
BG2   = (28,  8,  55)   # bottom gradient
BLUE  = (80, 110, 255)
GOLD  = (255, 200,  0)
GREEN = (30,  210, 110)
RED   = (255,  60,  75)
DARK  = (15,  15,  45)
WHITE = (255, 255, 255)
GRAY  = (150, 150, 175)
CARD  = (22,  22,  58)

# Timing (total ≈ 98s)
HOOK_S  = 3
QQ_S    = 2    # voix lit la question
TICK_S  = 4    # silence + countdown
ANS_S   = 3    # ding + voix lit la réponse
CTA_S   = 5

VOICE = "fr-FR-HenriNeural"

CAT_COLORS = {
    "géographie": (0, 150, 200),
    "histoire":   (180, 80, 0),
    "sciences":   (0, 180, 120),
    "animaux":    (120, 180, 0),
    "sport":      (220, 80, 0),
    "cinéma":     (180, 0, 120),
    "musique":    (100, 0, 200),
    "gastronomie":(200, 100, 0),
    "technologies":(0, 120, 220),
    "insolite":   (150, 0, 180),
}
def cat_color(cat):
    for k,v in CAT_COLORS.items():
        if k in cat.lower(): return v
    return BLUE

# ─── FONTS ──────────────────────────────────────────────────────────────────

def _try_font(path, size):
    try: return ImageFont.truetype(str(path), size)
    except: return None

def bebas(size):
    for p in [FONTS_DIR/"BebasNeue.ttf",
              Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
              Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")]:
        f = _try_font(p, size)
        if f: return f
    return ImageFont.load_default()

def body(size):
    for p in [Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
              Path("/usr/share/fonts/truetype/liberation/LiberationSans.ttf")]:
        f = _try_font(p, size)
        if f: return f
    return ImageFont.load_default()

# ─── DRAWING HELPERS ────────────────────────────────────────────────────────

def gradient_image():
    img = Image.new("RGB", (W, H))
    for y in range(H):
        t = y / H
        img.paste(tuple(int(BG1[i]*(1-t)+BG2[i]*t) for i in range(3)), (0, y, W, y+1))
    return img

_BG = None
def bg(): 
    global _BG
    if _BG is None: _BG = gradient_image()
    return _BG.copy()

def draw_bg_pattern(img, color):
    """Fond avec motifs '?' semi-transparents (fiable sur Linux, pas emoji)."""
    overlay = Image.new("RGBA", (W,H), (0,0,0,0))
    d = ImageDraw.Draw(overlay)
    f_big  = bebas(140)
    f_med  = bebas(90)
    f_sml  = bebas(55)
    alpha  = 35  # semi-transparent
    items = [
        (80,  80,  f_big, "?"),  (820, 140, f_med, "?"),
        (50,  450, f_sml, "?"),  (870, 500, f_big, "?"),
        (200, 820, f_med, "?"),  (750, 900, f_sml, "?"),
        (60,  1200,f_big, "?"),  (880,1150, f_med, "?"),
        (350, 1450,f_sml, "?"),  (700,1550, f_big, "?"),
        (150, 1700,f_med, "?"),  (820,1750, f_sml, "?"),
    ]
    c = (*color, alpha)
    for x,y,f,txt in items:
        d.text((x,y), txt, font=f, fill=c)
    base = img.convert("RGBA")
    out  = Image.alpha_composite(base, overlay)
    return out.convert("RGB")

def measure(draw, text, font):
    bb = draw.textbbox((0,0), text, font=font)
    return bb[2]-bb[0], bb[3]-bb[1]

def put_centered(draw, text, y, font, color, max_w=960, gap=6):
    """Affiche texte multi-ligne centré, retourne hauteur totale."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur+" "+w).strip()
        ww,_ = measure(draw, t, font)
        if ww <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    lh = font.size + gap
    for i,line in enumerate(lines):
        ww,_ = measure(draw, line, font)
        draw.text(((W-ww)//2, y+i*lh), line, font=font, fill=color)
    return len(lines)*lh

def card_text_height(draw, text, font, max_w=800):
    """Hauteur nécessaire pour afficher le texte dans la carte."""
    words = text.split()
    lines, cur = [], ""
    for w in words:
        t = (cur+" "+w).strip()
        ww,_ = measure(draw, t, font)
        if ww <= max_w: cur = t
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    _,lh = measure(draw, "Ag", font)
    return max(1, len(lines)) * (lh+6)

def draw_choice(draw, letter, text, x, y, w, state="normal"):
    """Carte choix avec hauteur dynamique."""
    tf = body(36)
    th = card_text_height(draw, text, tf, max_w=w-120)
    h  = max(90, th + 36)
    c  = {
        "normal":  (CARD,         BLUE,  BLUE,  WHITE),
        "correct": ((12,50,30),   GREEN, GREEN, GREEN),
        "wrong":   ((50,10,15),   RED,   RED,   GRAY),
    }.get(state, (CARD, BLUE, BLUE, WHITE))
    bg_c, border, badge, txt = c
    draw.rounded_rectangle([x,y,x+w,y+h], radius=20, fill=bg_c)
    draw.rounded_rectangle([x,y,x+w,y+h], radius=20, outline=border, width=3)
    bs = h-16
    draw.rounded_rectangle([x+8,y+8,x+8+bs,y+h-8], radius=12, fill=badge)
    lf  = bebas(min(bs-4, 50))
    lw,lhh = measure(draw, letter, lf)
    draw.text((x+8+(bs-lw)//2, y+8+(bs-lhh)//2), letter, font=lf, fill=(10,10,30))
    # texte choix (multiline)
    words = text.split()
    lines, cur = [], ""
    for w2 in words:
        t = (cur+" "+w2).strip()
        ww,_ = measure(draw, t, tf)
        if ww <= w-120: cur = t
        else:
            if cur: lines.append(cur)
            cur = w2
    if cur: lines.append(cur)
    _,llh = measure(draw, "Ag", tf)
    total_th = len(lines)*(llh+6)
    ty = y + (h-total_th)//2
    for line in lines:
        draw.text((x+bs+24, ty), line, font=tf, fill=txt)
        ty += llh+6
    return h

def arc_progress(draw, cx, cy, r, prog, thick=14, col=GREEN):
    draw.ellipse([cx-r,cy-r,cx+r,cy+r], outline=(35,35,70), width=thick)
    if prog > 0.01:
        draw.arc([cx-r,cy-r,cx+r,cy+r], start=-90, end=-90+prog*360, fill=col, width=thick)

# ─── FRAMES ─────────────────────────────────────────────────────────────────

def make_hook(title):
    img = bg()
    draw = ImageDraw.Draw(img)
    # Bande accent
    draw.rectangle([0,0,W,10], fill=BLUE)
    draw.rectangle([0,H-10,W,H], fill=BLUE)
    # Titre gros
    f1 = bebas(118)
    y = 280
    y += put_centered(draw, "SEULS 5% REUSSISSENT", y, f1, GOLD) + 20
    f2 = body(50)
    y += put_centered(draw, "ces 10 questions !", y, f2, WHITE) + 30
    put_centered(draw, "Peux-tu relever le defi ?", y, f2, GRAY)
    # Bouton
    bx1,by1,bx2,by2 = 180, H//2+180, W-180, H//2+290
    draw.rounded_rectangle([bx1,by1,bx2,by2], radius=30, fill=BLUE)
    bf = bebas(68)
    put_centered(draw, "C'EST PARTI !", by1+18, bf, WHITE)
    return img


def make_question(n, q, countdown_prog, phase="think"):
    """
    phase='read'  : voix lit la question, pas de countdown visible
    phase='think' : silence, grand countdown centré
    """
    color = cat_color(q.get("category",""))
    img = draw_bg_pattern(bg(), color)
    draw = ImageDraw.Draw(img)

    # Header
    draw.rectangle([0,0,W,110], fill=(*DARK, 220))
    draw.text((44,20), f"QUESTION {n}/10", font=bebas(60), fill=(*BLUE,))
    # Catégorie
    cf = body(32)
    put_centered(draw, q.get("category","").upper(), 122, cf, (*color,))
    # Question
    qf = bebas(80)
    qh = put_centered(draw, q["question"].upper(), 178, qf, WHITE, max_w=970)
    # Cards
    letters = ["A","B","C","D"]
    cy_c = 200 + qh
    gap  = 14
    card_w = W - 88
    for l in letters:
        ch = draw_choice(draw, l, q["choices"][l], 44, cy_c, card_w, "normal")
        cy_c += ch + gap

    if phase == "think":
        # Grand countdown centré en bas
        secs = max(1, int(countdown_prog * TICK_S) + 1)
        cx_c = W//2
        cy_big = cy_c + 60
        r_big = 90
        prog_col = GREEN if countdown_prog > 0.5 else (GOLD if countdown_prog > 0.25 else RED)
        arc_progress(draw, cx_c, cy_big+r_big, r_big, countdown_prog, thick=16, col=prog_col)
        nf = bebas(120)
        ns = str(secs)
        nw,nh = measure(draw, ns, nf)
        draw.text((cx_c - nw//2, cy_big + r_big - nh//2), ns, font=nf, fill=prog_col)
        # "Reflechis !" en dessous
        pf = body(38)
        put_centered(draw, "Reflechis !", cy_big + 2*r_big + 20, pf, GRAY)
    return img


def make_answer(n, q):
    color = cat_color(q.get("category",""))
    img = draw_bg_pattern(bg(), color)
    draw = ImageDraw.Draw(img)
    correct = q["correct"]
    # Header vert
    draw.rectangle([0,0,W,110], fill=(12,55,30))
    draw.text((44,20), f"REPONSE  Q{n}/10", font=bebas(60), fill=GREEN)
    put_centered(draw, q.get("category","").upper(), 122, body(32), (*color,))
    qh = put_centered(draw, q["question"].upper(), 178, bebas(72), WHITE, max_w=970)
    letters = ["A","B","C","D"]
    cy_c = 200 + qh
    gap  = 12
    card_w = W - 88
    for l in letters:
        state = "correct" if l==correct else "wrong"
        ch = draw_choice(draw, l, q["choices"][l], 44, cy_c, card_w, state)
        cy_c += ch + gap
    # Explication
    if q.get("explanation"):
        ey = cy_c + 16
        draw.rounded_rectangle([40,ey,W-40,ey+95], radius=18, fill=(12,55,30))
        draw.rounded_rectangle([40,ey,W-40,ey+95], radius=18, outline=GREEN, width=2)
        put_centered(draw, q["explanation"], ey+14, body(33), GREEN, max_w=950)
    return img


def make_cta():
    img = bg()
    draw = ImageDraw.Draw(img)
    put_centered(draw, "TU AS AIME ?", 200, bebas(100), GOLD)
    put_centered(draw, "Soutiens-nous :", 330, body(46), WHITE)
    items = [
        ("Like la video",         RED),
        ("Abonne-toi",            BLUE),
        ("Partage a tes amis",    GREEN),
        ("Score en commentaire",  GOLD),
    ]
    for i,(txt,col) in enumerate(items):
        y = 430 + i*148
        draw.rounded_rectangle([50,y,W-50,y+120], radius=26, fill=col)
        tf = bebas(62)
        put_centered(draw, txt, y+22, tf, WHITE)
    put_centered(draw, "Dis ton score /10 en commentaire !", H-140, body(40), GRAY)
    return img

# ─── AUDIO ──────────────────────────────────────────────────────────────────

async def all_tts(quiz):
    async def save(text, path):
        try:
            c = edge_tts.Communicate(text, VOICE, rate="+5%")
            await c.save(str(path))
        except Exception as e:
            print(f"  ! TTS erreur ({path.name}): {e}", file=sys.stderr)

    tasks  = [save(
        "Attention ! Seuls 5 pourcents des gens repondent a ces 10 questions. Peux-tu relever le defi ?",
        AUDIO_DIR/"hook.mp3"
    )]
    tasks += [save(
        "Tu as aime ce quiz ? Like la video, abonne-toi, partage avec tes amis et dis ton score en commentaire !",
        AUDIO_DIR/"cta.mp3"
    )]
    for i,q in enumerate(quiz["questions"]):
        n = i+1
        tasks.append(save(q["question"], AUDIO_DIR/f"q{n:02d}_q.mp3"))
        ans = f"La reponse est {q['correct']} : {q['choices'][q['correct']]}. {q.get('explanation','')}"
        tasks.append(save(ans, AUDIO_DIR/f"q{n:02d}_ans.mp3"))
    await asyncio.gather(*tasks)
    print(f"  TTS OK : {len(tasks)} fichiers")

def gen_ding(out):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=880:duration=0.45",
                    "-af","volume=0.85,afade=t=out:st=0.38:d=0.07",str(out)],
                   capture_output=True, check=False)

def gen_tick(out, dur):
    tmp = Path(tempfile.mkdtemp())
    tick = tmp/"tk.mp3"
    sil  = tmp/"sl.mp3"
    cyc  = tmp/"cy.mp3"
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","sine=frequency=900:duration=0.028",
                    "-af","volume=0.45",str(tick)], capture_output=True, check=False)
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
                    "-t","0.472",str(sil)], capture_output=True, check=False)
    lst1 = tmp/"l1.txt"
    lst1.write_text(f"file '{tick.resolve()}'\nfile '{sil.resolve()}'\n")
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst1),
                    "-c","copy",str(cyc)], capture_output=True, check=False)
    n = int(dur/0.5)+4
    lst2 = tmp/"l2.txt"
    lst2.write_text(f"file '{cyc.resolve()}'\n"*n)
    subprocess.run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(lst2),
                    "-t",str(dur),str(out)], capture_output=True, check=False)

def gen_silence(out, dur):
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i","anullsrc=r=44100:cl=stereo",
                    "-t",str(dur),str(out)], capture_output=True, check=False)

def mix_ding_tts(ding, tts_a, out):
    subprocess.run([
        "ffmpeg","-y","-i",str(ding),"-i",str(tts_a),
        "-filter_complex","[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[a]",
        "-map","[a]",str(out)
    ], capture_output=True, check=False)

# ─── VIDEO HELPERS ──────────────────────────────────────────────────────────

def still_clip(frame, dur, out):
    tmp = Path(tempfile.mktemp(suffix=".png"))
    frame.save(tmp)
    subprocess.run([
        "ffmpeg","-y","-loop","1","-i",str(tmp),
        "-t",str(dur),"-vf",f"fps={FPS}",
        "-c:v","libx264","-pix_fmt","yuv420p","-preset","fast",str(out)
    ], capture_output=True, check=False)

def anim_clip(frames_list, out):
    """Liste de (frame_PIL, nb_repetitions)."""
    tmp = Path(tempfile.mkdtemp())
    idx = 0
    for frame, reps in frames_list:
        p = tmp/f"f{idx:04d}.png"
        frame.save(p)
        for _ in range(reps-1):
            import shutil
            idx2 = idx+1
            shutil.copy(p, tmp/f"f{idx2:04d}.png")
            idx = idx2
        idx += 1
    subprocess.run([
        "ffmpeg","-y","-framerate",str(FPS),"-i",str(tmp/"f%04d.png"),
        "-c:v","libx264","-pix_fmt","yuv420p","-preset","fast",str(out)
    ], capture_output=True, check=False)

def merge_va(video, audio, out, dur):
    """Merge avec durée explicite pour éviter les clips trop longs."""
    subprocess.run([
        "ffmpeg","-y","-i",str(video),"-i",str(audio),
        "-t",str(dur),"-c:v","copy","-c:a","aac",str(out)
    ], capture_output=True, check=False)

def concat(paths, out):
    lst = Path(tempfile.mktemp(suffix=".txt"))
    lst.write_text("".join(f"file '{Path(p).resolve().as_posix()}'\n" for p in paths))
    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(lst),
        "-c","copy",str(out)
    ], capture_output=True, check=False)

# ─── MAIN ───────────────────────────────────────────────────────────────────

def main():
    if not QUIZ_FILE.exists():
        print(f"Erreur : {QUIZ_FILE} introuvable.", file=sys.stderr); sys.exit(1)
    with open(QUIZ_FILE, encoding="utf-8") as f:
        quiz = json.load(f)

    CLIPS_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)

    # 1. TOUT le TTS en une seule session asyncio
    print("Generation TTS (toutes questions + reponses en parallele)...")
    asyncio.run(all_tts(quiz))

    # 2. Effets sonores
    print("Effets sonores...")
    ding_path = AUDIO_DIR/"ding.mp3"
    tick_path = AUDIO_DIR/"tick.mp3"
    gen_ding(ding_path)
    gen_tick(tick_path, TICK_S)

    all_clips = []

    # 3. Hook
    print("Hook...")
    hv = CLIPS_DIR/"hook.mp4";  still_clip(make_hook(quiz["title"]), HOOK_S, hv)
    hf = CLIPS_DIR/"hook_f.mp4"; merge_va(hv, AUDIO_DIR/"hook.mp3", hf, HOOK_S)
    all_clips.append(hf)

    # 4. Questions
    for i, q in enumerate(quiz["questions"]):
        n = i+1
        print(f"Q{n}/10 '{q['question'][:40]}...'")

        # Phase A : voix lit la question (image statique)
        qa_v = CLIPS_DIR/f"q{n:02d}a.mp4"; still_clip(make_question(n,q,1.0,"read"), QQ_S, qa_v)
        qa_f = CLIPS_DIR/f"q{n:02d}af.mp4"; merge_va(qa_v, AUDIO_DIR/f"q{n:02d}_q.mp3", qa_f, QQ_S)

        # Phase B : countdown animé + tic (SILENCE)
        total_fr = TICK_S * FPS
        steps    = 20  # 20 frames uniques max
        frame_list = []
        for s in range(steps):
            prog  = 1.0 - s/steps
            reps  = total_fr // steps + (1 if s < total_fr % steps else 0)
            frame_list.append((make_question(n, q, prog, "think"), reps))
        qb_v = CLIPS_DIR/f"q{n:02d}b.mp4"; anim_clip(frame_list, qb_v)
        qb_f = CLIPS_DIR/f"q{n:02d}bf.mp4"; merge_va(qb_v, tick_path, qb_f, TICK_S)

        # Phase C : réponse (ding + voix)
        qc_v = CLIPS_DIR/f"q{n:02d}c.mp4"; still_clip(make_answer(n,q), ANS_S, qc_v)
        qc_m = AUDIO_DIR/f"q{n:02d}cm.mp3"; mix_ding_tts(ding_path, AUDIO_DIR/f"q{n:02d}_ans.mp3", qc_m)
        qc_f = CLIPS_DIR/f"q{n:02d}cf.mp4"; merge_va(qc_v, qc_m, qc_f, ANS_S)

        # Assemblage question complète
        qfull = CLIPS_DIR/f"q{n:02d}_full.mp4"; concat([qa_f, qb_f, qc_f], qfull)
        all_clips.append(qfull)
        print(f"  Q{n} OK")

    # 5. CTA
    print("CTA...")
    cv = CLIPS_DIR/"cta.mp4";  still_clip(make_cta(), CTA_S, cv)
    cf = CLIPS_DIR/"cta_f.mp4"; merge_va(cv, AUDIO_DIR/"cta.mp3", cf, CTA_S)
    all_clips.append(cf)

    # 6. Assemblage final
    print("Assemblage final...")
    concat(all_clips, OUTPUT_FILE)
    total = HOOK_S + 10*(QQ_S+TICK_S+ANS_S) + CTA_S
    print(f"\nDone: {OUTPUT_FILE}")
    print(f"Duree estimee : {total}s (~{total//60}m{total%60:02d}s)")

if __name__ == "__main__":
    main()
