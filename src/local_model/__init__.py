"""Local open-weight model backend for offline MCQ inference (Phase 2L.47B).

Single open-weight model (<=5B), loaded once via Hugging Face Transformers; deterministic,
answer-only generation; no internet / no external API at runtime.
"""
