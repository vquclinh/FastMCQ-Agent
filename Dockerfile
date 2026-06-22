# Lightweight Python base for the Phase 1 baseline (stdlib + PyYAML only).
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY . .

# The competition harness mounts the dataset into /data and reads /output.
# The entrypoint auto-detects the input inside /data (private before public, csv
# before json, then any .csv/.json) and runs the generalized production pipeline
# with the stable preset. OPENROUTER_API_KEY is provided by the evaluator's env and
# is NOT baked into the image. If the local neural reranker is unavailable the
# pipeline fails closed to the lexical reranker.
RUN chmod +x scripts/docker_entrypoint.sh
CMD ["bash", "scripts/docker_entrypoint.sh"]
