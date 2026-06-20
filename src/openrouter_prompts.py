"""Prompt families for the OpenRouter graph solver (Vietnamese MCQA).

One system instruction per route. Every prompt:
  * is Vietnamese-aware,
  * enumerates ALL choices exactly with dynamic labels (never adds/removes one),
  * requires the model to answer with **one of the available labels**,
  * requires **JSON-only** output with the structured-answer fields,
  * asks for short evidence, not verbose chain-of-thought,
  * handles duplicate choice text by choosing a label (not the text).

Internal reasoning is allowed but must NOT appear in the output — only the JSON.
"""

from __future__ import annotations

from .labels import labels_for
from .prompting import format_choices

ROUTE_FAMILIES = (
    "short_knowledge", "long_context", "calculation",
    "law_admin", "safety_ethics", "ambiguous",
)

# JSON contract appended to every system prompt. Minimal-output by design:
# answer FIRST, evidence very short, JSON only, no chain-of-thought. This keeps
# the JSON from being truncated by long derivations (Phase 2K.2 correctness fix).
_JSON_CONTRACT = (
    "Chỉ in ra MỘT đối tượng JSON hợp lệ, KHÔNG kèm markdown hay bất kỳ văn bản nào khác. "
    "Trường \"answer\" PHẢI đứng ĐẦU TIÊN, theo đúng thứ tự khóa:\n"
    '{{"answer": "<NHÃN>", "confidence": <0..1>, '
    '"reason_type": "<lookup|reading|calculation|elimination|other>", '
    '"needs_review": <true|false>, "evidence": ["<manh mối ngắn>"]}}\n'
    '"answer" PHẢI là đúng một trong các nhãn: {labels}. Không tạo thêm lựa chọn mới; '
    "nếu hai lựa chọn trùng nội dung thì chọn theo nhãn.\n"
    "QUY TẮC NGẮN GỌN: KHÔNG suy luận từng bước, KHÔNG giải thích dài. "
    "\"evidence\" tối đa 2 mục, mỗi mục tối đa ~80 ký tự (chỉ manh mối/kết quả, không phải lời giải). "
    "Với câu tính toán: chỉ ghi kết quả ngắn, không ghi cả quá trình tính. "
    "Nếu không chắc, vẫn chọn nhãn tốt nhất và đặt confidence thấp."
)

_ROUTE_GUIDANCE = {
    "short_knowledge":
        "Đây là câu hỏi kiến thức ngắn. Chọn đáp án đúng nhất dựa trên kiến thức phổ quát.",
    "long_context":
        "Đây là câu hỏi đọc hiểu có đoạn văn. CHỈ dựa vào đoạn thông tin được cung cấp "
        "để chọn đáp án; trích evidence ngắn từ đoạn văn.",
    "calculation":
        "Đây là câu hỏi tính toán. Bạn có thể tính toán trong đầu, nhưng KHÔNG in ra "
        "các bước; chỉ chọn nhãn đáp án khớp kết quả.",
    "law_admin":
        "Đây là câu hỏi pháp luật/hành chính. Trả lời thận trọng, bám sát quy định; "
        "không suy diễn ngoài dữ kiện.",
    "safety_ethics":
        "Đây là câu hỏi an toàn/đạo đức. Chọn phương án an toàn, đúng chuẩn mực; "
        "không diễn giải có hại.",
    "ambiguous":
        "Câu hỏi có thể mơ hồ hoặc có lựa chọn gần giống nhau. Hãy loại trừ cẩn thận và "
        "chọn nhãn hợp lý nhất; đặt needs_review=true nếu không chắc chắn.",
}

_SYSTEM_BASE = (
    "Bạn là trợ lý giải trắc nghiệm tiếng Việt chính xác và súc tích. "
    "Nhiệm vụ: chọn đáp án đúng cho câu hỏi nhiều lựa chọn."
)


def system_prompt(route: str, labels: list[str]) -> str:
    guidance = _ROUTE_GUIDANCE.get(route, _ROUTE_GUIDANCE["short_knowledge"])
    contract = _JSON_CONTRACT.format(labels=", ".join(labels))
    return f"{_SYSTEM_BASE}\n{guidance}\n{contract}"


def user_prompt(sample: dict, labels: list[str], question_text: str | None = None) -> str:
    question = question_text if question_text is not None else (sample.get("question") or "")
    choices_block = format_choices(sample.get("choices", []) or [])
    return (
        f"Câu hỏi:\n{question}\n\n"
        f"Các lựa chọn:\n{choices_block}\n\n"
        f"Hãy chọn một nhãn trong [{', '.join(labels)}] và trả về JSON theo schema."
    )


def build_messages(route: str, sample: dict, *, question_text: str | None = None) -> list[dict]:
    """Build chat messages for a route. ``question_text`` overrides (e.g. compressed)."""
    labels = labels_for(len(sample.get("choices", []) or []))
    return [
        {"role": "system", "content": system_prompt(route, labels)},
        {"role": "user", "content": user_prompt(sample, labels, question_text)},
    ]


def repair_messages(route: str, sample: dict, prev_answer, *,
                    question_text: str | None = None) -> list[dict]:
    """A stricter retry prompt after an invalid/unparseable answer."""
    labels = labels_for(len(sample.get("choices", []) or []))
    msgs = build_messages(route, sample, question_text=question_text)
    msgs.append({
        "role": "user",
        "content": (
            f"Câu trả lời trước {('('+str(prev_answer)+') ') if prev_answer else ''}"
            f"không hợp lệ. Hãy trả về DUY NHẤT một JSON hợp lệ, với \"answer\" là đúng "
            f"một nhãn trong [{', '.join(labels)}]. Không thêm chữ nào ngoài JSON."
        ),
    })
    return msgs
