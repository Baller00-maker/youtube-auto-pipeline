"""
Orchestrateur du pipeline Quiz TikTok.
"""
import subprocess
import sys
import time

STEPS = [
    ("generate_quiz.py", "Génération des 10 questions"),
    ("render_quiz_video.py", "Rendu vidéo complet (frames + audio + montage)"),
]


def run_step(script, description):
    print(f"\n{'='*60}")
    print(f"ÉTAPE : {description}")
    print("="*60)
    start = time.time()
    result = subprocess.run([sys.executable, script])
    elapsed = time.time() - start
    print(f"--- Terminé en {elapsed:.1f}s (code : {result.returncode}) ---")
    return result.returncode == 0


def main():
    print("Démarrage du pipeline Quiz TikTok.\n")
    for script, description in STEPS:
        if not run_step(script, description):
            print(f"\nERREUR : '{description}' a échoué.", file=sys.stderr)
            sys.exit(1)
    print("\n" + "="*60)
    print("PIPELINE QUIZ TERMINÉ.")
    print("Télécharge quiz_final.mp4 depuis les Artifacts GitHub.")
    print("="*60)


if __name__ == "__main__":
    main()
