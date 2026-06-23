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
    # --- Phase 2L.25 expansion (general definitions only) ---
    KnowledgeCard(
        "subnet_usable_hosts", "computer_science",
        ("subnet", "mặt nạ mạng", "usable hosts", "địa chỉ host", "tiền tố mạng", "prefix"),
        "Số host khả dụng trong một mạng con IPv4 = 2^(32 - prefix) - 2 (trừ địa chỉ "
        "mạng và broadcast).",
        "usable_hosts = 2^(32 - prefix) - 2", ("/24 ⇒ 254 host.",), ""),
    KnowledgeCard(
        "big_o_basics", "computer_science",
        ("độ phức tạp", "big-o", "big o", "vòng lặp lồng", "o(n)", "o(n^2)"),
        "Một vòng lặp đơn theo n là O(n); hai vòng lặp lồng nhau theo n là O(n^2); "
        "chia đôi mỗi bước là O(log n).",
        "single loop O(n); nested O(n^2); halving O(log n)", (), ""),
    KnowledgeCard(
        "kinematics_uniform", "physics",
        ("chuyển động đều", "vận tốc", "quãng đường", "thời gian", "s=vt"),
        "Chuyển động thẳng đều: quãng đường = vận tốc × thời gian.",
        "s = v · t (v = s/t, t = s/v)", ("v=10, t=5 ⇒ s=50.",), ""),
    KnowledgeCard(
        "kinetic_potential_energy", "physics",
        ("động năng", "thế năng", "kinetic energy", "potential energy"),
        "Động năng = ½·m·v²; thế năng trọng trường = m·g·h.",
        "KE = 0.5·m·v² ; PE = m·g·h", (), ""),
    KnowledgeCard(
        "wave_speed", "physics",
        ("vận tốc sóng", "tần số", "bước sóng", "wave speed", "frequency", "wavelength"),
        "Tốc độ sóng = tần số × bước sóng.",
        "v = f · λ", (), ""),
    KnowledgeCard(
        "basic_probability_ev", "statistics",
        ("xác suất", "kỳ vọng", "giá trị kỳ vọng", "expected value", "probability"),
        "Giá trị kỳ vọng = tổng (giá trị × xác suất). Xác suất nằm trong [0,1] và tổng "
        "các xác suất loại trừ nhau bằng 1.",
        "E[X] = Σ x_i · p_i", (), ""),
    KnowledgeCard(
        "mean_median_mode", "statistics",
        ("trung bình", "trung vị", "mốt", "mean", "median", "mode"),
        "Trung bình cộng = tổng/đếm; trung vị = giá trị giữa khi sắp xếp; mốt = giá trị "
        "xuất hiện nhiều nhất.",
        "mean=sum/n; median=middle; mode=most frequent", (), ""),
    KnowledgeCard(
        "break_even", "finance",
        ("hòa vốn", "điểm hòa vốn", "break-even"),
        "Sản lượng hòa vốn = chi phí cố định / (giá bán − chi phí biến đổi mỗi đơn vị).",
        "Q* = FC / (P − VC)", (), ""),
    KnowledgeCard(
        "roi_profit", "finance",
        ("roi", "lợi nhuận", "tỷ suất lợi nhuận", "return on investment", "profit"),
        "Lợi nhuận = doanh thu − chi phí; ROI = lợi nhuận / vốn đầu tư.",
        "profit = revenue − cost ; ROI = gain / investment", (), ""),
    KnowledgeCard(
        "civic_general", "civics",
        ("hiến pháp", "quyền", "nghĩa vụ", "nguyên tắc", "nhà nước"),
        "Khái niệm dân sự/hiến pháp chung: hiến pháp là luật cơ bản; công dân có quyền "
        "và nghĩa vụ theo quy định pháp luật.",
        "general civic definitions (no specific article numbers)",
        (), "Chỉ định nghĩa chung; KHÔNG suy ra số điều/khoản cụ thể."),
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


# Minimum relevance to retrieve: a trigger-term hit (1.5) clears it; an incidental
# single-word token overlap (~0.2) does not — so unrelated questions retrieve nothing.
_MIN_SCORE = 0.5


def retrieve_cards(question: str, top_k: int = 3) -> list:
    """Return up to ``top_k`` (card, score) pairs with score >= _MIN_SCORE, best first.

    Deterministic (ties broken by registry order). Selects no answer.
    """
    scored = [(c, score_card(c, question)) for c in CARDS]
    scored = [(c, s) for c, s in scored if s >= _MIN_SCORE]
    scored.sort(key=lambda cs: cs[1], reverse=True)
    return scored[: max(0, top_k)]
