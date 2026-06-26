"""
Utilitaire (à lancer une seule fois, en local) : filtre un fichier cookies.txt
exporté par l'extension navigateur pour ne garder que les lignes concernant
youtube.com et google.com -- réduit fortement la taille pour respecter la
limite de 64 Ko des secrets GitHub.

Usage :
    py filter_cookies.py cookies.txt cookies_filtered.txt
"""

import sys
from pathlib import Path

KEEP_DOMAINS = ("youtube.com", "google.com")


def main():
    if len(sys.argv) != 3:
        print("Usage : py filter_cookies.py <fichier_entree> <fichier_sortie>")
        sys.exit(1)

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    if not input_path.exists():
        print(f"Erreur : {input_path} introuvable.")
        sys.exit(1)

    lines = input_path.read_text(encoding="utf-8").splitlines()
    kept = []

    for line in lines:
        stripped = line.strip()
        # Garde les lignes d'en-tête (commentaires standard du format Netscape)
        if stripped.startswith("# Netscape") or stripped.startswith("# HTTP Cookie File") or not stripped:
            kept.append(line)
            continue
        # Garde uniquement les lignes liées aux domaines voulus
        if any(domain in stripped for domain in KEEP_DOMAINS):
            kept.append(line)

    output_path.write_text("\n".join(kept) + "\n", encoding="utf-8")

    size_kb = output_path.stat().st_size / 1024
    print(f"{len(kept)} lignes gardées sur {len(lines)} -> {output_path}")
    print(f"Taille finale : {size_kb:.1f} Ko")
    if size_kb > 60:
        print("Attention : toujours proche de la limite de 64 Ko de GitHub Secrets.")

    # Encodage base64 : évite toute corruption (tabulations -> espaces) lors du
    # copier-coller dans la zone de texte de GitHub Secrets.
    import base64
    b64_path = output_path.with_suffix(".b64.txt")
    b64_content = base64.b64encode(output_path.read_bytes()).decode("ascii")
    b64_path.write_text(b64_content, encoding="utf-8")
    print(f"\nVersion base64 (à coller dans GitHub Secrets) : {b64_path}")
    print(f"Taille base64 : {len(b64_content) / 1024:.1f} Ko")


if __name__ == "__main__":
    main()
