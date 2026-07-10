#!/usr/bin/env python3
"""Build the self-authored confidence-promotion benchmark.

The model-facing benchmark JSON intentionally contains only qid/question/choices.
The separate manifest contains the deterministic answer key and provenance needed
to audit it. Gold labels are derived from local arithmetic, local invented fact
tables, or small exhaustive solvers; never from the evaluated model.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.utils.labels import index_to_label, labels_for

SEED = 20260710
RECORDS_PER_CATEGORY = 40
TOTAL_RECORDS = 120
CHOICE_COUNTS = (2, 3, 4, 5, 6)
SUBSET30_RECORDS_PER_CATEGORY = 10
SUBSET30_TOTAL_RECORDS = 30

BENCHMARK_PATH = Path("validation/confidence_promotion_benchmark.json")
MANIFEST_PATH = Path("validation/confidence_promotion_manifest.json")
SUBSET30_BENCHMARK_PATH = Path("validation/confidence_promotion_subset30.json")
SUBSET30_MANIFEST_PATH = Path("validation/confidence_promotion_subset30_manifest.json")

CATEGORY_PROGRAMMATIC = "programmatic_arithmetic"
CATEGORY_CONTENT = "content_first"
CATEGORY_LOGIC = "least_to_most"

LAYER_PROGRAMMATIC = "programmatic_solver"
LAYER_CONTENT = "content_first"
LAYER_LOGIC = "least_to_most"

FORBIDDEN_GOLD_SOURCES = ("model", "llm", "qwen", "leaderboard", "organizer")


class BenchmarkValidationError(AssertionError):
    """Raised when the benchmark or manifest violates a validation invariant."""


@dataclass(frozen=True)
class DraftRecord:
    qid: str
    question: str
    correct_choice: str
    distractors: tuple[str, ...]
    category: str
    intended_v13_layer: str
    language: str
    template_id: str
    choice_count: int
    deterministic_gold: dict[str, Any]


def _format_number(value: float | int) -> str:
    value = float(value)
    if math.isclose(value, round(value), rel_tol=0.0, abs_tol=1e-9):
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _format_value(value: float | int, unit: str | None = None) -> str:
    text = _format_number(value)
    return f"{text} {unit}" if unit else text


def _numeric_distractors(answer: float | int, unit: str | None, *, spread: int = 1) -> tuple[str, ...]:
    value = float(answer)
    raw = [
        value + spread,
        value - spread,
        value + 2 * spread,
        value - 2 * spread,
        value * 2,
        value / 2 if value else 1,
        value + 10 * spread,
        abs(value - 10 * spread),
    ]
    out: list[str] = []
    correct = _format_value(value, unit)
    for candidate in raw:
        if candidate < 0:
            continue
        text = _format_value(candidate, unit)
        if text != correct and text not in out:
            out.append(text)
    return tuple(out)


def _programmatic_value(operation: str, params: dict[str, Any]) -> float:
    if operation == "arithmetic":
        return params["a"] + params["b"] * params["c"]
    if operation == "percentage":
        return params["whole"] * params["percent"] / 100.0
    if operation == "ratio":
        return params["known_total"] * params["target_ratio"] / params["known_ratio"]
    if operation == "unit_conversion":
        return params["amount"] * params["factor"]
    if operation == "algebra":
        return (params["rhs"] - params["offset"]) / params["coefficient"]
    if operation == "sequence":
        return params["start"] + params["step"] * params["next_index"]
    raise BenchmarkValidationError(f"unknown programmatic operation {operation!r}")


def solve_programmatic_gold(gold: dict[str, Any]) -> str:
    value = _programmatic_value(str(gold["operation"]), dict(gold["params"]))
    return _format_value(value, gold.get("unit"))


def _build_programmatic_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    variant = i % 6
    serial = i + 1
    if variant == 0:
        a = 11 + i
        b = 3 + (i % 5)
        c = 4 + (i % 4)
        operation = "arithmetic"
        params = {"a": a, "b": b, "c": c}
        question = (
            f"Compute {a} + {b} x {c}."
            if language == "en"
            else f"Tinh {a} + {b} x {c}."
        )
        unit = None
        spread = 1
    elif variant == 1:
        percent = (i % 5 + 2) * 5
        whole = 80 + 20 * (i % 7)
        operation = "percentage"
        params = {"percent": percent, "whole": whole}
        question = (
            f"What is {percent}% of {whole}?"
            if language == "en"
            else f"{percent}% cua {whole} la bao nhieu?"
        )
        unit = None
        spread = 5
    elif variant == 2:
        target_ratio = 2 + (i % 4)
        known_ratio = target_ratio + 1
        known_total = known_ratio * (6 + i % 5)
        operation = "ratio"
        params = {
            "target_ratio": target_ratio,
            "known_ratio": known_ratio,
            "known_total": known_total,
        }
        question = (
            "A mixture has red:blue = "
            f"{target_ratio}:{known_ratio}. If blue is {known_total}, how many red items?"
            if language == "en"
            else "Mot hon hop co ti le do:xanh = "
            f"{target_ratio}:{known_ratio}. Neu mau xanh la {known_total}, mau do la bao nhieu?"
        )
        unit = "items" if language == "en" else "vat"
        spread = target_ratio
    elif variant == 3:
        amount = 2 + (i % 8)
        factor = 1000 if i % 2 == 0 else 60
        from_unit = "kilometers" if factor == 1000 else "hours"
        to_unit = "meters" if factor == 1000 else "minutes"
        operation = "unit_conversion"
        params = {"amount": amount, "factor": factor, "from_unit": from_unit, "to_unit": to_unit}
        question = (
            f"Convert {amount} {from_unit} to {to_unit}."
            if language == "en"
            else f"Doi {amount} {'kilomet' if factor == 1000 else 'gio'} sang "
            f"{'met' if factor == 1000 else 'phut'}."
        )
        unit = to_unit if language == "en" else ("met" if factor == 1000 else "phut")
        spread = factor
    elif variant == 4:
        coefficient = 2 + (i % 5)
        answer = 3 + (i % 9)
        offset = 4 + (i % 6)
        rhs = coefficient * answer + offset
        operation = "algebra"
        params = {"coefficient": coefficient, "offset": offset, "rhs": rhs}
        question = (
            f"Solve for x: {coefficient}x + {offset} = {rhs}."
            if language == "en"
            else f"Giai x: {coefficient}x + {offset} = {rhs}."
        )
        unit = None
        spread = 1
    else:
        start = 5 + (i % 8)
        step = 2 + (i % 6)
        terms = [start + step * k for k in range(4)]
        operation = "sequence"
        params = {"start": start, "step": step, "next_index": 4}
        question = (
            f"The sequence adds {step}: {terms[0]}, {terms[1]}, {terms[2]}, {terms[3]}. "
            "What comes next?"
            if language == "en"
            else f"Day so moi buoc cong {step}: {terms[0]}, {terms[1]}, {terms[2]}, {terms[3]}. "
            "So tiep theo la gi?"
        )
        unit = None
        spread = step

    answer = _programmatic_value(operation, params)
    correct = _format_value(answer, unit)
    gold = {
        "kind": "programmatic",
        "gold_source": "computed_by_python_arithmetic",
        "operation": operation,
        "params": params,
        "unit": unit,
    }
    return DraftRecord(
        qid=f"cp_prog_{serial:03d}",
        question=question,
        correct_choice=correct,
        distractors=_numeric_distractors(answer, unit, spread=spread),
        category=CATEGORY_PROGRAMMATIC,
        intended_v13_layer=LAYER_PROGRAMMATIC,
        language=language,
        template_id=f"programmatic:{operation}:{language}",
        choice_count=choice_count,
        deterministic_gold=gold,
    )


_TERMS = (
    "mira", "solen", "naro", "velin", "pavo", "lumen", "karo", "davin",
    "seru", "talin", "boru", "ciran", "lato", "virel", "moren", "sika",
    "dorel", "anvi", "rokan", "elun", "maro", "sovel", "kiren", "tavo",
    "belin", "orim", "cavo", "niven", "lireo", "sumen", "ravel", "devon",
    "polen", "sorin", "tiren", "avon", "melu", "zano", "rilan", "tevon",
    "balen", "orven", "cirel", "navo", "dorin", "sevan", "liron", "piren",
)

_MEANINGS = (
    "blue lantern", "silver reed", "quiet drum", "river glass", "soft metal",
    "winter shell", "green compass", "hollow bell", "bright bridge", "stone ribbon",
    "amber leaf", "hidden gate", "calm engine", "woven map", "small thunder",
    "violet key", "paper moon", "clear ladder", "warm signal", "salt mirror",
    "round harbor", "sleeping wire", "cloud needle", "gentle magnet", "white orchard",
    "folded spark", "plain crystal", "silent marker", "yellow hinge", "open feather",
    "steady candle", "glass pebble", "north button", "thin anchor", "fresh wheel",
    "purple switch", "narrow window", "honest lever", "soft beacon", "tidy circuit",
    "red capsule", "level prism", "silver basket", "early whistle", "curved stamp",
    "square blossom", "clear feather", "golden bracket",
)


def _fact_window(start: int, size: int) -> list[tuple[str, str]]:
    return [(_TERMS[(start + j) % len(_TERMS)], _MEANINGS[(start + j) % len(_MEANINGS)])
            for j in range(size)]


def solve_content_gold(gold: dict[str, Any]) -> str:
    facts = dict(gold["facts"])
    ask = gold["ask"]
    if ask == "meaning_for_term":
        return str(facts[gold["term"]])
    if ask == "term_for_meaning":
        inverse = {meaning: term for term, meaning in facts.items()}
        return str(inverse[gold["meaning"]])
    raise BenchmarkValidationError(f"unknown content ask {ask!r}")


def _build_content_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    serial = i + 1
    facts = _fact_window(i * 3, max(6, choice_count))
    term, meaning = facts[i % len(facts)]
    ask_meaning = i % 2 == 0
    fact_text = "; ".join(f"{t} = {m}" for t, m in facts)
    if ask_meaning:
        question = (
            f"Use only these invented definitions: {fact_text}. What is the meaning of {term}?"
            if language == "en"
            else f"Chi dung bang dinh nghia tu tao nay: {fact_text}. Nghia cua {term} la gi?"
        )
        correct = meaning
        distractors = tuple(m for t, m in facts if t != term)
        ask = "meaning_for_term"
    else:
        question = (
            f"Use only these invented definitions: {fact_text}. Which term means {meaning}?"
            if language == "en"
            else f"Chi dung bang dinh nghia tu tao nay: {fact_text}. Thuat ngu nao co nghia la {meaning}?"
        )
        correct = term
        distractors = tuple(t for t, m in facts if m != meaning)
        ask = "term_for_meaning"
    gold = {
        "kind": "content_fact",
        "gold_source": "explicit_local_fact_table",
        "facts": facts,
        "ask": ask,
        "term": term,
        "meaning": meaning,
    }
    return DraftRecord(
        qid=f"cp_content_{serial:03d}",
        question=question,
        correct_choice=correct,
        distractors=distractors,
        category=CATEGORY_CONTENT,
        intended_v13_layer=LAYER_CONTENT,
        language=language,
        template_id=f"content:{ask}:{language}",
        choice_count=choice_count,
        deterministic_gold=gold,
    )


_ORDER_NAMES = (
    "Iris", "Jade", "Kilo", "Luma", "Miro", "Nia", "Orin", "Pax",
    "Quin", "Rhea", "Sato", "Tavi", "Uma", "Vera", "Wilo", "Yani",
)
_TASKS = (
    "Clay", "Ink", "Loom", "Mint", "Nova", "Opal", "Pearl", "Quill",
    "Reed", "Sage", "Tin", "Umber", "Vale", "Wave", "Yarn", "Zinc",
)
_BADGES = ("amber", "cobalt", "silver", "jade", "ivory", "coral")
_VI_BADGES = ("ho phach", "lam", "bac", "ngoc", "nga", "san ho")


def _join_order(order: tuple[str, ...]) -> str:
    return " -> ".join(order)


def _orders_satisfying(names: tuple[str, ...], before_pairs: tuple[tuple[str, str], ...]) -> list[tuple[str, ...]]:
    valid: list[tuple[str, ...]] = []
    for perm in itertools.permutations(names):
        positions = {name: idx for idx, name in enumerate(perm)}
        if all(positions[left] < positions[right] for left, right in before_pairs):
            valid.append(perm)
    return valid


def solve_ordering_gold(gold: dict[str, Any]) -> str:
    names = tuple(gold["names"])
    before_pairs = tuple(tuple(pair) for pair in gold["before_pairs"])
    valid = _orders_satisfying(names, before_pairs)
    if len(valid) != 1:
        raise BenchmarkValidationError(f"ordering gold is not unique: {valid}")
    return _join_order(valid[0])


def _build_ordering_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    names = tuple(_ORDER_NAMES[(i * 2 + j) % len(_ORDER_NAMES)] for j in range(3))
    before_pairs = ((names[0], names[1]), (names[1], names[2]))
    correct = solve_ordering_gold({"names": names, "before_pairs": before_pairs})
    distractors = tuple(_join_order(order) for order in itertools.permutations(names)
                        if _join_order(order) != correct)
    question = (
        f"Which of the following orders is consistent? {names[0]} is before {names[1]}, "
        f"and {names[1]} is before {names[2]}."
        if language == "en"
        else f"Phat bieu nao dung ve thu tu? {names[0]} dung truoc {names[1]}, "
        f"va {names[1]} dung truoc {names[2]}."
    )
    gold = {
        "kind": "ordering",
        "gold_source": "exhaustive_permutation_solver",
        "names": names,
        "before_pairs": before_pairs,
    }
    return DraftRecord(
        qid=f"cp_logic_order_{i + 1:03d}",
        question=question,
        correct_choice=correct,
        distractors=distractors,
        category=CATEGORY_LOGIC,
        intended_v13_layer=LAYER_LOGIC,
        language=language,
        template_id=f"logic:ordering:{language}",
        choice_count=choice_count,
        deterministic_gold=gold,
    )


def _render_schedule(order: tuple[str, str, str], language: str) -> str:
    if language == "en":
        return f"morning {order[0]}, midday {order[1]}, evening {order[2]}"
    return f"sang {order[0]}, trua {order[1]}, chieu {order[2]}"


def solve_schedule_gold(gold: dict[str, Any]) -> str:
    tasks = tuple(gold["tasks"])
    before_pairs = tuple(tuple(pair) for pair in gold["before_pairs"])
    valid = _orders_satisfying(tasks, before_pairs)
    if len(valid) != 1:
        raise BenchmarkValidationError(f"schedule gold is not unique: {valid}")
    return _render_schedule(valid[0], str(gold["language"]))


def _build_schedule_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    tasks = tuple(_TASKS[(i * 3 + j) % len(_TASKS)] for j in range(3))
    before_pairs = ((tasks[0], tasks[1]), (tasks[1], tasks[2]))
    correct = solve_schedule_gold({"tasks": tasks, "before_pairs": before_pairs, "language": language})
    distractors = tuple(_render_schedule(order, language) for order in itertools.permutations(tasks)
                        if _render_schedule(order, language) != correct)
    question = (
        f"A workshop schedule must satisfy both rules: {tasks[0]} before {tasks[1]}, "
        f"and {tasks[1]} before {tasks[2]}. Which schedule is possible?"
        if language == "en"
        else f"Lich xuong thuc hanh can thoa ca hai dieu kien: {tasks[0]} truoc {tasks[1]}, "
        f"va {tasks[1]} truoc {tasks[2]}. Phat bieu nao dung?"
    )
    gold = {
        "kind": "schedule",
        "gold_source": "exhaustive_permutation_solver",
        "tasks": tasks,
        "before_pairs": before_pairs,
        "language": language,
    }
    return DraftRecord(
        qid=f"cp_logic_schedule_{i + 1:03d}",
        question=question,
        correct_choice=correct,
        distractors=distractors,
        category=CATEGORY_LOGIC,
        intended_v13_layer=LAYER_LOGIC,
        language=language,
        template_id=f"logic:schedule:{language}",
        choice_count=choice_count,
        deterministic_gold=gold,
    )


def _assignment_solutions(
    people: tuple[str, ...],
    items: tuple[str, ...],
    fixed: tuple[tuple[str, str], ...],
    forbidden: tuple[tuple[str, str], ...],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for perm in itertools.permutations(items):
        assignment = dict(zip(people, perm))
        if all(assignment[person] == item for person, item in fixed) and all(
            assignment[person] != item for person, item in forbidden
        ):
            out.append(assignment)
    return out


def _render_assignment_statement(person: str, item: str, language: str) -> str:
    return f"{person} has the {item} badge" if language == "en" else f"{person} nhan huy hieu {item}"


def solve_assignment_gold(gold: dict[str, Any]) -> str:
    people = tuple(gold["people"])
    items = tuple(gold["items"])
    fixed = tuple(tuple(pair) for pair in gold["fixed"])
    forbidden = tuple(tuple(pair) for pair in gold["forbidden"])
    solutions = _assignment_solutions(people, items, fixed, forbidden)
    if len(solutions) != 1:
        raise BenchmarkValidationError(f"assignment gold is not unique: {solutions}")
    person, item = tuple(gold["target_statement"])
    if solutions[0].get(person) != item:
        raise BenchmarkValidationError("assignment target statement is false")
    return _render_assignment_statement(person, item, str(gold["language"]))


def _build_assignment_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    people = tuple(_ORDER_NAMES[(i * 3 + j) % len(_ORDER_NAMES)] for j in range(3))
    badges = _BADGES if language == "en" else _VI_BADGES
    items = tuple(badges[(i + j) % len(badges)] for j in range(3))
    fixed = ((people[0], items[1]), (people[2], items[0]))
    forbidden = ((people[1], items[0]),)
    target_statement = fixed[0]
    correct = solve_assignment_gold({
        "people": people,
        "items": items,
        "fixed": fixed,
        "forbidden": forbidden,
        "target_statement": target_statement,
        "language": language,
    })
    false_specs = [
        (people[0], items[0]),
        (people[1], items[0]),
        (people[1], items[1]),
        (people[2], items[2]),
        (people[2], items[1]),
    ]
    distractors = tuple(_render_assignment_statement(person, item, language) for person, item in false_specs)
    question = (
        f"Each person gets one badge and each badge is used once. Rules: {people[0]} has {items[1]}, "
        f"{people[2]} has {items[0]}, and {people[1]} does not have {items[0]}. "
        "Which of the following statements is true?"
        if language == "en"
        else f"Moi nguoi nhan mot huy hieu va moi huy hieu dung mot lan. Quy tac: "
        f"{people[0]} nhan {items[1]}, {people[2]} nhan {items[0]}, va {people[1]} khong nhan "
        f"{items[0]}. Phat bieu nao dung?"
    )
    gold = {
        "kind": "assignment",
        "gold_source": "exhaustive_assignment_solver",
        "people": people,
        "items": items,
        "fixed": fixed,
        "forbidden": forbidden,
        "target_statement": target_statement,
        "language": language,
    }
    return DraftRecord(
        qid=f"cp_logic_assign_{i + 1:03d}",
        question=question,
        correct_choice=correct,
        distractors=distractors,
        category=CATEGORY_LOGIC,
        intended_v13_layer=LAYER_LOGIC,
        language=language,
        template_id=f"logic:assignment:{language}",
        choice_count=choice_count,
        deterministic_gold=gold,
    )


def _table_passes(row: dict[str, str], rule: dict[str, str]) -> bool:
    return all(row.get(key) == value for key, value in rule.items())


def _render_table_statement(item: str, passes: bool, language: str) -> str:
    if language == "en":
        return f"{item} passes the gate" if passes else f"{item} does not pass the gate"
    return f"{item} vuot qua cong" if passes else f"{item} khong vuot qua cong"


def solve_table_gold(gold: dict[str, Any]) -> str:
    table = {item: dict(attrs) for item, attrs in gold["table"].items()}
    rule = dict(gold["rule"])
    item = str(gold["target_item"])
    passes = _table_passes(table[item], rule)
    if not passes:
        raise BenchmarkValidationError("table target item does not pass")
    return _render_table_statement(item, True, str(gold["language"]))


def _build_table_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    items = tuple(_TASKS[(i * 2 + j) % len(_TASKS)] for j in range(4))
    rule = {"texture": "smooth", "shape": "square"}
    table = {
        items[0]: {"texture": "smooth", "shape": "square"},
        items[1]: {"texture": "rough", "shape": "square"},
        items[2]: {"texture": "smooth", "shape": "round"},
        items[3]: {"texture": "rough", "shape": "round"},
    }
    correct = solve_table_gold({"table": table, "rule": rule, "target_item": items[0], "language": language})
    false_specs = [(items[1], True), (items[2], True), (items[3], True), (items[0], False), (items[2], False)]
    distractors = tuple(_render_table_statement(item, passes, language) for item, passes in false_specs)
    facts = "; ".join(f"{item}: {attrs['texture']} and {attrs['shape']}" for item, attrs in table.items())
    question = (
        "A token passes the gate only when it is smooth and square. "
        f"Local facts: {facts}. Which of the following statements is true?"
        if language == "en"
        else "Mot the vuot qua cong chi khi no min va vuong. "
        f"Bang su kien cuc bo: {facts}. Phat bieu nao dung?"
    )
    gold = {
        "kind": "table_conjunction",
        "gold_source": "deterministic_logic_table_solver",
        "table": table,
        "rule": rule,
        "target_item": items[0],
        "language": language,
    }
    return DraftRecord(
        qid=f"cp_logic_table_{i + 1:03d}",
        question=question,
        correct_choice=correct,
        distractors=distractors,
        category=CATEGORY_LOGIC,
        intended_v13_layer=LAYER_LOGIC,
        language=language,
        template_id=f"logic:table_conjunction:{language}",
        choice_count=choice_count,
        deterministic_gold=gold,
    )


def _build_logic_draft(i: int, choice_count: int, language: str) -> DraftRecord:
    variant = i % 4
    if variant == 0:
        return _build_ordering_draft(i, choice_count, language)
    if variant == 1:
        return _build_schedule_draft(i, choice_count, language)
    if variant == 2:
        return _build_assignment_draft(i, choice_count, language)
    return _build_table_draft(i, choice_count, language)


def solve_gold_choice(gold: dict[str, Any]) -> str:
    kind = str(gold.get("kind"))
    if kind == "programmatic":
        return solve_programmatic_gold(gold)
    if kind == "content_fact":
        return solve_content_gold(gold)
    if kind == "ordering":
        return solve_ordering_gold(gold)
    if kind == "schedule":
        return solve_schedule_gold(gold)
    if kind == "assignment":
        return solve_assignment_gold(gold)
    if kind == "table_conjunction":
        return solve_table_gold(gold)
    raise BenchmarkValidationError(f"unknown gold kind {kind!r}")


def _choice_count_for_index(i: int) -> int:
    return CHOICE_COUNTS[i % len(CHOICE_COUNTS)]


def _language_for_index(i: int) -> str:
    return "en" if i % 2 == 0 else "vi"


def _dedupe(items: tuple[str, ...] | list[str], *, exclude: str) -> list[str]:
    out: list[str] = []
    for item in items:
        text = str(item)
        if text == exclude or text in out:
            continue
        out.append(text)
    return out


def _materialize(draft: DraftRecord, *, expected_index: int, seed: int) -> dict[str, Any]:
    distractors = _dedupe(draft.distractors, exclude=draft.correct_choice)
    needed = draft.choice_count - 1
    if len(distractors) < needed:
        raise BenchmarkValidationError(f"{draft.qid} has too few distractors")
    choices = distractors[:needed]
    choices.insert(expected_index, draft.correct_choice)
    if len(choices) != len(set(choices)):
        raise BenchmarkValidationError(f"{draft.qid} has duplicate choices")
    expected_answer = index_to_label(expected_index)
    return {
        "qid": draft.qid,
        "question": draft.question,
        "choices": choices,
        "expected_answer": expected_answer,
        "category": draft.category,
        "intended_v13_layer": draft.intended_v13_layer,
        "choice_count": draft.choice_count,
        "language": draft.language,
        "generation_seed": seed,
        "template_id": draft.template_id,
        "deterministic_gold": draft.deterministic_gold,
    }


def build_manifest_records(seed: int = SEED) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    drafts_by_category: dict[str, list[DraftRecord]] = {
        CATEGORY_PROGRAMMATIC: [],
        CATEGORY_CONTENT: [],
        CATEGORY_LOGIC: [],
    }
    for i in range(RECORDS_PER_CATEGORY):
        choice_count = _choice_count_for_index(i)
        language = _language_for_index(i)
        drafts_by_category[CATEGORY_PROGRAMMATIC].append(
            _build_programmatic_draft(i, choice_count, language)
        )
        drafts_by_category[CATEGORY_CONTENT].append(
            _build_content_draft(i, choice_count, language)
        )
        drafts_by_category[CATEGORY_LOGIC].append(
            _build_logic_draft(i, choice_count, language)
        )

    # Shuffle within each category deterministically so templates/languages are not
    # presented in a mechanical repeating order, while category balance remains exact.
    for drafts in drafts_by_category.values():
        rng.shuffle(drafts)

    interleaved: list[DraftRecord] = []
    for i in range(RECORDS_PER_CATEGORY):
        interleaved.append(drafts_by_category[CATEGORY_PROGRAMMATIC][i])
        interleaved.append(drafts_by_category[CATEGORY_CONTENT][i])
        interleaved.append(drafts_by_category[CATEGORY_LOGIC][i])

    answer_position_counters: dict[int, int] = defaultdict(int)
    records: list[dict[str, Any]] = []
    for draft in interleaved:
        count = draft.choice_count
        expected_index = answer_position_counters[count] % count
        answer_position_counters[count] += 1
        records.append(_materialize(draft, expected_index=expected_index, seed=seed))
    return records


def build_benchmark_payload(seed: int = SEED) -> list[dict[str, Any]]:
    return [
        {"qid": record["qid"], "question": record["question"], "choices": record["choices"]}
        for record in build_manifest_records(seed)
    ]


def build_manifest_payload(seed: int = SEED) -> dict[str, Any]:
    records = build_manifest_records(seed)
    return {
        "metadata": {
            "name": "confidence_promotion_benchmark",
            "record_count": len(records),
            "seed": seed,
            "categories": dict(Counter(record["category"] for record in records)),
            "intended_v13_layers": dict(Counter(record["intended_v13_layer"] for record in records)),
            "choice_counts": {str(k): v for k, v in sorted(Counter(record["choice_count"] for record in records).items())},
            "languages": dict(Counter(record["language"] for record in records)),
            "gold_label_policy": (
                "Gold answers are produced only by deterministic local arithmetic, explicit "
                "self-authored fact tables, or exhaustive local constraint solvers."
            ),
        },
        "records": records,
    }


def _expected_index(record: dict[str, Any]) -> int:
    return labels_for(int(record["choice_count"])).index(str(record["expected_answer"]))


def select_subset30_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select a deterministic 30-record subset from the 120-record manifest.

    Selection is stratified by category, choice count, and language. Within each
    stratum, the pair that best improves answer-position balance is chosen by a
    deterministic score over manifest metadata only; no model predictions, router
    decisions, or accuracy outcomes are read.
    """
    by_qid = {record["qid"]: record for record in records}
    if len(by_qid) != len(records):
        raise BenchmarkValidationError("cannot select subset from records with duplicate qids")

    categories = (CATEGORY_PROGRAMMATIC, CATEGORY_CONTENT, CATEGORY_LOGIC)
    selected_by_category: dict[str, list[dict[str, Any]]] = {category: [] for category in categories}
    used_qids: set[str] = set()
    position_counts: dict[int, Counter[str]] = defaultdict(Counter)

    for category in categories:
        category_records = [record for record in records if record["category"] == category]
        for choice_count in CHOICE_COUNTS:
            en_candidates = sorted(
                (
                    record for record in category_records
                    if record["choice_count"] == choice_count and record["language"] == "en"
                    and record["qid"] not in used_qids
                ),
                key=lambda record: record["qid"],
            )
            vi_candidates = sorted(
                (
                    record for record in category_records
                    if record["choice_count"] == choice_count and record["language"] == "vi"
                    and record["qid"] not in used_qids
                ),
                key=lambda record: record["qid"],
            )
            if not en_candidates or not vi_candidates:
                raise BenchmarkValidationError(
                    f"missing subset candidates for {category}/{choice_count}"
                )

            def pair_score(pair: tuple[dict[str, Any], dict[str, Any]]) -> tuple:
                counter = Counter(position_counts[choice_count])
                for candidate in pair:
                    counter[candidate["expected_answer"]] += 1
                values = [counter.get(label, 0) for label in labels_for(choice_count)]
                imbalance = max(values) - min(values)
                total_expected_index = sum(_expected_index(candidate) for candidate in pair)
                return (
                    imbalance,
                    max(values),
                    total_expected_index,
                    pair[0]["qid"],
                    pair[1]["qid"],
                )

            pair = min(
                itertools.product(en_candidates, vi_candidates),
                key=pair_score,
            )
            for record in pair:
                selected_by_category[category].append(record)
                used_qids.add(record["qid"])
                position_counts[choice_count][record["expected_answer"]] += 1

    selected: list[dict[str, Any]] = []
    for i in range(SUBSET30_RECORDS_PER_CATEGORY):
        for category in categories:
            selected.append(selected_by_category[category][i])
    return [dict(record) for record in selected]


