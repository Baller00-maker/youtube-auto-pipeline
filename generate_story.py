"""
Pipeline "Histoires dramatiques" -- Étape 1 : génération du script + scènes
- Choisit un thème (depuis story_topics.txt, sans répéter)
- Génère un script dramatique COMPLET en FRANÇAIS, narration à la première personne,
  visant 1-2 minutes de narration (~200-280 mots)
- Découpe le script en scènes avec des requêtes de recherche Pexels pour chaque scène
- Sauvegarde story_script.json
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = "meta/llama-3.1-70b-instruct"

TOPICS_FILE = Path("story_topics.txt")
USED_TOPICS_FILE = Path("story_used_topics.txt")
OUTPUT_FILE = Path("story_script.json")

TARGET_WORDS_MIN = 450
TARGET_WORDS_MAX = 600  # ~3-4 min en narration française dramatique


def call_llm(client, prompt, max_tokens=4096, max_retries=3):
    last_error = None
    for attempt in range(1, max_retries + 1):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.85,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
        last_error = "réponse vide"
        print(f"  ! Tentative {attempt}/{max_retries} : {last_error}, nouvel essai...", file=sys.stderr)
        time.sleep(3)
    raise RuntimeError(f"API sans réponse après {max_retries} tentatives.")


def pick_topic():
    if not TOPICS_FILE.exists():
        return None
    all_topics = [t.strip() for t in TOPICS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()]
    used = set()
    if USED_TOPICS_FILE.exists():
        used = set(t.strip() for t in USED_TOPICS_FILE.read_text(encoding="utf-8").splitlines())
    available = [t for t in all_topics if t not in used]
    if not available:
        return None
    topic = random.choice(available)
    with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
        f.write(topic + "\n")
    return topic


def generate_new_topic(client):
    prompt = (
        "Propose ONE single emotionally dramatic family/relationship story premise, "
        "in the style of viral TikTok story-time videos (betrayal, secrets, inheritance, "
        "family conflict). Reply with ONLY the premise in one sentence, in English, no quotes."
    )
    return call_llm(client, prompt, max_tokens=64)


def generate_story(client, topic):
    target_words = random.randint(TARGET_WORDS_MIN, TARGET_WORDS_MAX)
    prompt = f"""You are a viral scriptwriter for emotional family-drama story-time videos
(the kind seen on TikTok accounts that narrate dramatic family secrets and betrayals).

Story premise: "{topic}"

Write the FULL narration script IN FRENCH, first-person point of view, dramatic and emotional
tone, with a strong hook in the FIRST sentence (something shocking or intriguing), a twist or
revelation in the middle, and a satisfying emotional resolution at the end.
Target length: approximately {target_words} words in French. THIS IS MANDATORY -- do not stop
early. Develop the story with rich emotional detail, inner monologue, and vivid descriptions
to reach this word count naturally.

Then break the script into 10 to 15 short SCENES for illustration. For each scene provide:
- "narration_fr": the exact portion of the French script for this scene
- "pexels_query": a 2-4 word English search query for Pexels stock footage that visually
  matches this scene (focus on emotions and settings: e.g. "woman crying bedroom",
  "family argument living room", "man shocked face", "couple fighting kitchen")

Return ONLY a valid JSON object, no markdown, no explanation:
{{
  "title": "short French title for the video",
  "full_script_fr": "the complete French narration script",
  "scenes": [
    {{"narration_fr": "...", "pexels_query": "..."}}
  ]
}}"""

    for attempt in range(1, 4):
        text = call_llm(client, prompt, max_tokens=4096)
        cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip()).strip()
        if not cleaned:
            print(f"  ! Tentative {attempt}/3 : réponse vide après nettoyage.", file=sys.stderr)
            time.sleep(3)
            continue
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"  ! Tentative {attempt}/3 : JSON invalide ({e}). Texte : {cleaned[:200]!r}", file=sys.stderr)
            time.sleep(3)
    raise RuntimeError("Impossible d'obtenir un JSON valide après 3 tentatives.")


def main():
    if not NVIDIA_API_KEY:
        print("Erreur : NVIDIA_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)

    print("Sélection du thème...")
    topic = pick_topic()
    if topic is None:
        print("Liste épuisée, génération d'un nouveau thème...")
        topic = generate_new_topic(client)
    print(f"Thème retenu : {topic}")

    print("Génération du script + découpage en scènes...")
    story = generate_story(client, topic)
    word_count = len(story["full_script_fr"].split())
    print(f"Script : {word_count} mots, {len(story['scenes'])} scènes")

    story["topic"] = topic
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(story, f, ensure_ascii=False, indent=2)
    print(f"Sauvegardé dans {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
