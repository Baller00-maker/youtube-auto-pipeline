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
import time
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


def call_llm(client, prompt, max_tokens=4096, max_retries=3):
    """Appel générique au modèle via l'endpoint compatible OpenAI de NVIDIA NIM.
    Réessaie automatiquement si la réponse est vide (aléa occasionnel observé sur
    l'API gratuite, pas systématique)."""
    last_error = None
    for attempt in range(1, max_retries + 1):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
        last_error = "réponse vide"
        print(f"  ! Tentative {attempt}/{max_retries} : {last_error}, nouvel essai...", file=sys.stderr)
        time.sleep(3)

    raise RuntimeError(f"L'API n'a renvoyé aucune réponse utilisable après {max_retries} tentatives ({last_error}).")


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

    for attempt in range(1, 4):
        text = call_llm(client, prompt, max_tokens=1024)
        cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip()).strip()
        if not cleaned:
            print(f"  ! Tentative {attempt}/3 : réponse non-vide mais vide après nettoyage Markdown.", file=sys.stderr)
            print(f"    Texte brut reçu : {text[:300]!r}", file=sys.stderr)
            time.sleep(3)
            continue
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"  ! Tentative {attempt}/3 : JSON invalide ({e}).", file=sys.stderr)
            print(f"    Texte reçu : {cleaned[:300]!r}", file=sys.stderr)
            time.sleep(3)

    raise RuntimeError("Impossible d'obtenir un profil de style JSON valide après 3 tentatives.")


def generate_script(client, style_profile, topic, target_words):
    """Appel LLM n°2 (multi-étapes) : génération du script ORIGINAL section par section.
    Ne reçoit QUE le profil de style abstrait + le sujet -- jamais le texte source.

    Génère un bloc par étape de narrative_structure plutôt qu'en un seul gros bloc :
    les LLM ont tendance à s'arrêter "naturellement" bien avant la longueur demandée
    sur une génération unique, mais respectent mieux une cible courte par section."""
    beats = style_profile.get("narrative_structure") or ["introduction", "development", "climax", "conclusion"]
    words_per_beat = max(150, target_words // len(beats))

    sections = []
    previous_text = ""

    for i, beat in enumerate(beats):
        prompt = f"""You are a professional scriptwriter for a military history YouTube channel.

You are writing ONE SECTION of a longer video script about: "{topic}"

This section corresponds to the narrative beat: "{beat}" (section {i + 1} of {len(beats)}).

STYLE PROFILE to follow (structure and tone only -- content must be original and accurate):
{json.dumps(style_profile, indent=2)}

{"Here is what has been narrated so far, for continuity (do not repeat it, continue naturally from it):" if previous_text else ""}
{previous_text[-1200:] if previous_text else ""}

Requirements for THIS SECTION ONLY:
- Write approximately {words_per_beat} words for this section alone (mandatory, do not undershoot)
- Continuous spoken narration only, NOT a screenplay -- no camera directions, no [brackets], no headers
- Match the tone, sentence_style, and pacing_notes from the style profile
- Be historically accurate -- only dramatize real history
- {"Do NOT add a conclusion or closing line yet, more sections follow." if i < len(beats) - 1 else "This is the FINAL section: end with a natural thematic closing line (no generic 'like and subscribe')."}

Write only the narration text for this section now."""

        print(f"  Génération section {i + 1}/{len(beats)} ({beat}, cible {words_per_beat} mots)...")
        section_text = call_llm(client, prompt, max_tokens=2048)
        print(f"    -> {len(section_text.split())} mots obtenus")
        sections.append(section_text)
        previous_text += " " + section_text

    return "\n\n".join(sections)


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
