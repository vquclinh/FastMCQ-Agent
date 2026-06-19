# Lightweight Python base for the Phase 1 baseline (stdlib + PyYAML only).
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code.
COPY . .

# The competition harness mounts the dataset into /data and reads /output.
# We do NOT hard-code the input filename: run.py auto-detects the input inside
# /data (public-test.json, private-test.json, public_test.csv, private_test.csv,
# or any other .csv/.json), so the same image works whichever file BTC mounts.
CMD ["python", "run.py", "--output", "/output/pred.csv"]