def build_subset30_manifest_payload(seed: int = SEED) -> dict[str, Any]:
    full_records = build_manifest_records(seed)
    records = select_subset30_records(full_records)
    return {
        "metadata": {
            "name": "confidence_promotion_subset30",
            "record_count": len(records),
            "source_manifest": str(MANIFEST_PATH),
            "source_benchmark": str(BENCHMARK_PATH),
            "selection_policy": (
                "Deterministic stratified selection from the 120-record self-authored "
                "benchmark: 10 records per category, one English and one Vietnamese "
                "record for each choice count within each category, with answer-position "
                "balance optimized from manifest metadata only."
            ),
            "seed": seed,
            "categories": dict(Counter(record["category"] for record in records)),
            "intended_v13_layers": dict(Counter(record["intended_v13_layer"] for record in records)),
            "choice_counts": {str(k): v for k, v in sorted(Counter(record["choice_count"] for record in records).items())},
            "languages": dict(Counter(record["language"] for record in records)),
        },
        "records": records,
    }


def build_subset30_benchmark_payload(seed: int = SEED) -> list[dict[str, Any]]:
    return [
        {"qid": record["qid"], "question": record["question"], "choices": record["choices"]}
        for record in build_subset30_manifest_payload(seed)["records"]
    ]


def _canonical_json_bytes(payload: Any) -> bytes:
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return (text + "\n").encode("utf-8")


