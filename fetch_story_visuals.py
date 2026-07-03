"""
Pipeline "Histoires dramatiques" -- Étape 3 : génération d'images IA via Pollinations.ai
- Gratuit, sans clé API
- Format vertical 1080x1920 (TikTok/Shorts)
- Style : illustration cinématographique africaine, éclairage dramatique
- Description de personnage répétée dans chaque prompt pour maximiser la cohérence
- Sauvegarde story_assets/ + story_visuals.json
"""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_FILE = Path("story_script.json")
ASSETS_DIR = Path("story_assets")
OUTPUT_FILE = Path("story_visuals.json")

WIDTH, HEIGHT = 1080, 1920
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Style visuel fixe appliqué à chaque image
STYLE_SUFFIX = (
    ", digital illustration, African characters, cinematic dramatic lighting, "
    "emotional close-up, vertical composition 9:16, vivid colors, film quality, "
    "highly detailed, professional artwork"
)

# Description des personnages principaux, répétée dans chaque prompt pour la cohérence
FEMALE_CHAR = "a beautiful West African woman in her 30s, dark skin, long braided hair, wearing a colorful dress"
MALE_CHAR = "a West African man in his 30s, dark skin, short hair, wearing a formal shirt"


def build_image_prompt(scene_prompt, story_topic):
    """Enrichit le prompt de base avec le style et les descriptions de personnages fixes."""
    prompt = scene_prompt
    if "woman" in scene_prompt.lower() or "femme" in scene_prompt.lower() or "wife" in scene_prompt.lower():
        prompt = f"{FEMALE_CHAR}, {prompt}"
    if "man" in scene_prompt.lower() or "homme" in scene_prompt.lower() or "husband" in scene_prompt.lower():
        if MALE_CHAR not in prompt:
            prompt = f"{prompt}, with {MALE_CHAR} nearby"
    prompt += STYLE_SUFFIX
    return prompt


def generate_image(prompt, seed, dest_path, timeout=90):
    encoded = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_BASE}{encoded}?width={WIDTH}&height={HEIGHT}&seed={seed}&nologo=true&model=flux"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest_path, "wb") as out:
        data = resp.read()
        if len(data) < 5000:
            raise ValueError(f"Image trop petite ({len(data)} octets), probablement une erreur")
        out.write(data)


def main():
    if not SCRIPT_FILE.exists():
        print(f"Erreur : {SCRIPT_FILE} introuvable.", file=sys.stderr)
        sys.exit(1)

    with open(SCRIPT_FILE, "r", encoding="utf-8") as f:
        story = json.load(f)

    ASSETS_DIR.mkdir(exist_ok=True)
    scenes = story["scenes"]

    # Seed fixe pour toute l'histoire (aide à la cohérence visuelle entre scènes)
    story_seed = abs(hash(story.get("topic", "default"))) % 100_000

    manifest = []
    for i, scene in enumerate(scenes):
        raw_prompt = scene.get("image_prompt") or scene.get("pexels_query", "dramatic emotional scene")
        prompt = build_image_prompt(raw_prompt, story.get("topic", ""))
        dest = ASSETS_DIR / f"story_scene_{i:02d}.jpg"

        print(f"[{i+1}/{len(scenes)}] Génération image...")
        print(f"  Prompt : {prompt[:100]}...")

        success = False
        for attempt in range(1, 4):
            try:
                generate_image(prompt, story_seed + i, dest)
                success = True
                break
            except Exception as e:
                print(f"  ! Tentative {attempt}/3 échouée : {e}", file=sys.stderr)
                time.sleep(5)

        if not success:
            print(f"  ! Scène {i} ignorée après 3 tentatives.", file=sys.stderr)
            continue

        manifest.append({
            "index": i,
            "narration_fr": scene["narration_fr"],
            "image_prompt": prompt,
            "type": "image",
            "path": str(dest),
        })
        time.sleep(2)  # ménage l'API Pollinations

    if not manifest:
        print("Erreur : aucune image générée.", file=sys.stderr)
        sys.exit(1)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n{len(manifest)}/{len(scenes)} images générées.")
    print(f"Manifeste : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
