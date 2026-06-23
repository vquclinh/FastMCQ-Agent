# FASTMCQ final submission image (Phase 2L.31A).
# DEFAULT behavior is OFFLINE, reproducible frozen_csv export of the current best
# independent-v11 submission (public 78.4) — NO API key required, NO v10, NO inference.
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code + the frozen final assets. .dockerignore keeps secrets,
# scratch, caches, .git, notebooks and large logs OUT of the image.
COPY . .

# The competition harness mounts the dataset into /data and reads /output. The no-arg
# default runs scripts/final_infer.py in frozen_csv mode (current best independent v11):
# final_infer.py auto-detects the input from /data and writes /output/pred.csv, prints a
# timing block, and validates it. No OPENROUTER_API_KEY is baked in or required by default.
# ENTRYPOINT (not CMD) so that any args passed to `docker run` are forwarded to
# final_infer.py (e.g. `docker run ... fastmcq-final --mode v10`); override with
# `--entrypoint bash` to run an arbitrary command. The experimental v11_independent rerun
# mode needs a key + budget and is strictly opt-in (the image never runs v10 by default).
RUN chmod +x scripts/docker_entrypoint_v11.sh
ENTRYPOINT ["bash", "scripts/docker_entrypoint_v11.sh"]
