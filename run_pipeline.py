"""
Orchestrateur du pipeline complet.
Exécute dans l'ordre les 6 étapes, en s'arrêtant immédiatement si une étape échoue
(pour ne pas uploader une vidéo construite sur des données incomplètes).

Étapes :
1. collect.py          -> collecte de la vidéo de référence (transcription)
2. generate_script.py  -> analyse de style + script original
3. produce_audio.py    -> narration audio (voix)
4. transcribe.py       -> sous-titres + timing précis (Whisper)
5. fetch_visuals.py    -> images/clips vidéo par segment
6. assemble_video.py   -> montage final (audio + visuels + sous-titres incrustés)
7. upload_video.py     -> upload YouTube en "non répertorié" (validation manuelle requise)
"""

import subprocess
import sys
import time

STEPS = [
    ("collect.py", "Collecte de la vidéo de référence"),
    ("generate_script.py", "Analyse de style + génération du script"),
    ("produce_audio.py", "Génération de la narration audio"),
    ("transcribe.py", "Sous-titres + timing (Whisper)"),
    ("fetch_visuals.py", "Récupération des visuels"),
    ("assemble_video.py", "Montage final de la vidéo"),
    ("upload_video.py", "Upload YouTube (non répertorié)"),
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
    print("Démarrage du pipeline complet de production vidéo.\n")

    for script_name, description in STEPS:
        success = run_step(script_name, description)
        if not success:
            print(f"\nERREUR : l'étape '{description}' a échoué. Arrêt du pipeline.", file=sys.stderr)
            sys.exit(1)

    print("\n" + "=" * 60)
    print("PIPELINE TERMINÉ AVEC SUCCÈS.")
    print("La vidéo est uploadée en 'non répertorié' -- une validation manuelle")
    print("sur YouTube Studio est nécessaire avant de la passer en 'Public'.")
    print("=" * 60)


if __name__ == "__main__":
    main()