def _json_normalized(payload: Any) -> Any:
    return json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def expected_label_for_manifest_record(record: dict[str, Any]) -> str:
    choices = list(record["choices"])
    gold_choice = solve_gold_choice(dict(record["deterministic_gold"]))
    try:
        index = choices.index(gold_choice)
    except ValueError as exc:
        raise BenchmarkValidationError(f"{record.get('qid')} gold choice not present in choices") from exc
    return index_to_label(index)


def validate_payloads(benchmark: list[dict[str, Any]], manifest: dict[str, Any], *, seed: int = SEED) -> dict[str, Any]:
    if not isinstance(benchmark, list):
        raise BenchmarkValidationError("benchmark must be a list")
    records = manifest.get("records")
    if not isinstance(records, list):
        raise BenchmarkValidationError("manifest.records must be a list")
    if len(benchmark) != len(records):
        raise BenchmarkValidationError("benchmark and manifest record counts differ")
    if len(records) < TOTAL_RECORDS:
        raise BenchmarkValidationError("benchmark must contain at least 120 records")
    if manifest.get("metadata", {}).get("seed") != seed:
        raise BenchmarkValidationError("manifest seed mismatch")

    qids: list[str] = []
    category_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()
    choice_counts: Counter[int] = Counter()
    language_counts: Counter[str] = Counter()
    positions_by_choice_count: dict[int, Counter[str]] = defaultdict(Counter)

    for ordinal, (bench_record, manifest_record) in enumerate(zip(benchmark, records)):
        if set(bench_record) != {"qid", "question", "choices"}:
            raise BenchmarkValidationError(f"benchmark record {ordinal} contains non-input fields")
        qid = manifest_record.get("qid")
        if bench_record.get("qid") != qid:
            raise BenchmarkValidationError(f"qid mismatch at ordinal {ordinal}")
        if bench_record.get("question") != manifest_record.get("question"):
            raise BenchmarkValidationError(f"question mismatch for {qid}")
        if bench_record.get("choices") != manifest_record.get("choices"):
            raise BenchmarkValidationError(f"choices mismatch for {qid}")
        if not isinstance(qid, str) or not qid:
            raise BenchmarkValidationError(f"invalid qid at ordinal {ordinal}")
        qids.append(qid)
        question = manifest_record.get("question")
        choices = manifest_record.get("choices")
        if not isinstance(question, str) or not question.strip():
            raise BenchmarkValidationError(f"{qid} has an invalid question")
        if isinstance(choices, (str, bytes)) or not isinstance(choices, list):
            raise BenchmarkValidationError(f"{qid} has invalid choices")
        choice_count = len(choices)
        if choice_count < 2 or choice_count > 26:
            raise BenchmarkValidationError(f"{qid} has unsupported choice count {choice_count}")
        if choice_count != manifest_record.get("choice_count"):
            raise BenchmarkValidationError(f"{qid} choice_count field mismatch")
        if len(set(choices)) != len(choices):
            raise BenchmarkValidationError(f"{qid} has duplicate choices")
        expected = manifest_record.get("expected_answer")
        if expected not in labels_for(choice_count):
            raise BenchmarkValidationError(f"{qid} expected answer is not canonical/in range")
        recomputed = expected_label_for_manifest_record(manifest_record)
        if recomputed != expected:
            raise BenchmarkValidationError(f"{qid} answer key mismatch: {expected} != {recomputed}")
        source = str(manifest_record.get("deterministic_gold", {}).get("gold_source", "")).lower()
        if not source or any(token in source for token in FORBIDDEN_GOLD_SOURCES):
            raise BenchmarkValidationError(f"{qid} has forbidden or missing gold source")
        if manifest_record.get("generation_seed") != seed:
            raise BenchmarkValidationError(f"{qid} generation seed mismatch")

        category_counts[str(manifest_record.get("category"))] += 1
        layer_counts[str(manifest_record.get("intended_v13_layer"))] += 1
        choice_counts[choice_count] += 1
        language_counts[str(manifest_record.get("language"))] += 1
        positions_by_choice_count[choice_count][str(expected)] += 1

    if len(qids) != len(set(qids)):
        raise BenchmarkValidationError("duplicate qid found")
    expected_categories = {
        CATEGORY_PROGRAMMATIC: RECORDS_PER_CATEGORY,
        CATEGORY_CONTENT: RECORDS_PER_CATEGORY,
        CATEGORY_LOGIC: RECORDS_PER_CATEGORY,
    }
    if dict(category_counts) != expected_categories:
        raise BenchmarkValidationError(f"category counts mismatch: {dict(category_counts)}")
    expected_layers = {
        LAYER_PROGRAMMATIC: RECORDS_PER_CATEGORY,
        LAYER_CONTENT: RECORDS_PER_CATEGORY,
        LAYER_LOGIC: RECORDS_PER_CATEGORY,
    }
    if dict(layer_counts) != expected_layers:
        raise BenchmarkValidationError(f"layer counts mismatch: {dict(layer_counts)}")
    expected_choice_counts = {count: TOTAL_RECORDS // len(CHOICE_COUNTS) for count in CHOICE_COUNTS}
    if dict(choice_counts) != expected_choice_counts:
        raise BenchmarkValidationError(f"choice-count distribution mismatch: {dict(choice_counts)}")
    if dict(language_counts) != {"en": TOTAL_RECORDS // 2, "vi": TOTAL_RECORDS // 2}:
        raise BenchmarkValidationError(f"language distribution mismatch: {dict(language_counts)}")
    for choice_count, counts in positions_by_choice_count.items():
        labels = labels_for(choice_count)
        values = [counts.get(label, 0) for label in labels]
        if max(values) - min(values) > 1:
            raise BenchmarkValidationError(
                f"answer positions imbalanced for {choice_count} choices: {dict(counts)}"
            )

    rebuilt_benchmark = build_benchmark_payload(seed)
    rebuilt_manifest = build_manifest_payload(seed)
    if _canonical_json_bytes(rebuilt_benchmark) != _canonical_json_bytes(benchmark):
        raise BenchmarkValidationError("benchmark is not byte-deterministic against generator")
    if _canonical_json_bytes(rebuilt_manifest) != _canonical_json_bytes(manifest):
        raise BenchmarkValidationError("manifest is not byte-deterministic against generator")

    return {
        "records": len(records),
        "categories": dict(category_counts),
        "layers": dict(layer_counts),
        "choice_counts": dict(choice_counts),
        "languages": dict(language_counts),
        "answer_positions_by_choice_count": {
            str(count): dict(counter) for count, counter in sorted(positions_by_choice_count.items())
        },
    }


def validate_subset30_payloads(
    subset_benchmark: list[dict[str, Any]],
    subset_manifest: dict[str, Any],
    full_benchmark: list[dict[str, Any]],
    full_manifest: dict[str, Any],
    *,
    seed: int = SEED,
) -> dict[str, Any]:
    full_summary = validate_payloads(full_benchmark, full_manifest, seed=seed)
    del full_summary

    records = subset_manifest.get("records")
    if not isinstance(subset_benchmark, list) or not isinstance(records, list):
        raise BenchmarkValidationError("subset benchmark/manifest shapes are invalid")
    if len(records) != SUBSET30_TOTAL_RECORDS or len(subset_benchmark) != SUBSET30_TOTAL_RECORDS:
        raise BenchmarkValidationError("subset30 must contain exactly 30 records")
    if subset_manifest.get("metadata", {}).get("seed") != seed:
        raise BenchmarkValidationError("subset manifest seed mismatch")

    full_by_qid = {record["qid"]: record for record in full_manifest["records"]}
    full_input_by_qid = {record["qid"]: record for record in full_benchmark}
    qids: list[str] = []
    category_counts: Counter[str] = Counter()
    layer_counts: Counter[str] = Counter()
    choice_counts: Counter[int] = Counter()
    language_counts: Counter[str] = Counter()
    positions_by_choice_count: dict[int, Counter[str]] = defaultdict(Counter)

    for ordinal, (bench_record, manifest_record) in enumerate(zip(subset_benchmark, records)):
        if set(bench_record) != {"qid", "question", "choices"}:
            raise BenchmarkValidationError(f"subset benchmark record {ordinal} contains non-input fields")
        qid = manifest_record.get("qid")
        if qid not in full_by_qid:
            raise BenchmarkValidationError(f"subset qid {qid!r} is not in the 120-record manifest")
        if _json_normalized(manifest_record) != _json_normalized(full_by_qid[qid]):
            raise BenchmarkValidationError(f"subset manifest record {qid} differs from source manifest")
        if bench_record != full_input_by_qid[qid]:
            raise BenchmarkValidationError(f"subset benchmark record {qid} differs from source benchmark")
        if bench_record["qid"] != qid:
            raise BenchmarkValidationError(f"subset qid mismatch at ordinal {ordinal}")
        expected = manifest_record["expected_answer"]
        choice_count = int(manifest_record["choice_count"])
        if expected not in labels_for(choice_count):
            raise BenchmarkValidationError(f"subset qid {qid} has invalid expected label")
        if expected_label_for_manifest_record(manifest_record) != expected:
            raise BenchmarkValidationError(f"subset qid {qid} answer key mismatch")
        qids.append(str(qid))
        category_counts[str(manifest_record["category"])] += 1
        layer_counts[str(manifest_record["intended_v13_layer"])] += 1
        choice_counts[choice_count] += 1
        language_counts[str(manifest_record["language"])] += 1
        positions_by_choice_count[choice_count][str(expected)] += 1

    if len(qids) != len(set(qids)):
        raise BenchmarkValidationError("subset has duplicate qids")
    expected_categories = {
        CATEGORY_PROGRAMMATIC: SUBSET30_RECORDS_PER_CATEGORY,
        CATEGORY_CONTENT: SUBSET30_RECORDS_PER_CATEGORY,
        CATEGORY_LOGIC: SUBSET30_RECORDS_PER_CATEGORY,
    }
    if dict(category_counts) != expected_categories:
        raise BenchmarkValidationError(f"subset category counts mismatch: {dict(category_counts)}")
    if dict(layer_counts) != {
        LAYER_PROGRAMMATIC: SUBSET30_RECORDS_PER_CATEGORY,
        LAYER_CONTENT: SUBSET30_RECORDS_PER_CATEGORY,
        LAYER_LOGIC: SUBSET30_RECORDS_PER_CATEGORY,
    }:
        raise BenchmarkValidationError(f"subset layer counts mismatch: {dict(layer_counts)}")
    if dict(choice_counts) != {count: 6 for count in CHOICE_COUNTS}:
        raise BenchmarkValidationError(f"subset choice-count distribution mismatch: {dict(choice_counts)}")
    if dict(language_counts) != {"en": 15, "vi": 15}:
        raise BenchmarkValidationError(f"subset language distribution mismatch: {dict(language_counts)}")

    rebuilt_benchmark = build_subset30_benchmark_payload(seed)
    rebuilt_manifest = build_subset30_manifest_payload(seed)
    if _canonical_json_bytes(rebuilt_benchmark) != _canonical_json_bytes(subset_benchmark):
        raise BenchmarkValidationError("subset benchmark is not byte-deterministic")
    if _canonical_json_bytes(rebuilt_manifest) != _canonical_json_bytes(subset_manifest):
        raise BenchmarkValidationError("subset manifest is not byte-deterministic")

    return {
        "records": len(records),
        "categories": dict(category_counts),
        "layers": dict(layer_counts),
        "choice_counts": dict(choice_counts),
        "languages": dict(language_counts),
        "answer_positions_by_choice_count": {
            str(count): dict(counter) for count, counter in sorted(positions_by_choice_count.items())
        },
    }


def write_payloads(
    *,
    benchmark_path: Path = BENCHMARK_PATH,
    manifest_path: Path = MANIFEST_PATH,
    seed: int = SEED,
) -> dict[str, Any]:
    benchmark = build_benchmark_payload(seed)
    manifest = build_manifest_payload(seed)
    summary = validate_payloads(benchmark, manifest, seed=seed)
    benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    benchmark_path.write_bytes(_canonical_json_bytes(benchmark))
    manifest_path.write_bytes(_canonical_json_bytes(manifest))
    return summary


def write_subset30_payloads(
    *,
    subset_benchmark_path: Path = SUBSET30_BENCHMARK_PATH,
    subset_manifest_path: Path = SUBSET30_MANIFEST_PATH,
    seed: int = SEED,
) -> dict[str, Any]:
    full_benchmark = build_benchmark_payload(seed)
    full_manifest = build_manifest_payload(seed)
    subset_benchmark = build_subset30_benchmark_payload(seed)
    subset_manifest = build_subset30_manifest_payload(seed)
    summary = validate_subset30_payloads(
        subset_benchmark, subset_manifest, full_benchmark, full_manifest, seed=seed
    )
    subset_benchmark_path.parent.mkdir(parents=True, exist_ok=True)
    subset_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    subset_benchmark_path.write_bytes(_canonical_json_bytes(subset_benchmark))
    subset_manifest_path.write_bytes(_canonical_json_bytes(subset_manifest))
    return summary


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-path", default=str(BENCHMARK_PATH))
    parser.add_argument("--manifest-path", default=str(MANIFEST_PATH))
    parser.add_argument("--subset-benchmark-path", default=str(SUBSET30_BENCHMARK_PATH))
    parser.add_argument("--subset-manifest-path", default=str(SUBSET30_MANIFEST_PATH))
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--check", action="store_true", help="validate existing files instead of writing them")
    parser.add_argument("--subset30-only", action="store_true", help="write/check only the subset30 files")
    args = parser.parse_args(argv)

    benchmark_path = Path(args.benchmark_path)
    manifest_path = Path(args.manifest_path)
    subset_benchmark_path = Path(args.subset_benchmark_path)
    subset_manifest_path = Path(args.subset_manifest_path)
    if args.check:
        full_benchmark = _read_json(benchmark_path)
        full_manifest = _read_json(manifest_path)
        if args.subset30_only:
            summary = validate_subset30_payloads(
                _read_json(subset_benchmark_path),
                _read_json(subset_manifest_path),
                full_benchmark,
                full_manifest,
                seed=args.seed,
            )
        else:
            summary = validate_payloads(full_benchmark, full_manifest, seed=args.seed)
            if subset_benchmark_path.exists() and subset_manifest_path.exists():
                summary["subset30"] = validate_subset30_payloads(
                    _read_json(subset_benchmark_path),
                    _read_json(subset_manifest_path),
                    full_benchmark,
                    full_manifest,
                    seed=args.seed,
                )
    else:
        if args.subset30_only:
            summary = write_subset30_payloads(
                subset_benchmark_path=subset_benchmark_path,
                subset_manifest_path=subset_manifest_path,
                seed=args.seed,
            )
        else:
            summary = write_payloads(benchmark_path=benchmark_path, manifest_path=manifest_path, seed=args.seed)
            summary["subset30"] = write_subset30_payloads(
                subset_benchmark_path=subset_benchmark_path,
                subset_manifest_path=subset_manifest_path,
                seed=args.seed,
            )
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
