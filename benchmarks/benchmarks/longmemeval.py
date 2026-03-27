"""LongMemEval dataset metadata and loader helpers for the benchmarking harness."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from benchmarks.models import (
    BenchmarkQuestion,
    MessageRole,
    QuestionCategory,
    Session,
    SessionMessage,
)

LONGMEMEVAL_DATASET_ID = "xiaowu0162/longmemeval-cleaned"
LONGMEMEVAL_DATASET_REVISION = "98d7416c24c778c2fee6e6f3006e7a073259d48f"
LONGMEMEVAL_S_FILENAME = "longmemeval_s_cleaned.json"

LONGMEMEVAL_DATE_FORMATS = (
    "%Y/%m/%d (%a) %H:%M",
    "%Y/%m/%d %H:%M",
)


@dataclass(frozen=True, slots=True)
class DatasetLock:
    """Committed lock metadata for a benchmark dataset artifact."""

    dataset_id: str
    revision: str
    filename: str
    source_url: str
    sha256: str
    size_bytes: int


LONGMEMEVAL_S_LOCK = DatasetLock(
    dataset_id=LONGMEMEVAL_DATASET_ID,
    revision=LONGMEMEVAL_DATASET_REVISION,
    filename=LONGMEMEVAL_S_FILENAME,
    source_url=(
        "https://huggingface.co/datasets/"
        "xiaowu0162/longmemeval-cleaned/resolve/"
        "98d7416c24c778c2fee6e6f3006e7a073259d48f/longmemeval_s_cleaned.json"
    ),
    sha256="d6f21ea9d60a0d56f34a05b609c79c88a451d2ae03597821ea3d5a9678c3a442",
    size_bytes=277383467,
)


def longmemeval_dataset_dir(root: Path | None = None) -> Path:
    """Return the gitignored download directory used for LongMemEval artifacts."""

    if root is None:
        root = Path(__file__).resolve().parents[1]
    return root / "datasets" / "longmemeval"


QUESTION_TYPE_TO_CATEGORY: dict[str, QuestionCategory] = {
    "single-session-user": QuestionCategory.INFORMATION_EXTRACTION,
    "single-session-assistant": QuestionCategory.INFORMATION_EXTRACTION,
    "single-session-preference": QuestionCategory.INFORMATION_EXTRACTION,
    "multi-session": QuestionCategory.MULTI_SESSION_REASONING,
    "temporal-reasoning": QuestionCategory.TEMPORAL_REASONING,
    "knowledge-update": QuestionCategory.KNOWLEDGE_UPDATES,
}


def longmemeval_dataset_path(root: Path | None = None) -> Path:
    """Return the default local path for the pinned LongMemEval-S artifact."""

    return longmemeval_dataset_dir(root=root) / LONGMEMEVAL_S_FILENAME


def _dataset_not_found_error(path: Path) -> FileNotFoundError:
    return FileNotFoundError(
        f"Dataset not found at {path}. Run: uv run python benchmarks/download_datasets.py"
    )


def _normalize_answer(answer: Any) -> str:
    """Normalize mixed answer types to a stable string representation."""

    if isinstance(answer, list):
        return "; ".join(_normalize_answer(item) for item in answer)
    if isinstance(answer, dict):
        return json.dumps(answer, sort_keys=True, ensure_ascii=True)
    if answer is None:
        return ""
    return str(answer).strip()


def _parse_datetime(date_str: str | None) -> datetime | None:
    """Parse the dataset's date formats into naive datetimes."""

    if date_str is None:
        return None

    normalized = date_str.strip()
    if not normalized:
        return None

    for fmt in LONGMEMEVAL_DATE_FORMATS:
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue

    raise ValueError(f"Unsupported LongMemEval datetime format: {date_str!r}")


def _skip_whitespace(buffer: str, start: int = 0) -> int:
    while start < len(buffer) and buffer[start].isspace():
        start += 1
    return start


