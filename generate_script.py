"""
Étape 2-3 du pipeline :
- Lit reference.json (transcription collectée à l'étape 1)
- Appel LLM n°1 : extrait le PROFIL DE STYLE (structure, rythme, ton) -- pas le texte verbatim
- Choisit un sujet (depuis topics.txt, sans répéter ceux déjà utilisés)
- Appel LLM n°2 : génère un script ORIGINAL sur ce sujet, en respectant le profil de style
  -> Cet appel ne reçoit JAMAIS le texte source, uniquement le profil JSON abstrait
- Sauvegarde le script final dans script.json pour l'étape suivante (production vidéo)

Utilise NVIDIA NIM (endpoint compatible OpenAI), gratuit, sans carte bancaire requise.
"""

import json
import os
import random
import re
import sys
from pathlib import Path

from openai import OpenAI

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = "meta/llama-3.1-70b-instruct"  # bon compromis qualité/disponibilité gratuite

TOPICS_FILE = Path("topics.txt")
USED_TOPICS_FILE = Path("used_topics.txt")
REFERENCE_FILE = Path("reference.json")
OUTPUT_FILE = Path("script.json")

TARGET_WORD_COUNT_MIN = 1200  # ~8-9 min à un rythme parlé normal
TARGET_WORD_COUNT_MAX = 2000  # ~13-15 min


def load_reference():
    with open(REFERENCE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_topic():
    """Choisit un sujet non utilisé depuis topics.txt. Si la liste est épuisée, retourne None
    (le script appellera alors le LLM pour en générer un nouveau)."""
    if not TOPICS_FILE.exists():
        return None

    all_topics = [t.strip() for t in TOPICS_FILE.read_text(encoding="utf-8").splitlines() if t.strip()]
    used_topics = set()
    if USED_TOPICS_FILE.exists():
        used_topics = set(t.strip() for t in USED_TOPICS_FILE.read_text(encoding="utf-8").splitlines())

    available = [t for t in all_topics if t not in used_topics]
    if not available:
        return None

    topic = random.choice(available)
    with open(USED_TOPICS_FILE, "a", encoding="utf-8") as f:
        f.write(topic + "\n")
    return topic


def call_llm(client, prompt, max_tokens=4096):
    """Appel générique au modèle via l'endpoint compatible OpenAI de NVIDIA NIM."""
    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content.strip()


def generate_new_topic(client):
    """Si la liste de sujets est épuisée, demande au LLM d'en proposer un nouveau,
    cohérent avec la niche (histoire militaire / guerre)."""
    prompt = (
        "You are a content strategist for a military history YouTube channel. "
        "Propose ONE single specific, compelling video topic about a historical war, "
        "battle, or military event that would perform well on YouTube. "
        "Reply with ONLY the topic title, nothing else, no quotes, no explanation."
    )
    return call_llm(client, prompt, max_tokens=64)


def extract_style_profile(client, transcript):
    """Appel LLM n°1 : extraction du profil de style structurel.
    IMPORTANT: on demande explicitement de NE PAS reproduire le texte source."""
    prompt = f"""Analyze the following YouTube video transcript and extract its STRUCTURAL style profile.

Do NOT quote or reproduce any sentence from the transcript. Only describe HOW it is written.

Extract and return ONLY a valid JSON object with these fields:
- "hook_type": how the video opens (e.g. "shocking statistic", "rhetorical question", "in-media-res action scene")
- "narrative_structure": ordered list of the narrative beats/stages used (e.g. ["context setup", "rising tension", "turning point", "climax", "resolution", "call to action"])
- "tone": overall tone (e.g. "serious and dramatic", "fast-paced and urgent")
- "pacing_notes": how pacing changes through the video (slow build vs fast cuts, etc.)
- "sentence_style": typical sentence length and rhythm (short punchy vs long descriptive)
- "emotional_triggers": list of emotional techniques used (e.g. "stakes for individual soldiers", "ticking clock tension")
- "transitions": how the narrator moves between sections
- "direct_address": whether/how the narrator speaks directly to the viewer
- "estimated_words_per_minute": a number estimate

TRANSCRIPT:
{transcript}

Return ONLY the JSON object, no markdown formatting, no explanation."""

    text = call_llm(client, prompt, max_tokens=1024)
    text = re.sub(r"^```json\s*|\s*```$", "", text.strip())
    return json.loads(text)


def generate_script(client, style_profile, topic, target_words):
    """Appel LLM n°2 : génération du script ORIGINAL.
    Ne reçoit QUE le profil de style abstrait + le sujet -- jamais le texte source."""
    prompt = f"""You are a professional scriptwriter for a military history YouTube channel.

Write a COMPLETE, ORIGINAL video script about this topic: "{topic}"

The script must follow this STYLE PROFILE (structure and tone only -- all content must be
entirely original and factually accurate about the topic above):

{json.dumps(style_profile, indent=2)}

Requirements:
- Target length: approximately {target_words} words (this is critical, stay within 5% of this number)
- Follow the narrative_structure beats in order
- Match the tone, sentence_style, and pacing_notes described above
- Use the emotional_triggers techniques naturally
- This is a voice-over narration script: write it as continuous spoken narration, NOT as a
  screenplay with scene directions. No camera directions, no [brackets], no headers.
- Be historically accurate -- do not invent fake events, only dramatize real history
- End with a natural closing line (no generic "like and subscribe" -- something thematic)

Write the full script now."""

    return call_llm(client, prompt, max_tokens=4096)


def main():
    if not NVIDIA_API_KEY:
        print("Erreur : NVIDIA_API_KEY n'est pas définie dans les variables d'environnement.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)

    print("Chargement de la vidéo de référence...")
    reference = load_reference()
    print(f"Référence : {reference['title']} ({reference['view_count']} vues)")

    print("Extraction du profil de style (appel LLM #1)...")
    style_profile = extract_style_profile(client, reference["transcript"])
    print("Profil de style extrait :")
    print(json.dumps(style_profile, indent=2, ensure_ascii=False))

    print("\nSélection du sujet...")
    topic = pick_topic()
    if topic is None:
        print("Liste de sujets épuisée, génération d'un nouveau sujet via le LLM...")
        topic = generate_new_topic(client)
    print(f"Sujet retenu : {topic}")

    target_words = random.randint(TARGET_WORD_COUNT_MIN, TARGET_WORD_COUNT_MAX)
    print(f"\nGénération du script original (appel LLM #2, cible {target_words} mots)...")
    script_text = generate_script(client, style_profile, topic, target_words)
    actual_words = len(script_text.split())
    print(f"Script généré : {actual_words} mots")

    output = {
        "topic": topic,
        "style_profile": style_profile,
        "target_words": target_words,
        "actual_words": actual_words,
        "script": script_text,
        "reference_video_id": reference["video_id"],
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\nScript sauvegardé dans {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
