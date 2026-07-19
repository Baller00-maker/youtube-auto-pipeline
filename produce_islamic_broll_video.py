name: Islamic B-roll Video (Silent)
on:
  schedule:
    - cron: "0 6 * * *"   # tous les jours à 6h UTC -- adapte l'horaire si besoin
  workflow_dispatch: {}
permissions:
  contents: write   # nécessaire pour commiter islamic_broll_history.json (anti-répétition)
jobs:
  produce-islamic-broll:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - name: Recuperation du depot
        uses: actions/checkout@v4

      - name: Installation Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Installation ffmpeg
        timeout-minutes: 6
        run: |
          if ! command -v ffmpeg >/dev/null 2>&1; then
            sudo apt-get update -qq
            sudo apt-get install -y --no-install-recommends ffmpeg
          else
            echo "ffmpeg deja present : $(ffmpeg -version | head -1)"
          fi

      - name: Installation dependances Python
        run: pip install -r requirements.txt

      - name: Execution pipeline B-roll islamique silencieux
        env:
          PEXELS_API_KEY: ${{ secrets.PEXELS_API_KEY }}
          PIXABAY_API_KEY: ${{ secrets.PIXABAY_API_KEY }}
          MIN_DURATION_SECONDS: "60"
          MAX_DURATION_SECONDS: "90"
        run: python run_islamic_broll_pipeline.py

      - name: Sauvegarde video finale
        uses: actions/upload-artifact@v4
        with:
          name: islamic-broll-video-${{ github.run_number }}
          path: islamic_broll_video.mp4
          retention-days: 7

      - name: Commit de l'historique (anti-repetition des rush)
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add islamic_broll_history.json
          git diff --staged --quiet || git commit -m "Mise a jour historique B-roll islamique [skip ci]"
          git push
