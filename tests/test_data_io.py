"""Tests for loading data, the baseline solver, and submission validity.

Runnable with pytest, or standalone: ``python tests/test_data_io.py``.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.baseline_solver import AlwaysASolver  # noqa: E402
from src.data_io import load_dataset, read_predictions, write_predictions  # noqa: E402
from src.postprocess import build_predictions  # noqa: E402

PUBLIC_TEST = ROOT / "public-test_1780368312.json"


def test_load_public_test_json():
    if not PUBLIC_TEST.exists():
        print(f"SKIP test_load_public_test_json: {PUBLIC_TEST.name} not found")
        return
    samples = load_dataset(PUBLIC_TEST)
    assert len(samples) > 0
    first = samples[0]
    assert set(first) >= {"qid", "question", "choices"}
    assert isinstance(first["choices"], list)
    assert all(s["qid"] for s in samples)


def test_load_csv_separate_columns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.csv"
        path.write_text(
            "qid,question,A,B,C,D\n"
            "q1,What?,alpha,beta,gamma,delta\n",
            encoding="utf-8",
        )
        samples = load_dataset(path)
    assert samples[0]["choices"] == ["alpha", "beta", "gamma", "delta"]


def test_load_csv_option_columns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.csv"
        path.write_text(
            "qid,question,option_a,option_b,option_c\n"
            "q1,Pick,one,two,three\n",
            encoding="utf-8",
        )
        samples = load_dataset(path)
    assert samples[0]["choices"] == ["one", "two", "three"]


def test_load_csv_single_choices_column():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.csv"
        path.write_text(
            'qid,question,choices\n'
            'q1,Pick,"[""x"", ""y"", ""z""]"\n',
            encoding="utf-8",
        )
        samples = load_dataset(path)
    assert samples[0]["choices"] == ["x", "y", "z"]


def test_baseline_predicts_all_A():
    samples = [{"qid": "q1", "question": "?", "choices": ["a", "b", "c"]}]
    solver = AlwaysASolver()
    assert solver.predict_batch(samples) == ["A"]


def test_write_and_validate_baseline_submission():
    if not PUBLIC_TEST.exists():
        print(f"SKIP test_write_and_validate_baseline_submission: {PUBLIC_TEST.name} not found")
        return
    samples = load_dataset(PUBLIC_TEST)
    labels = AlwaysASolver().predict_batch(samples)
    predictions = build_predictions(samples, labels)

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "pred.csv"
        write_predictions(predictions, out)
        rows = read_predictions(out)

    assert len(rows) == len(samples)
    assert {r["qid"] for r in rows} == {s["qid"] for s in samples}
    assert all(r["answer"] == "A" for r in rows)


def test_postprocess_fallback_for_invalid_label():
    samples = [{"qid": "q1", "question": "?", "choices": ["a", "b"]}]
    # "Z" is out of range for a 2-choice question -> falls back to "A".
    predictions = build_predictions(samples, ["Z"])
    assert predictions == [{"qid": "q1", "answer": "A"}]


def test_postprocess_dedupes_qids():
    samples = [
        {"qid": "q1", "question": "?", "choices": ["a", "b"]},
        {"qid": "q1", "question": "?", "choices": ["a", "b"]},
    ]
    predictions = build_predictions(samples, ["A", "B"])
    assert len(predictions) == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
