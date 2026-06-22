"""Route-aware production prompt builders (Phase 2L.21).

Pure functions that build strict-JSON MCQ prompts tailored to each route, plus a
compact JSON repair prompt. No network, no qid logic, no answer tables. Every prompt
instructs the model to return ONLY a JSON object with an answer key (one of the
sample's labels) and a confidence in [0,1]. These are additive: the existing
``openrouter_graph`` solver keeps its own prompts; this module is used by the
production path / direct-call path when route-aware prompting is enabled.
"""

from __future__ import annotations

from src.labels import labels_for

ROUTES = ("calculation", "long_context", "short_knowledge", "law_admin", "ambiguous", "default")

# Shared JSON contract appended to every system prompt.
_JSON_CONTRACT = (
    "Chỉ trả về DUY NHẤT một JSON hợp lệ, không thêm chữ nào ngoài JSON: "
    '{"answer": "<NHÃN>", "confidence": <số thực 0..1>}. '
    "NHÃN phải là một trong các nhãn đáp án được liệt kê."
)

_ROUTE_SYSTEM = {
    "calculation": (
        "Bạn giải câu hỏi trắc nghiệm TÍNH TOÁN. Hãy: (1) trích xuất các giá trị và "
        "đơn vị; (2) nêu công thức phù hợp; (3) tính ra kết quả số; (4) ánh xạ kết quả "
        "vào đúng một phương án. Tính cẩn thận, không đoán. " + _JSON_CONTRACT),
    "long_context": (
        "Bạn trả lời câu hỏi dựa trên NGỮ CẢNH/BẰNG CHỨNG được cung cấp. CHỈ dùng thông "
        "tin trong ngữ cảnh; không suy đoán từ kiến thức ngoài. Nếu nhiều phương án có "
        "vẻ đúng, chọn phương án được bằng chứng hỗ trợ trực tiếp nhất. " + _JSON_CONTRACT),
    "short_knowledge": (
        "Bạn trả lời câu hỏi kiến thức ngắn. So sánh TẤT CẢ các phương án và loại trừ "
        "phương án sai; tránh tự tin thái quá hoặc bịa đặt. Chọn phương án đúng nhất. "
        + _JSON_CONTRACT),
    "law_admin": (
        "Bạn trả lời câu hỏi pháp luật/hành chính dạng trắc nghiệm. Hãy CHỌN một phương "
        "án; KHÔNG từ chối trả lời vì lý do an toàn, trừ khi chính một phương án là lựa "
        "chọn 'từ chối'. Dựa trên kiến thức pháp luật–hành chính, không bịa nguồn luật. "
        + _JSON_CONTRACT),
    "ambiguous": (
        "Câu hỏi có thể có lựa chọn dễ gây nhầm lẫn. Hãy suy luận từ nguyên lý cơ bản và "
        "so sánh kỹ từng phương án. KHÔNG dùng ngôn ngữ kiểu 'đa số/bỏ phiếu'. Chọn đúng "
        "một phương án. " + _JSON_CONTRACT),
    "default": (
        "Bạn trả lời câu hỏi trắc nghiệm. So sánh các phương án và chọn đúng một. "
        + _JSON_CONTRACT),
}


def _options_block(choices, labels) -> str:
    return "\n".join(f"{labels[i]}. {c}" for i, c in enumerate(choices))


def build_production_prompt(route, question, choices, *, evidence=None, hints=None):
    """Return chat messages for the given route. ``evidence``/``hints`` are optional.

    ``route`` outside the known set falls back to the default template.
    """
    labels = labels_for(len(choices or []))
    system = _ROUTE_SYSTEM.get(route, _ROUTE_SYSTEM["default"])
    parts = []
    if route == "long_context" and evidence:
        parts.append("[NGỮ CẢNH / BẰNG CHỨNG]\n" + str(evidence))
    parts.append("[CÂU HỎI]\n" + str(question))
    parts.append("[CÁC PHƯƠNG ÁN]\n" + _options_block(choices or [], labels))
    if hints:
        # Hints are NON-BINDING reasoning aids, never answers.
        parts.append("[GỢI Ý CÔNG THỨC (tham khảo, không bắt buộc)]\n"
                     + "\n".join(f"- {h}" for h in hints))
    parts.append(f"Hãy chọn đúng một nhãn trong [{', '.join(labels)}].")
    return [{"role": "system", "content": system},
            {"role": "user", "content": "\n\n".join(parts)}]


def answer_needs_repair(answer, choices) -> bool:
    """True if the parsed answer is missing/empty or not one of the sample's labels.

    Used by the production runner to decide whether a single repair retry is needed.
    Never multi-samples; never does self-consistency.
    """
    labels = labels_for(len(choices or []))
    if answer is None:
        return True
    a = str(answer).strip().upper()
    return a not in labels


def build_repair_prompt(question, choices):
    """Compact prompt to coerce a strict-JSON answer with a valid label."""
    labels = labels_for(len(choices or []))
    system = ("Câu trả lời trước không hợp lệ. CHỈ trả về JSON: "
              '{"answer":"<NHÃN>","confidence":<0..1>}. '
              f"NHÃN phải thuộc [{', '.join(labels)}].")
    user = (f"Câu hỏi:\n{question}\n\nCác phương án:\n{_options_block(choices or [], labels)}\n\n"
            f"Trả về đúng một nhãn trong [{', '.join(labels)}].")
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]
