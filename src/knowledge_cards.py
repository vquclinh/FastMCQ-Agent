"""Knowledge-card / RAG-lite foundation (Phase 2L.23).

A small set of GENERAL knowledge cards (concepts/formulas/rules) — NOT public-test
answers. A lexical scorer retrieves the most relevant cards for a question to support
future evidence-grounded reasoning. This module does NOT select an answer and uses no
qid logic, no ground truth, and no external sheet.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

_WORD = re.compile(r"\w+", re.UNICODE)
# Generic function words dropped so stopword-only overlap never retrieves a card.
_STOP = {"là", "và", "của", "có", "không", "các", "một", "những", "được", "cho", "với",
         "trong", "đến", "này", "đó", "khi", "thì", "ra", "vào", "về", "theo", "hay",
         "nào", "gì", "bao", "nhiêu", "sao", "vì", "để", "bằng", "trên", "dưới", "thủ",
         "đô", "the", "a", "an", "of", "to", "is", "in", "and", "or", "what", "which"}


@dataclass
class KnowledgeCard:
    id: str
    domain: str
    trigger_terms: tuple
    statement: str
    formula_or_rule: str
    examples: tuple = ()
    safety_notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


CARDS = (
    KnowledgeCard(
        "paging_logical_address", "computer_science",
        ("phân trang", "địa chỉ luận lý", "logical address", "paging", "offset", "độ dời"),
        "Trong phân trang, địa chỉ luận lý gồm số trang (page number) và độ dời trong "
        "trang (offset).",
        "logical address = (page number, page offset)",
        ("Không phải số frame; không phải kích thước trang.",),
        "Chỉ áp dụng khi hỏi cấu trúc địa chỉ luận lý trong phân trang."),
    KnowledgeCard(
        "mc_vs_average_cost", "economics",
        ("chi phí biên", "chi phí biến đổi trung bình", "chi phí trung bình", "marginal cost",
         "average variable cost", "average total cost", "avc", "atc"),
        "Khi sản lượng tăng thêm một đơn vị: nếu MC > chi phí trung bình thì chi phí "
        "trung bình tăng; MC < thì giảm; MC = thì không đổi.",
        "MC>AVG ⇒ AVG↑; MC<AVG ⇒ AVG↓; MC=AVG ⇒ AVG không đổi",
        ("AVC=15, MC=20 ⇒ AVC tăng.",),
        "Phân biệt rõ AVC và ATC theo câu hỏi."),
    KnowledgeCard(
        "pythagorean_distance", "math",
        ("vuông góc", "khoảng cách", "cạnh huyền", "pythagore", "pytago", "perpendicular"),
        "Khoảng cách thẳng giữa hai thành phần vuông góc là căn bậc hai của tổng bình phương.",
        "d = sqrt(a^2 + b^2)",
        ("a=100, b=150 ⇒ d=180.28.",), ""),
    KnowledgeCard(
        "resistor_cut_parallel", "physics",
        ("điện trở", "cắt", "song song", "hai phần bằng nhau"),
        "Cắt một điện trở R thành n phần bằng nhau rồi mắc song song: điện trở giảm "
        "theo n^2; dòng điện ở cùng hiệu điện thế tăng theo n^2.",
        "R_eq = R/n^2 ; I' = n^2 · I (n=2 ⇒ I'=4I)",
        ("n=2 ⇒ I'=4I.",), "Chỉ khi nêu rõ cắt đều và mắc song song."),
    KnowledgeCard(
        "ohms_law", "physics",
        ("định luật ohm", "hiệu điện thế", "dòng điện", "điện trở", "ohm"),
        "Định luật Ohm liên hệ hiệu điện thế, dòng điện và điện trở.",
        "V = I · R (I = V/R, R = V/I)",
        ("V=12, R=4 ⇒ I=3A.",), ""),
    KnowledgeCard(
        "operating_margin_asset_turnover", "finance",
        ("biên lợi nhuận hoạt động", "vòng quay tài sản", "operating margin", "asset turnover",
         "doanh thu", "tài sản"),
        "Biên lợi nhuận hoạt động = thu nhập hoạt động / doanh thu; vòng quay tài sản = "
        "doanh thu / tổng tài sản bình quân.",
        "operating margin = operating income / sales ; asset turnover = sales / assets",
        (), ""),
    KnowledgeCard(
        "cache_amat", "computer_science",
        ("cache", "bộ nhớ đệm", "thời gian truy cập trung bình", "amat", "miss rate", "hit time"),
        "Thời gian truy cập bộ nhớ trung bình = thời gian trúng + tỉ lệ trượt × hình phạt trượt.",
        "AMAT = hit_time + miss_rate × miss_penalty",
        ("hit=2, miss=10%, penalty=100 ⇒ AMAT=12.",), ""),
    KnowledgeCard(
        "database_keys", "computer_science",
        ("khóa chính", "khóa ngoại", "khóa dự tuyển", "primary key", "foreign key", "candidate key"),
        "Khóa chính định danh duy nhất một bản ghi; khóa dự tuyển là ứng viên làm khóa "
        "chính; khóa ngoại tham chiếu khóa chính của bảng khác.",
        "primary/candidate/foreign key definitions",
        (), "Định nghĩa khái niệm, không suy ra đáp án số."),
    KnowledgeCard(
        "normalization_forms", "computer_science",
        ("chuẩn hóa", "dạng chuẩn", "1nf", "2nf", "3nf"),
        "1NF: giá trị nguyên tử; 2NF: 1NF và không phụ thuộc bộ phận vào khóa; 3NF: 2NF "
        "và không phụ thuộc bắc cầu.",
        "1NF atomic; 2NF no partial dependency; 3NF no transitive dependency",
        (), ""),
    KnowledgeCard(
        "elasticity_total_revenue", "economics",
        ("co giãn", "doanh thu", "elastic", "inelastic", "tổng doanh thu"),
        "Cầu co giãn: tăng giá làm giảm tổng doanh thu, giảm giá làm tăng. Cầu không co "
        "giãn: ngược lại.",
        "elastic: P↑⇒TR↓, P↓⇒TR↑ ; inelastic: P↑⇒TR↑, P↓⇒TR↓",
        (), ""),
)

_REGISTRY = {c.id: c for c in CARDS}


def all_card_ids() -> list:
    return list(_REGISTRY.keys())


def get_card(card_id: str):
    return _REGISTRY.get(card_id)


def _tokens(text: str) -> set:
    return {t for t in (w.lower() for w in _WORD.findall(text or ""))
            if len(t) > 1 and t not in _STOP}


def score_card(card: KnowledgeCard, question: str) -> float:
    """Lexical relevance: weighted trigger-term hits + token overlap (0..~1+)."""
    low = str(question or "").lower()
    trigger_hits = sum(1 for t in card.trigger_terms if t in low)
    q_tokens = _tokens(question)
    c_tokens = _tokens(" ".join(card.trigger_terms) + " " + card.statement)
    overlap = len(q_tokens & c_tokens) / (len(q_tokens) or 1)
    return 1.5 * trigger_hits + overlap


def retrieve_cards(question: str, top_k: int = 3) -> list:
    """Return up to ``top_k`` (card, score) pairs with score > 0, best first.

    Deterministic (ties broken by registry order). Selects no answer.
    """
    scored = [(c, score_card(c, question)) for c in CARDS]
    scored = [(c, s) for c, s in scored if s > 0]
    scored.sort(key=lambda cs: cs[1], reverse=True)
    return scored[: max(0, top_k)]
