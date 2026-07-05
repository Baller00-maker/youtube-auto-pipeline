"""
Pipeline Quiz TikTok -- Étape 1 : génération des questions
- Génère 10 questions de culture générale en français via NVIDIA LLM
- 4 choix par question (A/B/C/D), une seule bonne réponse
- Variété garantie : 10 catégories différentes dans chaque vidéo
- Sauvegarde quiz_data.json
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL_NAME = "meta/llama-3.1-70b-instruct"
OUTPUT_FILE = Path("quiz_data.json")

CATEGORIES = [
    "géographie mondiale",
    "histoire de France",
    "sciences et nature",
    "animaux et faune",
    "sport et champions",
    "cinéma et séries",
    "musique et artistes",
    "gastronomie et cuisine",
    "technologies et inventions",
    "culture générale insolite",
]


def call_llm(client, prompt, max_tokens=3000, max_retries=3):
    for attempt in range(1, max_retries + 1):
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=max_tokens,
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text
        print(f"  ! Tentative {attempt}/{max_retries} : réponse vide.", file=sys.stderr)
        time.sleep(3)
    raise RuntimeError("API sans réponse après plusieurs tentatives.")


def generate_questions(client):
    categories_list = "\n".join(f"{i+1}. {cat}" for i, cat in enumerate(CATEGORIES))
    prompt = f"""Tu es un créateur de quiz TikTok viral en français. Génère exactement 10 questions
de culture générale, UNE par catégorie dans cet ordre :
{categories_list}

Règles :
- Questions courtes et percutantes (max 12 mots)
- 4 choix de réponse (A, B, C, D), UN SEUL correct
- Niveau : accessible mais pas trop facile (surprenant, mémorable)
- Les mauvaises réponses doivent être plausibles
- Inclus un fait insolite/surprenant dans l'explication

Retourne UNIQUEMENT un JSON valide, aucun markdown, aucune explication :
{{
  "title": "titre accrocheur pour la vidéo TikTok (max 8 mots)",
  "questions": [
    {{
      "category": "nom de la catégorie",
      "question": "texte de la question",
      "choices": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
      "correct": "A",
      "explanation": "explication courte et fun (max 15 mots)"
    }}
  ]
}}"""

    for attempt in range(1, 4):
        text = call_llm(client, prompt)
        cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip()).strip()
        if not cleaned:
            print(f"  ! Tentative {attempt}/3 : réponse vide.", file=sys.stderr)
            time.sleep(3)
            continue
        try:
            data = json.loads(cleaned)
            assert len(data["questions"]) == 10
            return data
        except (json.JSONDecodeError, KeyError, AssertionError) as e:
            print(f"  ! Tentative {attempt}/3 : JSON invalide ({e}).", file=sys.stderr)
            time.sleep(3)
    raise RuntimeError("Impossible de générer un quiz valide après 3 tentatives.")


def main():
    if not NVIDIA_API_KEY:
        print("Erreur : NVIDIA_API_KEY non définie.", file=sys.stderr)
        sys.exit(1)

    client = OpenAI(base_url=NVIDIA_BASE_URL, api_key=NVIDIA_API_KEY)

    print("Génération de 10 questions de quiz...")
    data = generate_questions(client)
    print(f"Titre : {data['title']}")
    for i, q in enumerate(data["questions"]):
        print(f"  Q{i+1} [{q['category']}] : {q['question']}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\nQuiz sauvegardé : {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
