FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scraper.py uploader.py main.py ask.py ./

# Mount a persistent volume at /app/articles (holds manifest.json + vector-store
# config) so re-runs can detect deltas instead of re-uploading everything.
CMD ["python", "main.py"]
