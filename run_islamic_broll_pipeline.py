"""Orchestrateur pipeline B-roll Islamique Silencieux (sans son, pour récital de Coran)."""
import subprocess
import sys
import time

STEPS = [
    ("produce_islamic_broll_video.py", "Production vidéo B-roll islamique silencieuse"),
]


def run_step(script, desc):
    print(f"\n{'='*60}\nETAPE : {desc}\n{'='*60}")
    t = time.time()
    r = subprocess.run([sys.executable, script])
    print(f"--- {time.time()-t:.1f}s (code {r.returncode}) ---")
    return r.returncode == 0


def main():
    print("Pipeline B-roll Islamique Silencieux -- Production\n")
    for script, desc in STEPS:
        if not run_step(script, desc):
            print(f"\nERREUR : '{desc}' a échoué.", file=sys.stderr)
            sys.exit(1)
    print("\n" + "="*60)
    print("PIPELINE TERMINE.")
    print("Telecharge islamic_broll_video.mp4 depuis les Artifacts GitHub.")
    print("Vidéo verticale 1080x1920, SANS SON, prête à être associée à un")
    print("récital de Coran au montage (audio ajouté séparément).")
    print("="*60)


if __name__ == "__main__":
    main()
