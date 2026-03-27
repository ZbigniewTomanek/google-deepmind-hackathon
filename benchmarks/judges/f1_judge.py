"""Token-level F1 scoring helpers for benchmark answer comparisons."""

from __future__ import annotations

import re
import string
from collections import Counter

_PUNCT_TRANSLATION = str.maketrans("", "", string.punctuation)
_ARTICLES_RE = re.compile(r"\b(a|an|the)\b")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    """Normalize free-form text into a stable QA-comparison form."""

    lowered = text.lower().translate(_PUNCT_TRANSLATION)
    without_articles = _ARTICLES_RE.sub(" ", lowered)
    return _WHITESPACE_RE.sub(" ", without_articles).strip()


def tokenize(text: str) -> list[str]:
    """Tokenize benchmark text after normalization."""

    normalized = normalize_text(text)
    if not normalized:
        return []
    return normalized.split(" ")


def compute_f1(prediction: str, reference: str) -> float:
    """Compute token-level F1 between a prediction and reference answer."""

    prediction_tokens = tokenize(prediction)
    reference_tokens = tokenize(reference)

    if not prediction_tokens and not reference_tokens:
        return 1.0
    if not prediction_tokens or not reference_tokens:
        return 0.0

    overlap = Counter(prediction_tokens) & Counter(reference_tokens)
    overlap_count = sum(overlap.values())
    if overlap_count == 0:
        return 0.0

    precision = overlap_count / len(prediction_tokens)
    recall = overlap_count / len(reference_tokens)
    return 2 * precision * recall / (precision + recall)
