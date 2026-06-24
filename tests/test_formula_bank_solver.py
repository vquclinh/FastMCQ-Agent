"""Tests for the generalized formula/concept bank (Phase 2L.19).

No network, no real model, no qid logic. Synthetic samples only.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.formula_bank_solver import solve_formula_bank_sample  # noqa: E402


def _r(q, ch):
    return solve_formula_bank_sample({"question": q, "choices": ch})


def _ans(q, ch):
    res = _r(q, ch)
    return res.selected_answer if res else None


# --- positive cases per rule --------------------------------------------------

def test_determinant_2x2():
    assert _ans("Tính định thức của ma trận [[3, 8], [4, 6]].", ["-14", "14", "50", "-50"]) == "A"


def test_ohms_law():
    assert _ans("Mạch có hiệu điện thế 12 V và điện trở 4 Ω. Cường độ dòng điện là bao nhiêu?",
                ["2 A", "3 A", "4 A", "6 A"]) == "B"


def test_electric_power():
    assert _ans("Công suất khi hiệu điện thế 10 V và dòng điện 2 A là bao nhiêu?",
                ["10 W", "20 W", "30 W", "5 W"]) == "B"


def test_wave_speed():
    assert _ans("Một sóng có tần số 50 Hz và bước sóng 2 m. Vận tốc sóng là bao nhiêu?",
                ["25 m/s", "100 m/s", "52 m/s", "200 m/s"]) == "B"


def test_pythagorean_distance():
    assert _ans("Hai thành phần vuông góc 3 và 4. Khoảng cách tổng hợp (cạnh huyền) là bao nhiêu?",
                ["5", "7", "6", "1"]) == "A"


def test_resistor_series_equivalent():
    assert _ans("Hai điện trở 10 Ω và 20 Ω mắc nối tiếp. Điện trở tương đương là bao nhiêu?",
                ["15 Ω", "30 Ω", "6.67 Ω", "200 Ω"]) == "B"


def test_resistor_parallel_equivalent():
    assert _ans("Hai điện trở 10 Ω và 20 Ω mắc song song. Điện trở tương đương là bao nhiêu?",
                ["15 Ω", "30 Ω", "6.67 Ω", "200 Ω"]) == "C"


def test_mc_vs_atc_increase():
    assert _ans("Chi phí trung bình là 25 đô la và chi phí biên là 30 đô la; khi sản lượng "
                "tăng thêm một đơn vị, chi phí trung bình sẽ?",
                ["Giảm", "Tăng", "Không đổi", "Không xác định"]) == "B"


def test_expected_value():
    assert _ans("Một biến nhận giá trị 10 với xác suất 0,3 và 20 với xác suất 0,7. Giá trị "
                "kỳ vọng là bao nhiêu?", ["15", "17", "13", "20"]) == "B"


def test_elasticity_revenue_elastic_price_up():
    assert _ans("Nếu cầu co giãn nhiều và doanh nghiệp tăng giá thì tổng doanh thu sẽ?",
                ["Doanh thu tăng", "Doanh thu giảm", "Doanh thu không đổi", "Không xác định"]) == "B"


def test_matrix_vector_multiply():
    # [[1,2],[3,4]] · (1,1) = (3,7)
    assert _ans("Cho ma trận [[1,2],[3,4]] và vector (1,1). Tích ma trận-vector là?",
                ["(3, 7)", "(7, 3)", "(4, 6)", "(1, 1)"]) == "A"


def test_determinant_negative_and_exact():
    assert _ans("Định thức của ma trận [[2, 0], [0, 2]]?", ["0", "2", "4", "-4"]) == "C"


# --- decline / no-misfire cases ----------------------------------------------

def test_resistor_power_matching_does_not_fire():
    # The test_0194-style power-matching question must NOT be treated as a series sum.
    q = ("Một mạch điện gồm một acquy 24V, một điện trở 6Ω và một điện trở biến đổi mắc nối "
         "tiếp. Điện trở biến đổi được điều chỉnh để tiêu thụ công suất bằng công suất của "
         "điện trở 6Ω. Điện trở biến đổi có giá trị là bao nhiêu?")
    assert _r(q, ["2Ω", "4Ω", "6Ω", "8Ω", "12Ω"]) is None


def test_ohms_declines_without_two_values():
    assert _r("Định luật Ohm phát biểu điều gì?", ["V=IR", "P=VI", "F=ma", "E=mc^2"]) is None


def test_wave_declines_without_two_values():
    assert _r("Sóng âm là gì?", ["Sóng dọc", "Sóng ngang", "Cả hai", "Không"]) is None


def test_expected_value_declines_when_probs_not_sum_one():
    assert _r("Giá trị 10 với xác suất 0,3 và 20 với xác suất 0,3. Giá trị kỳ vọng?",
              ["9", "17", "13", "20"]) is None


def test_non_formula_declines():
    assert _r("Thủ đô của Pháp là gì?", ["Paris", "Lyon", "Nice", "Huế"]) is None


# --- Phase 2L.20 new rule families -------------------------------------------

def test_kinetic_energy():
    assert _ans("Một vật khối lượng 2 kg chuyển động với vận tốc 3 m/s. Động năng là bao nhiêu?",
                ["6 J", "9 J", "18 J", "12 J"]) == "B"


def test_potential_energy():
    assert _ans("Một vật khối lượng 2 kg ở độ cao 5 m (g=10). Thế năng trọng trường là bao nhiêu?",
                ["50 J", "100 J", "20 J", "10 J"]) == "B"


def test_uniform_motion():
    assert _ans("Một xe chuyển động đều với vận tốc 10 m/s trong thời gian 5 s. Quãng đường "
                "đi được là bao nhiêu?", ["15 m", "50 m", "2 m", "100 m"]) == "B"


def test_density():
    assert _ans("Một vật có khối lượng 10 kg và thể tích 2 m³. Khối lượng riêng là bao nhiêu?",
                ["5 kg/m³", "20 kg/m³", "12 kg/m³", "8 kg/m³"]) == "A"


def test_pressure():
    assert _ans("Một lực 20 N tác dụng lên diện tích 4 m². Áp suất là bao nhiêu?",
                ["5 Pa", "80 Pa", "24 Pa", "16 Pa"]) == "A"


def test_triangle_area():
    assert _ans("Tam giác có đáy 6 và chiều cao 4. Diện tích là bao nhiêu?",
                ["12", "24", "10", "20"]) == "A"


def test_profit():
    assert _ans("Doanh thu là 1000 và tổng chi phí là 600. Lợi nhuận là bao nhiêu?",
                ["400", "1600", "600", "1000"]) == "A"


def test_roi():
    assert _ans("Lợi nhuận 200 trên vốn đầu tư 1000. ROI là bao nhiêu?",
                ["10%", "20%", "30%", "50%"]) == "B"


def test_depreciation():
    assert _ans("Một tài sản nguyên giá 10000, giá trị thanh lý 2000, tuổi thọ 4 năm. Khấu "
                "hao hằng năm theo đường thẳng?", ["2000", "2500", "1500", "3000"]) == "A"


def test_moles():
    assert _ans("Có 36 gam nước, khối lượng mol là 18 g/mol. Số mol là bao nhiêu?",
                ["1", "2", "3", "0.5"]) == "B"


def test_concentration():
    assert _ans("Hòa tan 2 mol chất tan trong thể tích 4 lít dung dịch. Nồng độ mol là bao nhiêu?",
                ["0.5 M", "2 M", "8 M", "1 M"]) == "A"


def test_frequency_period():
    assert _ans("Một dao động có chu kỳ 0,5 s. Tần số là bao nhiêu?",
                ["1 Hz", "2 Hz", "0.5 Hz", "4 Hz"]) == "B"


def test_new_rules_decline_without_values():
    assert _r("Động năng là gì?", ["Năng lượng chuyển động", "Năng lượng vị trí", "Khác", "Khác2"]) is None
    assert _r("Lợi nhuận là gì?", ["Doanh thu trừ chi phí", "Doanh thu", "Chi phí", "Khác"]) is None


# --- Phase 2L.21 new rule families -------------------------------------------

def test_capacitor_series():
    assert _ans("Hai tụ điện 6 µF và 3 µF mắc nối tiếp. Điện dung tương đương là bao nhiêu?",
                ["2 µF", "9 µF", "18 µF", "4 µF"]) == "A"


def test_capacitor_parallel():
    assert _ans("Hai tụ điện 6 µF và 3 µF mắc song song. Điện dung tương đương là bao nhiêu?",
                ["2 µF", "9 µF", "18 µF", "4 µF"]) == "B"


def test_capacitor_declines_without_equivalent():
    assert _r("Tụ điện 6 µF tích điện ở 12 V. Điện tích là bao nhiêu?",
              ["72 µC", "2 µF", "18", "0.5"]) is None


def test_mean_median_mode():
    assert _ans("Cho dãy số: 2, 4, 6, 8. Số trung bình cộng là bao nhiêu?", ["4", "5", "6", "8"]) == "B"
    assert _ans("Cho tập dữ liệu: 1, 3, 5, 7, 9. Trung vị là bao nhiêu?", ["3", "5", "7", "9"]) == "B"
    assert _ans("Cho dãy số: 2, 2, 3, 4. Mốt (mode) là bao nhiêu?", ["2", "3", "4", "2.75"]) == "A"


def test_mean_declines_without_data():
    assert _r("Số trung bình của lớp là cao. Đúng hay sai?", ["Đúng", "Sai"]) is None


def test_break_even():
    assert _ans("Định phí là 1000, giá bán 20, chi phí biến đổi trên mỗi đơn vị là 15. Sản "
                "lượng hòa vốn là bao nhiêu?", ["100", "200", "50", "1000"]) == "B"


def test_binary_decimal_both_directions():
    assert _ans("Chuyển số thập phân 10 sang nhị phân.", ["1010", "1100", "1001", "1000"]) == "A"
    assert _ans("Chuyển số nhị phân 1011 sang thập phân.", ["9", "11", "13", "7"]) == "B"


def test_cache_amat():
    assert _ans("Cache có thời gian trúng (hit time) 2 ns, tỉ lệ trượt (miss rate) 10%, hình "
                "phạt trượt (miss penalty) 100 ns. Thời gian truy cập trung bình là bao nhiêu?",
                ["10 ns", "12 ns", "102 ns", "20 ns"]) == "B"


# --- Phase 2L.26B: Cournot duopoly --------------------------------------------

_COURNOT_OPTS = ["q_X = 3, q_Y = 3", "q_X = 4, q_Y = 4", "q_X = 5, q_Y = 5",
                 "q_X = 6, q_Y = 6", "q_X = 7, q_Y = 7"]


def test_cournot_duopoly_positive():
    q = ("Xét thị trường độc quyền hai hãng X và Y cạnh tranh về lượng (Cournot). Hàm chi "
         "phí mỗi hãng C(q) = 2q. Hàm cầu thị trường P = 20 - Q. Lượng cân bằng?")
    assert _ans(q, _COURNOT_OPTS) == "D"          # (20-2)/3 = 6 -> q_X=q_Y=6


def test_cournot_declines_three_firms():
    q = ("Thị trường Cournot ba hãng cạnh tranh về lượng, C(q)=2q, P=20-Q. Lượng mỗi hãng?")
    assert _r(q, _COURNOT_OPTS) is None


def test_cournot_declines_nonlinear_demand():
    q = ("Hai hãng cạnh tranh Cournot, C(q)=2q, cầu P = 20 - Q^2. Lượng cân bằng mỗi hãng?")
    assert _r(q, _COURNOT_OPTS) is None


def test_cournot_declines_no_matching_option():
    q = ("Hai hãng cạnh tranh Cournot (cạnh tranh về lượng), C(q)=2q, P=20-Q. Lượng mỗi hãng?")
    # q_i=6 but no option has 6
    assert _r(q, ["q_X=3,q_Y=3", "q_X=4,q_Y=4", "q_X=5,q_Y=5"]) is None


def test_cournot_declines_asymmetric_costs():
    q = ("Hai hãng Cournot: chi phí hãng X là C_X(q)=2q, chi phí hãng Y là C_Y(q)=4q, "
         "P=20-Q. Lượng cân bằng?")
    assert _r(q, _COURNOT_OPTS) is None


# --- source safety ------------------------------------------------------------

def test_no_qid_or_external_sheet_in_source():
    import re as _re
    for rel in ("src/formula_bank_solver.py", "scripts/apply_formula_bank_to_predictions.py"):
        src = (_ROOT / rel).read_text()
        # Detect qid-VALUE hardcoding / answer tables (not legitimate "qid" column refs).
        for pat in (r'qid\s*==', r'==\s*qid', r'==\s*["\']test_0', r'test_0\d{3}'):
            assert not _re.search(pat, src), f"qid/answer-table pattern {pat} in {rel}"
        assert "first100_external" not in src and "OpenRouterClient" not in src
        assert ".env" not in src and "OPENROUTER_API_KEY" not in src
        for bad in ("import requests", "import urllib", "eval(", "exec("):
            assert bad not in src, f"{bad} in {rel}"


# --- apply script guards ------------------------------------------------------

def _load_apply():
    path = _ROOT / "scripts" / "apply_formula_bank_to_predictions.py"
    spec = importlib.util.spec_from_file_location("apply_fb", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_apply_refuses_protected_output():
    mod = _load_apply()
    try:
        mod.main(["--input", "x", "--base-pred", "y", "--output", "output/pred.csv",
                  "--log-path", "output/z.jsonl", "--diff", "output/d.csv"])
        assert False, "should refuse protected output"
    except SystemExit as e:
        assert "REFUSING" in str(e) or e.code != 0


def test_apply_stops_when_changes_exceed_max():
    inp = _ROOT / "public-test_1780368312.json"
    base = _ROOT / "output" / "pred_v8_clean_generalized_from_v7.csv"
    if not (inp.exists() and base.exists()):
        return
    mod = _load_apply()
    d = Path(tempfile.mkdtemp())
    out = d / "v9.csv"
    rc = mod.main(["--input", str(inp), "--base-pred", str(base),
                   "--output", str(out), "--log-path", str(d / "v9.jsonl"),
                   "--diff", str(d / "v9diff.csv"), "--max-expected-changes", "0"])
    assert rc == 2 and not out.exists()      # stopped; no prediction written


# --- Phase 2L.24C: apply-script timing report -------------------------------

def test_apply_script_prints_timing_and_writes_summary_event():
    import importlib.util as _ilu
    import json as _json
    import tempfile as _tmp
    import io as _io
    from contextlib import redirect_stdout

    root = Path(__file__).resolve().parent.parent
    spec = _ilu.spec_from_file_location(
        "apply_fb_timing", root / "scripts" / "apply_formula_bank_to_predictions.py")
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # Tiny synthetic input + base prediction (no API, no public answers).
    d = Path(_tmp.mkdtemp())
    inp = d / "in.json"
    inp.write_text(_json.dumps([
        {"qid": "z1", "question": "Thủ đô của Pháp là gì?", "choices": ["Paris", "Lyon", "Nice"]},
        {"qid": "z2", "question": "Một câu hỏi thường.", "choices": ["A", "B"]},
    ], ensure_ascii=False))
    base = d / "base.csv"
    base.write_text("qid,answer\nz1,A\nz2,A\n")
    out, log, diff = d / "v.csv", d / "v.jsonl", d / "d.csv"

    buf = _io.StringIO()
    with redirect_stdout(buf):
        rc = mod.main(["--input", str(inp), "--base-pred", str(base), "--output", str(out),
                       "--log-path", str(log), "--diff", str(diff)])
    text = buf.getvalue()
    assert rc == 0
    for field in ("elapsed_seconds", "samples_per_second", "avg_seconds_per_sample"):
        assert field in text, f"missing timing field in printed summary: {field}"
    # JSONL summary event present with timing fields.
    last = _json.loads(log.read_text().splitlines()[-1])
    assert last.get("event") == "summary"
    for key in ("elapsed_seconds", "samples", "answers_changed", "samples_per_second",
                "avg_seconds_per_sample"):
        assert key in last, f"missing {key} in JSONL summary event"
    # Prediction content unchanged: no rule fires on these -> answers stay == base.
    rows = [r.split(",") for r in out.read_text().splitlines()[1:] if r]
    assert {r[0]: r[1] for r in rows} == {"z1": "A", "z2": "A"}


if __name__ == "__main__":
    failures = 0
    for nm, fn in sorted(globals().items()):
        if nm.startswith("test_") and callable(fn):
            try:
                fn(); print(f"PASS {nm}")
            except AssertionError as exc:
                failures += 1; print(f"FAIL {nm}: {exc}")
    raise SystemExit(1 if failures else 0)
