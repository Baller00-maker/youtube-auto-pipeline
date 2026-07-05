"""
Pipeline Quiz TikTok -- Étape 2 : rendu vidéo complet
- Lit quiz_data.json
- Génère chaque frame avec Pillow (fond blanc éduratif, typographie propre)
- Structure : intro → 10 questions (timer + révélation) → call to action TikTok
- Effets sonores générés par ffmpeg (ding/buzzer)
- Narration TTS via Edge-TTS (voix française enthousiaste)
- Sauvegarde quiz_final.mp4
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
FRAMES_DIR = Path("quiz_frames")
AUDIO_DIR = Path("quiz_audio")

WIDTH, HEIGHT = 1080, 1920
FPS = 30
BG_COLOR = (255, 255, 255)
TEXT_COLOR = (30, 30, 30)
ACCENT_COLOR = (99, 102, 241)      # violet éducatif
CORRECT_COLOR = (34, 197, 94)      # vert
WRONG_COLOR = (239, 68, 68)        # rouge
TIMER_COLOR = (251, 146, 60)       # orange
CATEGORY_COLOR = (148, 163, 184)   # gris clair

VOICE = "fr-FR-DeniseNeural"
QUESTION_DURATION = 6   # secondes pour répondre
ANSWER_DURATION = 5     # secondes pour voir la réponse
INTRO_DURATION = 3
CTA_DURATION = 8


def get_font(size, bold=False):
    """Charge une police système ou retourne la police par défaut."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                pass
    return ImageFont.load_default()


