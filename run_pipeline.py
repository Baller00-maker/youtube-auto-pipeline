"""
Orchestrateur du pipeline complet.
Exécute dans l'ordre les étapes automatisables, en s'arrêtant immédiatement si une étape
échoue (pour ne pas uploader une vidéo construite sur des données incomplètes).

IMPORTANT : l'étape de collecte (collect.py) n'est PAS incluse ici. YouTube bloque trop
souvent les IP de datacenter (GitHub Actions) pour scraper les vidéos de façon fiable.
À la place :
  - L'utilisateur lance collect.py manuellement EN LOCAL (sur son PC) environ 1x/semaine
  - Le fichier reference.json généré est commité sur le repo
  - Ce pipeline automatisé réutilise ce reference.json existant pour produire une
    nouvelle vidéo à chaque exécution (le sujet change, le style de référence reste figé
    jusqu'au prochain rafraîchissement manuel).

Étapes automatisées :
1. generate_script.py  -> analyse de style + script original
2. produce_audio.py    -> narration audio (voix)
3. transcribe.py       -> sous-titres + timing précis (Whisper)
4. fetch_visuals.py    -> images/clips vidéo par segment
5. assemble_video.py   -> montage final (audio + visuels + sous-titres incrustés)
6. upload_video.py     -> upload YouTube en "non répertorié" (validation manuelle requise)
"""

import sys
from pathlib import Path
import subprocess
import time

REFERENCE_FILE = Path("reference.json")

STEPS = [
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
    print("Démarrage du pipeline automatisé de production vidéo.\n")

    if not REFERENCE_FILE.exists():
        print(
            "ERREUR : reference.json introuvable. Lance d'abord 'py collect.py' en local "
            "sur ton PC, puis commit le fichier reference.json sur le repo avant de relancer "
            "ce pipeline automatisé.",
            file=sys.stderr,
        )
        sys.exit(1)

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
