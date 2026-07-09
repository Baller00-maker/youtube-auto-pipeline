"""Orchestrateur pipeline Récitation Coranique (audio + vidéo complète)."""
import subprocess, sys, time

STEPS = [
    ("fetch_quran_audio.py",   "Téléchargement récitation coranique"),
    ("produce_quran_video.py", "Production vidéo (effets pro audio + vidéo cinématique)"),
]

def run_step(script, desc):
    print(f"\n{'='*60}\nETAPE : {desc}\n{'='*60}")
    t = time.time()
    r = subprocess.run([sys.executable, script])
    print(f"--- {time.time()-t:.1f}s (code {r.returncode}) ---")
    return r.returncode == 0

def main():
    print("Pipeline Récitation Coranique -- Production Complète\n")
    for script, desc in STEPS:
        if not run_step(script, desc):
            print(f"\nERREUR : '{desc}' a échoué.", file=sys.stderr)
            sys.exit(1)
    print("\n" + "="*60)
    print("PIPELINE TERMINE.")
    print("Telecharge quran_video.mp4 depuis les Artifacts GitHub.")
    print("Audio : reverb mosquee + EQ warm + broadcast -14 LUFS")
    print("Video : color grade dore + Ken Burns + crossfade + vignette")
    print("="*60)

if __name__ == "__main__":
    main()
