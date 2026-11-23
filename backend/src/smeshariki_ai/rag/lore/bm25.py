"""A small, side-effect-free implementation of the BM25 ranking function."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

Postings = Mapping[str, Mapping[int, int]]
Lengths = Mapping[int, int]


@dataclass(frozen=True, slots=True)
class Bm25Params:
    """Parameters of the scoring function; defaults follow the course guide."""

    k1: float = 1.2
    b: float = 0.75

    def __post_init__(self) -> None:
        if self.k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= self.b <= 1:
            raise ValueError("b must be between 0 and 1")


def idf(n_documents: int, document_frequency: int) -> float:
    """The BM25 IDF with the ``+0.5`` smoothing from the course guide."""

    if n_documents <= 0 or document_frequency <= 0:
        return 0.0
    numerator = n_documents - document_frequency + 0.5
    denominator = document_frequency + 0.5
    return math.log(1.0 + numerator / denominator)


def term_score(
    term_frequency: int,
    document_length: int,
    average_length: float,
    params: Bm25Params,
) -> float:
    """The frequency-and-length part of one query term's contribution."""

    if term_frequency <= 0 or document_length <= 0 or average_length <= 0:
        return 0.0
    length_ratio = document_length / average_length
    normalization = params.k1 * (1.0 - params.b + params.b * length_ratio)
    return term_frequency * (params.k1 + 1.0) / (term_frequency + normalization)


def unique_terms(terms: Sequence[str]) -> tuple[str, ...]:
    """Query terms are counted once, as in the reference implementation."""

    return tuple(dict.fromkeys(term for term in terms if term))


def score(
    query_terms: Sequence[str],
    postings: Postings,
    lengths: Lengths,
    n_documents: int,
    average_length: float,
    params: Bm25Params,
) -> dict[int, float]:
    """Score every chunk that shares at least one term with the query."""

    scores: dict[int, float] = {}
    if n_documents <= 0 or average_length <= 0:
        return scores

    for term in unique_terms(query_terms):
        term_postings = postings.get(term)
        if not term_postings:
            continue
        term_idf = idf(n_documents, len(term_postings))
        if term_idf <= 0:
            continue
        for chunk_id, term_frequency in term_postings.items():
            length = lengths.get(chunk_id, 0)
            contribution = term_idf * term_score(
                term_frequency, length, average_length, params
            )
            if contribution <= 0:
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + contribution
    return scores


def rank(
    scores: Mapping[int, float],
    order: Mapping[int, tuple[str, int]],
    top_k: int,
) -> tuple[int, ...]:
    """Return positive-scoring chunks, highest score first and stable ties."""

    if top_k <= 0:
        return ()
    ranked = sorted(
        (chunk_id for chunk_id, value in scores.items() if value > 0),
        key=lambda chunk_id: (-scores[chunk_id], order[chunk_id]),
    )
    return tuple(ranked[:top_k])
