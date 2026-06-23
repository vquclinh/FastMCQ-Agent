"""API candidate agents — prompt builders + parsers only (Phase 2L.26A; no API here).

Each agent builds strict-JSON chat messages and parses the model's reply into a
normalized dict. No network is contacted in this module; the selective runner injects
a client. No qid logic, no answer table, no ground truth. Strict JSON is enforced and
the answer must be one of the sample's labels (else parse_status reflects the failure).
"""

from __future__ import annotations

import json
import re

from src.labels import labels_for

_LABEL_RE = re.compile(r"[A-K]")
AGENTS = ("route_specialist", "challenger", "option_elimination", "tool_hint",
          "calculation_solver", "pairwise_judge")


def _opts(choices, labels):
    return "\n".join(f"{labels[i]}. {c}" for i, c in enumerate(choices))


def _norm_label(val, labels):
    if val is None:
        return None
    m = _LABEL_RE.search(str(val).strip().upper())
    return m.group(0) if (m and m.group(0) in labels) else None


def _parse_json(content):
    """Best-effort strict-JSON object parse (handles fenced/embedded)."""
    if not content:
        return None
    txt = content.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?|\n?```$", "", txt).strip()
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


# --- prompt builders ----------------------------------------------------------

_ROUTE_SYS = {
    "calculation": "Bạn giải câu hỏi TÍNH TOÁN: trích giá trị, nêu công thức, tính, ánh xạ phương án.",
    "long_context": "Bạn trả lời DỰA TRÊN NGỮ CẢNH được cung cấp; không suy đoán ngoài ngữ cảnh.",
    "short_knowledge": "Bạn so sánh TẤT CẢ phương án và loại trừ phương án sai; tránh tự tin thái quá.",
    "law_admin": "Bạn trả lời câu hỏi pháp luật/hành chính; CHỌN một phương án, KHÔNG từ chối vì an toàn trừ khi một phương án là 'từ chối'; không bịa nguồn luật.",
    "ambiguous": "Bạn suy luận từ nguyên lý cơ bản; KHÔNG dùng ngôn ngữ đa số/bỏ phiếu.",
    "default": "Bạn trả lời câu hỏi trắc nghiệm; so sánh các phương án.",
}
# Quality contract: forbid placeholder evidence; require a real evidence span/proof,
# the chosen option (quoted/summarized), and why other likely options are weaker.
_QUALITY = ('YÊU CẦU BẰNG CHỨNG: "evidence" phải là trích dẫn/đoạn dẫn hoặc phép tính cụ '
            'thể — KHÔNG được để trống hay dùng cụm rỗng như "some evidence", "r", "because". '
            'Nêu (tóm tắt) nội dung phương án đã chọn và vì sao các phương án khác yếu hơn. '
            'Nếu KHÔNG có bằng chứng, đặt "risk":"high" và GIỮ đáp án hiện tại trừ khi biện minh được.')
_JSON5 = ('Trả về DUY NHẤT JSON: {"answer":"<NHÃN>","confidence":<0..1>,'
          '"rationale":"<ngắn>","evidence":"<trích dẫn/phép tính cụ thể>",'
          '"risk":"low|medium|high"}. ' + _QUALITY)


_ROUTE_EVIDENCE_REQ = {
    "calculation": " Bắt buộc: nêu kết quả số cuối cùng và phương án đã chọn phải chứa giá trị đó.",
    "long_context": " Bắt buộc: 'evidence' phải là trích dẫn/đoạn dẫn ngắn từ ngữ cảnh được cung cấp.",
    "short_knowledge": " Nếu có thẻ kiến thức/bằng chứng thì dùng; nếu không, đặt risk='high'.",
}


def build_route_specialist(sample, route, evidence=None):
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    sys = _ROUTE_SYS.get(route, _ROUTE_SYS["default"]) + " " + _JSON5 + _ROUTE_EVIDENCE_REQ.get(route, "")
    parts = []
    if route == "long_context" and evidence:
        parts.append("[NGỮ CẢNH]\n" + str(evidence))
    parts += [f"[CÂU HỎI]\n{sample.get('question','')}", f"[PHƯƠNG ÁN]\n{_opts(choices, labels)}",
              f"Chọn đúng một nhãn trong [{', '.join(labels)}]."]
    return [{"role": "system", "content": sys}, {"role": "user", "content": "\n\n".join(parts)}]


def build_challenger(sample, v10_answer):
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    sys = ("Bạn là người phản biện. Hãy cố CHỨNG MINH đáp án hiện tại SAI bằng lập luận/"
           "bằng chứng. Nếu KHÔNG chứng minh được nó sai, hãy GIỮ NGUYÊN đáp án hiện tại. "
           + _JSON5)
    user = (f"[CÂU HỎI]\n{sample.get('question','')}\n\n[PHƯƠNG ÁN]\n{_opts(choices, labels)}\n\n"
            f"Đáp án hiện tại: {v10_answer}\nNếu không bác bỏ được, trả về đúng {v10_answer}.")
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def build_option_elimination(sample):
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    sys = ("Bạn loại trừ phương án. So sánh TỪNG phương án, nêu rõ phương án nào bị loại "
           "và vì sao. Trả về DUY NHẤT JSON: "
           '{"eliminated":["<NHÃN>",...],"answer":"<NHÃN>","confidence":<0..1>,'
           '"rationale":"<ngắn>","risk":"low|medium|high"}.')
    user = (f"[CÂU HỎI]\n{sample.get('question','')}\n\n[PHƯƠNG ÁN]\n{_opts(choices, labels)}\n\n"
            f"Loại trừ rồi chọn một nhãn trong [{', '.join(labels)}].")
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def build_tool_hint(sample, hints=None, tool_candidates=None):
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    sys = ("Bạn có thể tham khảo các GỢI Ý công thức/thẻ kiến thức và ứng viên từ công cụ, "
           "nhưng KHÔNG được bịa công thức không có căn cứ. " + _JSON5)
    parts = [f"[CÂU HỎI]\n{sample.get('question','')}", f"[PHƯƠNG ÁN]\n{_opts(choices, labels)}"]
    if hints:
        parts.append("[GỢI Ý CÔNG THỨC]\n" + "\n".join(f"- {h}" for h in hints))
    if tool_candidates:
        parts.append("[ỨNG VIÊN CÔNG CỤ]\n" + "\n".join(
            f"- {c.get('source')}: {c.get('answer')} ({c.get('proof_text','')})" for c in tool_candidates))
    parts.append(f"Chọn đúng một nhãn trong [{', '.join(labels)}].")
    return [{"role": "system", "content": sys}, {"role": "user", "content": "\n\n".join(parts)}]


_CALC_SYS = (
    "Bạn là máy giải TÍNH TOÁN. Trả về DUY NHẤT JSON, KHÔNG giải thích dài. "
    'Định dạng: {"final_answer":"<NHÃN>","final_numeric_value":<số hoặc null>,'
    '"chosen_option_text":"<nội dung phương án đã chọn>","calculation_steps":'
    '["b1","b2"],"evidence":"<phép tính ngắn>","confidence":<0..1>,'
    '"risk":"low|medium|high"}. QUY TẮC: tối đa 4 bước ngắn; '
    "phương án đã chọn PHẢI chứa final_numeric_value; chosen_option_text phải khớp nhãn; "
    "CẤM bằng chứng rỗng/đặt chỗ; nếu ánh xạ số→phương án KHÔNG duy nhất thì đặt risk='high'.")


def build_calculation_solver(sample, tool_context=None):
    """Compact calculation agent — structured numeric JSON, small token budget (~384)."""
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    parts = [f"[CÂU HỎI]\n{sample.get('question','')}", f"[PHƯƠNG ÁN]\n{_opts(choices, labels)}"]
    if tool_context:
        parts.append(str(tool_context))
    parts.append(f"Chọn đúng một nhãn trong [{', '.join(labels)}]. Trả về JSON gọn.")
    return [{"role": "system", "content": _CALC_SYS}, {"role": "user", "content": "\n\n".join(parts)}]


def build_pairwise_judge(sample, v10_answer, alternatives):
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    sys = ("Bạn là trọng tài. So sánh đáp án v10 với các ứng viên thay thế. ƯU TIÊN bằng "
           "chứng/chứng minh hơn là độ tự tin. KHÔNG dùng đáp án chuẩn ẩn. Trả về DUY NHẤT "
           'JSON: {"winner_answer":"<NHÃN>","confidence":<0..1>,"reason":"<ngắn>",'
           '"requires_manual_review":true|false}.')
    alt = "\n".join(f"- {a.get('source')}: {a.get('answer')} "
                    f"(risk={a.get('risk_level','?')}; {a.get('proof_text') or a.get('evidence_text','')})"
                    for a in alternatives)
    user = (f"[CÂU HỎI]\n{sample.get('question','')}\n\n[PHƯƠNG ÁN]\n{_opts(choices, labels)}\n\n"
            f"v10: {v10_answer}\n[ỨNG VIÊN THAY THẾ]\n{alt or '(không có)'}\n\n"
            f"Chọn winner_answer trong [{', '.join(labels)}].")
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


# --- parsers ------------------------------------------------------------------

def parse_candidate(content, sample, *, answer_key="answer"):
    """Parse a standard agent reply -> normalized dict (answer normalized to a label).

    Quality gates: a low/medium-risk candidate with placeholder evidence AND placeholder
    rationale is rejected (``parse_status="placeholder_evidence"``); a candidate whose
    numeric evidence result is absent from the chosen option is rejected
    (``parse_status="numeric_mismatch"``). Parse-rejected candidates are not valid.
    """
    from src.candidate_consistency import (candidate_matches_option,
                                           detect_placeholder_evidence, strong_claim)
    labels = labels_for(len(sample.get("choices", []) or []))
    obj = _parse_json(content) or {}
    ans = _norm_label(obj.get(answer_key), labels)
    evidence = str(obj.get("evidence") or "")[:300]
    rationale = str(obj.get("rationale") or "")[:300]
    risk = obj.get("risk") if obj.get("risk") in ("low", "medium", "high") else "medium"
    out = {"answer": ans, "confidence": _clamp(obj.get("confidence")),
           "rationale": rationale, "evidence": evidence, "risk": risk,
           "eliminated": obj.get("eliminated") if isinstance(obj.get("eliminated"), list) else None}
    if not ans:
        out["parse_status"] = "no_valid_label" if obj else "no_json"
        return out
    # Quality rejection (low/medium-risk only — a self-declared high-risk candidate is
    # already weak and won't override).
    if risk in ("low", "medium"):
        if detect_placeholder_evidence(evidence) and detect_placeholder_evidence(rationale):
            out["parse_status"] = "placeholder_evidence"
            return out

        class _C:  # lightweight candidate for the numeric check
            pass
        c = _C(); c.answer = ans; c.evidence_text = evidence; c.proof_text = ""; c.rationale = rationale
        if strong_claim(evidence + " " + rationale) is not None and not candidate_matches_option(c, sample):
            out["parse_status"] = "numeric_mismatch"
            return out
    out["parse_status"] = "ok"
    return out


def parse_calculation_candidate(content, sample):
    """Parse the calculation agent reply with strict numeric grounding.

    Rejects (``parse_status``) when: no valid label; ``final_numeric_value`` does not map
    to the chosen option; ``chosen_option_text`` does not match the selected label; the
    calculation steps are missing for a low/medium-risk answer; or evidence is a
    placeholder. Only an ``ok`` candidate is eligible downstream.
    """
    from src.candidate_consistency import detect_placeholder_evidence
    from src.option_grounding import map_claim_to_option
    choices = sample.get("choices", []) or []
    labels = labels_for(len(choices))
    obj = _parse_json(content) or {}
    ans = _norm_label(obj.get("final_answer"), labels)
    steps = obj.get("calculation_steps") if isinstance(obj.get("calculation_steps"), list) else []
    evidence = str(obj.get("evidence") or "")[:300]
    chosen_text = str(obj.get("chosen_option_text") or "")
    risk = obj.get("risk") if obj.get("risk") in ("low", "medium", "high") else "medium"
    numeric = obj.get("final_numeric_value")
    try:
        numeric = float(numeric) if numeric is not None else None
    except (TypeError, ValueError):
        numeric = None
    out = {"answer": ans, "confidence": _clamp(obj.get("confidence")),
           "rationale": " ".join(str(s) for s in steps)[:300], "evidence": evidence,
           "risk": risk, "final_numeric_value": numeric,
           "chosen_option_text": chosen_text[:160],
           "calculation_steps": [str(s)[:160] for s in steps[:4]]}
    if not ans:
        out["parse_status"] = "no_valid_label" if obj else "no_json"
        return out
    if risk in ("low", "medium"):
        if not steps:
            out["parse_status"] = "missing_steps"
            return out
        if detect_placeholder_evidence(evidence):
            out["parse_status"] = "placeholder_evidence"
            return out
        # final_numeric_value must map to the chosen option (unique).
        if numeric is not None and map_claim_to_option(numeric, choices) != ans:
            out["parse_status"] = "numeric_mismatch"
            return out
        # chosen_option_text must point at the selected label.
        sel_text = str(choices[labels.index(ans)]) if ans in labels and labels.index(ans) < len(choices) else ""
        if chosen_text and sel_text:
            mapped = map_claim_to_option(chosen_text, choices)
            if mapped is not None and mapped != ans:
                out["parse_status"] = "option_text_mismatch"
                return out
    out["parse_status"] = "ok"
    return out


def parse_judge(content, sample):
    labels = labels_for(len(sample.get("choices", []) or []))
    obj = _parse_json(content) or {}
    ans = _norm_label(obj.get("winner_answer"), labels)
    return {
        "winner_answer": ans, "confidence": _clamp(obj.get("confidence")),
        "reason": str(obj.get("reason") or "")[:300],
        "requires_manual_review": bool(obj.get("requires_manual_review", True)),
        "parse_status": "ok" if ans else ("no_valid_label" if obj else "no_json"),
    }


def _clamp(v):
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0