def wrap_text(text, font, max_width, draw):
    """Découpe le texte en lignes pour tenir dans max_width."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_centered_text(draw, text, y, font, color, max_width=900):
    """Dessine du texte centré horizontalement."""
    lines = wrap_text(text, font, max_width, draw)
    line_height = font.size + 10
    total_height = len(lines) * line_height
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, y + i * line_height), line, font=font, fill=color)
    return total_height


def draw_choice_box(draw, letter, text, x, y, w, h, state="normal"):
    """Dessine une boîte de choix (normal, correct, wrong)."""
    colors = {
        "normal": {"bg": (248, 250, 252), "border": (226, 232, 240), "text": TEXT_COLOR, "letter_bg": ACCENT_COLOR},
        "correct": {"bg": (240, 253, 244), "border": CORRECT_COLOR, "text": (21, 128, 61), "letter_bg": CORRECT_COLOR},
        "wrong": {"bg": (254, 242, 242), "border": WRONG_COLOR, "text": (185, 28, 28), "letter_bg": WRONG_COLOR},
        "dim": {"bg": (248, 250, 252), "border": (226, 232, 240), "text": (200, 200, 200), "letter_bg": (200, 200, 200)},
    }
    c = colors.get(state, colors["normal"])
    radius = 20
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=c["bg"], outline=c["border"], width=3)
    letter_size = h - 20
    draw.rounded_rectangle([x+10, y+10, x+10+letter_size, y+h-10], radius=12, fill=c["letter_bg"])
    letter_font = get_font(36, bold=True)
    lb = draw.textbbox((0, 0), letter, font=letter_font)
    lx = x + 10 + (letter_size - (lb[2]-lb[0])) // 2
    ly = y + 10 + (h - 20 - (lb[3]-lb[1])) // 2
    draw.text((lx, ly), letter, font=letter_font, fill=(255, 255, 255))
    text_font = get_font(34)
    text_lines = wrap_text(text, text_font, w - letter_size - 40, draw)
    line_h = text_font.size + 6
    total = len(text_lines) * line_h
    ty = y + (h - total) // 2
    for line in text_lines:
        draw.text((x + letter_size + 30, ty), line, font=text_font, fill=c["text"])
        ty += line_h


def draw_timer_bar(draw, progress, y=160):
    """Dessine une barre de progression timer."""
    margin = 60
    bar_w = WIDTH - 2 * margin
    bar_h = 14
    draw.rounded_rectangle([margin, y, margin+bar_w, y+bar_h], radius=7, fill=(229, 231, 235))
    fill_w = int(bar_w * progress)
    if fill_w > 0:
        color = CORRECT_COLOR if progress > 0.5 else (TIMER_COLOR if progress > 0.25 else WRONG_COLOR)
        draw.rounded_rectangle([margin, y, margin+fill_w, y+bar_h], radius=7, fill=color)


def make_intro_frame(title, question_count=10):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, WIDTH, 8], fill=ACCENT_COLOR)
    draw.rectangle([0, HEIGHT-8, WIDTH, HEIGHT], fill=ACCENT_COLOR)
    emoji_font = get_font(120)
    draw_centered_text(draw, "🧠", HEIGHT//2 - 280, emoji_font, TEXT_COLOR)
    title_font = get_font(72, bold=True)
    draw_centered_text(draw, title, HEIGHT//2 - 120, title_font, TEXT_COLOR)
    sub_font = get_font(48)
    draw_centered_text(draw, f"{question_count} questions • Sauras-tu toutes y répondre ?", HEIGHT//2 + 60, sub_font, CATEGORY_COLOR)
    start_font = get_font(52, bold=True)
    draw.rounded_rectangle([240, HEIGHT//2 + 180, WIDTH-240, HEIGHT//2 + 280], radius=30, fill=ACCENT_COLOR)
    sb = draw.textbbox((0,0), "C'est parti ! 🚀", font=start_font)
    sx = (WIDTH - (sb[2]-sb[0])) // 2
    draw.text((sx, HEIGHT//2 + 200), "C'est parti ! 🚀", font=start_font, fill=(255,255,255))
    return img


def make_question_frame(q_num, question_data, progress):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, WIDTH, 140], fill=ACCENT_COLOR)
    num_font = get_font(52, bold=True)
    draw_centered_text(draw, f"Question {q_num}/10", 45, num_font, (255,255,255))
    draw_timer_bar(draw, progress, y=155)
    cat_font = get_font(36)
    draw_centered_text(draw, f"📚 {question_data['category'].upper()}", 200, cat_font, ACCENT_COLOR)
    q_font = get_font(56, bold=True)
    q_h = draw_centered_text(draw, question_data["question"], 290, q_font, TEXT_COLOR)
    choices = question_data["choices"]
    letters = ["A", "B", "C", "D"]
    box_h = 130
    box_w = WIDTH - 80
    start_y = 430 + q_h
    for i, letter in enumerate(letters):
        draw_choice_box(draw, letter, choices[letter], 40, start_y + i * (box_h + 18), box_w, box_h, "normal")
    return img


def make_answer_frame(q_num, question_data, show_explanation=False):
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, WIDTH, 140], fill=CORRECT_COLOR)
    num_font = get_font(52, bold=True)
    draw_centered_text(draw, f"✅ Réponse Question {q_num}/10", 45, num_font, (255,255,255))
    cat_font = get_font(36)
    draw_centered_text(draw, f"📚 {question_data['category'].upper()}", 180, cat_font, CORRECT_COLOR)
    q_font = get_font(52, bold=True)
    q_h = draw_centered_text(draw, question_data["question"], 260, q_font, TEXT_COLOR)
    choices = question_data["choices"]
    correct = question_data["correct"]
    letters = ["A", "B", "C", "D"]
    box_h = 130
    box_w = WIDTH - 80
    start_y = 400 + q_h
    for i, letter in enumerate(letters):
        state = "correct" if letter == correct else "wrong"
        draw_choice_box(draw, letter, choices[letter], 40, start_y + i * (box_h + 18), box_w, box_h, state)
    if show_explanation and question_data.get("explanation"):
        exp_y = start_y + 4 * (box_h + 18) + 20
        exp_font = get_font(38)
        draw.rounded_rectangle([40, exp_y, WIDTH-40, exp_y+100], radius=16, fill=(240, 253, 244))
        draw_centered_text(draw, f"💡 {question_data['explanation']}", exp_y + 18, exp_font, (21, 128, 61), max_width=920)
    return img


def make_cta_frame():
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, WIDTH, HEIGHT], fill=(15, 15, 15))
    title_font = get_font(72, bold=True)
    draw_centered_text(draw, "Tu as aimé ce quiz ? 🎉", 180, title_font, (255,255,255))
    sub_font = get_font(48)
    draw_centered_text(draw, "Soutiens-nous en :", 310, sub_font, (200,200,200))
    actions = [
        ("❤️", "Like la vidéo", WRONG_COLOR),
        ("➕", "Abonne-toi", ACCENT_COLOR),
        ("↗️", "Partage à tes amis", CORRECT_COLOR),
        ("💬", "Commente ton score", TIMER_COLOR),
    ]
    for i, (emoji, text, color) in enumerate(actions):
        y = 420 + i * 160
        draw.rounded_rectangle([60, y, WIDTH-60, y+130], radius=24, fill=color)
        e_font = get_font(60)
        eb = draw.textbbox((0,0), emoji, font=e_font)
        draw.text((100, y + (130-(eb[3]-eb[1]))//2), emoji, font=e_font, fill=(255,255,255))
        t_font = get_font(52, bold=True)
        tb = draw.textbbox((0,0), text, font=t_font)
        ty = y + (130-(tb[3]-tb[1]))//2
        draw.text((200, ty), text, font=t_font, fill=(255,255,255))
    score_font = get_font(44)
    draw_centered_text(draw, "📊 Dis ton score en commentaire !", HEIGHT-180, score_font, (200,200,200))
    return img


async def generate_tts(text, output_path):
    communicate = edge_tts.Communicate(text, VOICE, rate="+5%")
    await communicate.save(str(output_path))


def generate_beep(output_path, freq=880, duration=0.4, volume=0.7):
    """Génère un son ding via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency={freq}:duration={duration}",
        "-af", f"volume={volume},afade=t=out:st={duration-0.1}:d=0.1",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True)