def iter_question_records(path: Path | None = None) -> Iterator[dict[str, Any]]:
    """Yield dataset records one at a time from the top-level JSON array."""

    data_path = path or longmemeval_dataset_path()
    if not data_path.exists():
        raise _dataset_not_found_error(data_path)

    decoder = json.JSONDecoder()
    buffer = ""
    started = False
    exhausted = False

    with data_path.open(encoding="utf-8") as handle:
        while True:
            idx = _skip_whitespace(buffer)
            if idx:
                buffer = buffer[idx:]

            if not started:
                while not buffer and not exhausted:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        exhausted = True
                        break
                    buffer += chunk
                if not buffer:
                    raise ValueError(f"LongMemEval dataset at {data_path} is empty.")
                if buffer[0] != "[":
                    raise ValueError(f"Expected JSON array at {data_path}, found {buffer[0]!r}.")
                buffer = buffer[1:]
                started = True
                continue

            idx = _skip_whitespace(buffer)
            if idx:
                buffer = buffer[idx:]

            if buffer.startswith("]"):
                return

            while True:
                try:
                    record, end = decoder.raw_decode(buffer)
                    break
                except json.JSONDecodeError:
                    if exhausted:
                        raise ValueError(f"Incomplete JSON object while reading {data_path}.") from None
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        exhausted = True
                    buffer += chunk

            yield record
            buffer = buffer[end:]

            while True:
                idx = _skip_whitespace(buffer)
                if idx:
                    buffer = buffer[idx:]

                if buffer.startswith(","):
                    buffer = buffer[1:]
                    break
                if buffer.startswith("]"):
                    return
                if exhausted:
                    raise ValueError(f"Expected ',' or ']' while reading {data_path}.")

                chunk = handle.read(1024 * 1024)
                if not chunk:
                    exhausted = True
                buffer += chunk


def _category_for_record(question_id: str, raw_question_type: str) -> QuestionCategory:
    if question_id.endswith("_abs"):
        return QuestionCategory.ABSTENTION

    try:
        return QUESTION_TYPE_TO_CATEGORY[raw_question_type]
    except KeyError as exc:
        raise ValueError(f"Unknown question_type {raw_question_type!r} for question {question_id}.") from exc


def load_questions(path: Path | None = None, limit: int | None = None) -> list[BenchmarkQuestion]:
    """Load normalized LongMemEval questions without materializing all sessions."""

    questions: list[BenchmarkQuestion] = []
    for record in iter_question_records(path=path):
        questions.append(
            BenchmarkQuestion(
                question_id=record["question_id"],
                question=record["question"],
                question_type=record["question_type"],
                category=_category_for_record(record["question_id"], record["question_type"]),
                expected_answer=_normalize_answer(record.get("answer")),
                question_date=record.get("question_date"),
                question_timestamp=_parse_datetime(record.get("question_date")),
                answer_session_ids=list(record.get("answer_session_ids", [])),
                haystack_session_ids=list(record.get("haystack_session_ids", [])),
                haystack_dates=list(record.get("haystack_dates", [])),
                metadata={
                    "answer_type": type(record.get("answer")).__name__,
                    "haystack_session_count": len(record.get("haystack_sessions", [])),
                },
            )
        )
        if limit is not None and len(questions) >= limit:
            break
    return questions


def load_sessions_for_question(question_id: str, path: Path | None = None) -> list[Session]:
    """Load normalized haystack sessions for a single LongMemEval question."""

    for record in iter_question_records(path=path):
        if record["question_id"] != question_id:
            continue

        sessions: list[Session] = []
        answer_session_ids = set(record.get("answer_session_ids", []))
        haystack_dates = record.get("haystack_dates", [])
        haystack_session_ids = record.get("haystack_session_ids", [])

        for index, raw_session in enumerate(record.get("haystack_sessions", [])):
            session_id = (
                haystack_session_ids[index] if index < len(haystack_session_ids) else f"{question_id}-session-{index}"
            )
            raw_timestamp = haystack_dates[index] if index < len(haystack_dates) else None
            messages = [
                SessionMessage(
                    role=MessageRole(turn["role"]),
                    content=turn["content"],
                    has_answer=bool(turn.get("has_answer", False)),
                )
                for turn in raw_session
            ]
            contains_answer = session_id in answer_session_ids or any(message.has_answer for message in messages)

            sessions.append(
                Session(
                    session_id=session_id,
                    messages=messages,
                    timestamp=_parse_datetime(raw_timestamp),
                    metadata={
                        "question_id": question_id,
                        "question_date": record.get("question_date"),
                        "question_type": record["question_type"],
                        "haystack_date": raw_timestamp,
                        "source_index": index,
                        "contains_answer": contains_answer,
                    },
                )
            )

        return sessions

    raise ValueError(f"Question {question_id} not found in dataset.")


def get_category_distribution(questions: list[BenchmarkQuestion]) -> dict[str, int]:
    """Return a stable count map for every benchmark category."""

    distribution = {category.value: 0 for category in QuestionCategory}
    for question in questions:
        distribution[question.category.value] += 1
    return distribution
