"""
Orchestrateur du pipeline "Histoires dramatiques" (TikTok/YouTube Shorts).
Entièrement autonome, pas d'étape de collecte YouTube requise.
"""

import subprocess
import sys
import time

STEPS = [
    ("generate_story.py", "Génération du script + scènes"),
    ("produce_story_audio.py", "Narration audio (français)"),
    ("fetch_story_visuals.py", "Visuels Pexels (portrait/vertical)"),
    ("transcribe_story.py", "Sous-titres anglais + timing (Whisper)"),
    ("assemble_story_video.py", "Montage final vertical 1080x1920"),
]


def run_step(script_name, description):
    print(f"\n{'=' * 60}")
    print(f"ÉTAPE : {description} ({script_name})")
    print("=" * 60)
    start = time.time()
    result = subprocess.run([sys.executable, script_name])
    elapsed = time.time() - start
    print(f"--- Terminé en {elapsed:.1f}s (code retour : {result.returncode}) ---")
    return result.returncode == 0


def main():
    print("Démarrage du pipeline 'Histoires dramatiques'.\n")
    for script_name, description in STEPS:
        if not run_step(script_name, description):
            print(f"\nERREUR : '{description}' a échoué. Arrêt.", file=sys.stderr)
            sys.exit(1)

    print("\n" + "=" * 60)
    print("PIPELINE TERMINÉ.")
    print("Télécharge story_final.mp4 depuis les Artifacts GitHub.")
    print("Poste-la sur YouTube Shorts, TikTok, Instagram Reels...")
    print("=" * 60)


if __name__ == "__main__":
    main()