def generate_buzzer(output_path, duration=0.3):
    """Génère un buzzer via ffmpeg."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"sine=frequency=200:duration={duration}",
        "-af", f"volume=0.5,afade=t=out:st={duration-0.05}:d=0.05",
        str(output_path)
    ]
    subprocess.run(cmd, capture_output=True)


def frames_to_video(frames, duration, output, fps=FPS):
    """Convertit une liste de frames PIL en clip vidéo silencieux."""
    tmp_dir = Path(tempfile.mkdtemp())
    for i, frame in enumerate(frames):
        frame.save(tmp_dir / f"frame_{i:04d}.png")
    total_frames = int(duration * fps)
    if len(frames) == 1:
        cmd = [
            "ffmpeg", "-y", "-loop", "1",
            "-i", str(tmp_dir / "frame_0000.png"),
            "-t", str(duration),
            "-vf", f"fps={fps}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(output)
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-framerate", str(fps),
            "-i", str(tmp_dir / "frame_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(output)
        ]
    subprocess.run(cmd, capture_output=True)


def merge_video_audio(video, audio, output, video_duration=None):
    """Fusionne une vidéo silencieuse avec un audio."""
    args = ["ffmpeg", "-y", "-i", str(video), "-i", str(audio)]
    if video_duration:
        args += ["-t", str(video_duration)]
    args += [
        "-c:v", "copy", "-c:a", "aac",
        "-shortest", str(output)
    ]
    subprocess.run(args, capture_output=True)


def concat_videos(video_paths, output):
    """Concatène plusieurs vidéos en une seule."""
    list_file = Path(tempfile.mktemp(suffix=".txt"))
    with open(list_file, "w") as f:
        for p in video_paths:
            f.write(f"file '{Path(p).resolve().as_posix()}'\n")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy", str(output)
    ]
    subprocess.run(cmd, capture_output=True)


def make_silent_audio(duration, output):
    """Génère un silence audio de la durée donnée."""
    cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"anullsrc=r=44100:cl=stereo:d={duration}",
        "-t", str(duration),
        str(output)
    ]
    subprocess.run(cmd, capture_output=True)


def main():
    if not QUIZ_FILE.exists():
        print(f"Erreur : {QUIZ_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(QUIZ_FILE, "r", encoding="utf-8") as f:
        quiz = json.load(f)

    FRAMES_DIR.mkdir(exist_ok=True)
    AUDIO_DIR.mkdir(exist_ok=True)

    print("Génération des effets sonores...")
    ding_path = AUDIO_DIR / "ding.mp3"
    buzzer_path = AUDIO_DIR / "buzzer.mp3"
    generate_beep(ding_path, freq=880, duration=0.5)
    generate_beep(AUDIO_DIR / "start.mp3", freq=660, duration=0.3)
    generate_buzzer(buzzer_path)

    clips = []

    print("Rendu intro...")
    intro_frame = make_intro_frame(quiz["title"])
    intro_video = FRAMES_DIR / "clip_intro.mp4"
    frames_to_video([intro_frame], INTRO_DURATION, intro_video)
    intro_tts = AUDIO_DIR / "intro_tts.mp3"
    asyncio.run(generate_tts(f"Bienvenue ! {quiz['title']}. Commençons !", intro_tts))
    intro_final = FRAMES_DIR / "clip_intro_final.mp4"
    merge_video_audio(intro_video, intro_tts, intro_final, INTRO_DURATION)
    clips.append(intro_final)

    for i, q in enumerate(quiz["questions"]):
        q_num = i + 1
        print(f"Rendu question {q_num}/10 : {q['question'][:50]}...")

        q_frames = []
        total_q_frames = int(QUESTION_DURATION * FPS)
        for frame_idx in range(total_q_frames):
            progress = 1.0 - (frame_idx / total_q_frames)
            q_frames.append(make_question_frame(q_num, q, progress))

        q_video = FRAMES_DIR / f"clip_q{q_num:02d}_question.mp4"
        q_tts = AUDIO_DIR / f"q{q_num:02d}_tts.mp3"
        q_final = FRAMES_DIR / f"clip_q{q_num:02d}_final.mp4"

        frames_to_video(q_frames, QUESTION_DURATION, q_video, fps=FPS)
        asyncio.run(generate_tts(
            f"Question {q_num}. {q['question']}. "
            f"A : {q['choices']['A']}. B : {q['choices']['B']}. "
            f"C : {q['choices']['C']}. D : {q['choices']['D']}.",
            q_tts
        ))
        merge_video_audio(q_video, q_tts, q_final, QUESTION_DURATION)
        clips.append(q_final)

        print(f"  Rendu réponse {q_num}/10...")
        ans_frames_1 = [make_answer_frame(q_num, q, show_explanation=False)] * int(FPS * 1.5)
        ans_frames_2 = [make_answer_frame(q_num, q, show_explanation=True)] * int(FPS * (ANSWER_DURATION - 1.5))
        ans_frames = ans_frames_1 + ans_frames_2

        ans_video = FRAMES_DIR / f"clip_q{q_num:02d}_answer.mp4"
        ans_tts = AUDIO_DIR / f"q{q_num:02d}_ans_tts.mp3"
        ans_final = FRAMES_DIR / f"clip_q{q_num:02d}_ans_final.mp4"

        frames_to_video(ans_frames, ANSWER_DURATION, ans_video, fps=FPS)
        asyncio.run(generate_tts(
            f"La réponse est {q['correct']} : {q['choices'][q['correct']]}. {q.get('explanation', '')}",
            ans_tts
        ))

        # Mixe ding + TTS pour la révélation de réponse
        mixed_audio = AUDIO_DIR / f"q{q_num:02d}_mixed.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(ans_tts),
            "-i", str(ding_path),
            "-filter_complex",
            "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0.5[a]",
            "-map", "[a]",
            str(mixed_audio)
        ]
        subprocess.run(cmd, capture_output=True)
        merge_video_audio(ans_video, mixed_audio, ans_final, ANSWER_DURATION)
        clips.append(ans_final)

    print("Rendu call to action...")
    cta_frame = make_cta_frame()
    cta_video = FRAMES_DIR / "clip_cta.mp4"
    cta_tts = AUDIO_DIR / "cta_tts.mp3"
    cta_final = FRAMES_DIR / "clip_cta_final.mp4"
    frames_to_video([cta_frame], CTA_DURATION, cta_video)
    asyncio.run(generate_tts(
        "Tu as aimé ce quiz ? Like la vidéo, abonne-toi, partage avec tes amis et dis-nous ton score en commentaire !",
        cta_tts
    ))
    merge_video_audio(cta_video, cta_tts, cta_final, CTA_DURATION)
    clips.append(cta_final)

    print("Assemblage final...")
    concat_videos(clips, OUTPUT_FILE)
    print(f"\nVidéo finale : {OUTPUT_FILE}")

    # Calcul durée estimée
    total = INTRO_DURATION + 10 * (QUESTION_DURATION + ANSWER_DURATION) + CTA_DURATION
    print(f"Durée estimée : {total}s ({total//60}m{total%60:02d}s)")


if __name__ == "__main__":
    main()
