"""Presidio masking adapted from kouki6951/pii-masking-chat/pii_chat/masker.py.

Retains Japanese NLP, overlap priorities, exclusions, and numbered placeholders;
does not retain original values or reversible mappings in results.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from threading import Lock

import spacy
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_analyzer.predefined_recognizers import (
    IpRecognizer, SpacyRecognizer, UrlRecognizer,
)

from .config import (
    DENYLIST_ENTITIES, ENTITY_LABELS_JA, MAX_TEXT_LENGTH, NER_DENYLIST,
    load_settings, parse_filters,
)
from .japanese_recognizers import get_japanese_recognizers


_CHUNK_TARGET_BYTES = 32 * 1024
# SudachiPy rejects any single input above 49149 bytes ("Input is too long"),
# regardless of spaCy's max_length, so oversized lines must be hard-split.
_MAX_CHUNK_BYTES = 40 * 1024


def _split_oversized_line(line: str) -> list[str]:
    """Split one line into pieces <= _MAX_CHUNK_BYTES utf-8 bytes without
    cutting a multi-byte character."""
    parts: list[str] = []
    cur: list[str] = []
    size = 0
    for ch in line:
        ch_size = len(ch.encode("utf-8"))
        if cur and size + ch_size > _MAX_CHUNK_BYTES:
            parts.append("".join(cur))
            cur = []
            size = 0
        cur.append(ch)
        size += ch_size
    if cur:
        parts.append("".join(cur))
    return parts


def _iter_text_chunks(text: str) -> Iterator[str]:
    """Keep complete lines; hard-split single lines larger than the byte limit."""
    lines = []
    size = 0
    for line in text.splitlines(keepends=True):
        line_size = len(line.encode("utf-8"))
        if line_size > _MAX_CHUNK_BYTES:
            if lines:
                yield "".join(lines)
                lines = []
                size = 0
            yield from _split_oversized_line(line)
            continue
        if lines and size + line_size > _CHUNK_TARGET_BYTES:
            yield "".join(lines)
            lines = []
            size = 0
        lines.append(line)
        size += line_size
    if lines:
        yield "".join(lines)


_JA_MORPH_LEAK_MARKER = "token.morph = MorphAnalysis(self.vocab, morph)"


def _patch_ja_morph_leak(nlp) -> None:
    """Mitigate explosion/spaCy#13684: the ja tokenizer builds a fresh
    MorphAnalysis per token and those objects enter reference cycles that gc
    cannot collect (~0.5MiB/request on long-lived services).

    Reuse one MorphAnalysis per distinct (inflection, reading) pair — the
    analysis content is identical, so behaviour is unchanged. Also drop the
    morphologizer pipe, which repeats the same per-token leak in the pipeline;
    NER/masking output is unaffected (validated on 300 synthetic PII
    sentences) and it can be kept with PII_KEEP_MORPHOLOGIZER=1.

    If spaCy fixes this upstream the source marker disappears and both
    mitigations become no-ops/skippable.
    """
    import inspect
    import os
    import re

    import spacy.lang.ja as spacy_ja
    from spacy.tokens import Doc, MorphAnalysis

    try:
        source = inspect.getsource(spacy_ja.JapaneseTokenizer.__call__)
    except (OSError, TypeError):
        source = ""
    if _JA_MORPH_LEAK_MARKER in source:
        cache: dict[tuple[str, str], MorphAnalysis] = {}
        empty = MorphAnalysis(nlp.vocab, {})

        def _morph_cached_call(self, text):
            sudachipy_tokens = self.tokenizer.tokenize(text)
            dtokens = self._get_dtokens(sudachipy_tokens)
            dtokens, spaces = spacy_ja.get_dtokens_and_spaces(dtokens, text)
            words, tags, inflections, lemmas, norms, readings, sub_tokens_list = (
                zip(*dtokens) if dtokens else [[]] * 7
            )
            sub_tokens_list = list(sub_tokens_list)
            doc = Doc(self.vocab, words=list(words), spaces=spaces)
            next_pos = None
            for idx, (token, dtoken) in enumerate(zip(doc, dtokens)):
                token.tag_ = dtoken.tag
                if next_pos:
                    token.pos = next_pos
                    next_pos = None
                else:
                    token.pos, next_pos = spacy_ja.resolve_pos(
                        token.orth_, dtoken.tag,
                        tags[idx + 1] if idx + 1 < len(tags) else None,
                    )
                token.lemma_ = dtoken.lemma if dtoken.lemma else dtoken.surface
                token.norm_ = dtoken.norm
                key = (dtoken.inf, dtoken.reading)
                analysis = cache.get(key)
                if analysis is None:
                    morph = {}
                    if dtoken.inf:
                        morph["Inflection"] = dtoken.inf
                    if dtoken.reading:
                        morph["Reading"] = re.sub("[=|]", "_", dtoken.reading)
                    analysis = MorphAnalysis(self.vocab, morph) if morph else empty
                    cache[key] = analysis
                token.morph = analysis
            if self.need_subtokens:
                doc.user_data["sub_tokens"] = sub_tokens_list
            return doc

        _morph_cached_call.__name__ = "_morph_cached_call"
        spacy_ja.JapaneseTokenizer.__call__ = _morph_cached_call

    if os.environ.get("PII_KEEP_MORPHOLOGIZER") != "1" \
            and "morphologizer" in nlp.pipe_names:
        nlp.disable_pipes("morphologizer")


@dataclass(frozen=True)
class DetectedEntity:
    entity_type: str
    start: int
    end: int
    score: float
    placeholder: str


@dataclass(frozen=True)
class MaskResult:
    masked_text: str
    entities: list[DetectedEntity]

    @property
    def has_pii(self) -> bool:
        return bool(self.entities)


class JapanesePiiMasker:
    _GENERIC_ENTITIES = frozenset(
        {"LOCATION", "DATE_TIME", "NRP", "ORGANIZATION", "PERSON", "URL"}
    )

    def __init__(
        self, spacy_model: str | None = None, score_threshold: float | None = None
    ) -> None:
        settings = load_settings()
        self.spacy_model = spacy_model or settings.get("SPACY_MODEL") or "ja_core_news_lg"
        self.score_threshold = (
            score_threshold if score_threshold is not None
            else float(settings.get("PII_SCORE_THRESHOLD") or "0.4")
        )
        if not 0 <= self.score_threshold <= 1:
            raise ValueError("PII_SCORE_THRESHOLD must be between 0 and 1")
        self.filters = parse_filters(settings.get("PII_FILTERS"))
        self._analyzer = self._build_analyzer()
        # SudachiPy's tokenizer is not thread-safe ("Tokenizer is already in
        # use... guard calls externally"); uvicorn serves sync endpoints from a
        # threadpool, so all analyzer calls must be serialized per process.
        self._analyzer_lock = Lock()

    def _build_analyzer(self) -> AnalyzerEngine:
        # Fail locally rather than letting Presidio download models at request time.
        if not spacy.util.is_package(self.spacy_model):
            raise RuntimeError("Install the configured Japanese spaCy model first")
        nlp_engine = NlpEngineProvider(nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "ja", "model_name": self.spacy_model}],
        }).create_engine()
        # spaCy's default limit is 1,000,000, below the API's 1 Mi-character limit.
        pipeline = nlp_engine.nlp["ja"]
        pipeline.max_length = max(pipeline.max_length, MAX_TEXT_LENGTH)
        _patch_ja_morph_leak(pipeline)
        registry = RecognizerRegistry(supported_languages=["ja"])
        registry.add_recognizer(SpacyRecognizer(supported_language="ja"))
        registry.add_recognizer(IpRecognizer(supported_language="ja"))
        registry.add_recognizer(UrlRecognizer(supported_language="ja"))
        for recognizer in get_japanese_recognizers():
            registry.add_recognizer(recognizer)
        return AnalyzerEngine(
            nlp_engine=nlp_engine, registry=registry, supported_languages=["ja"]
        )

    @classmethod
    def _resolve_overlaps(
        cls, results: list[RecognizerResult]
    ) -> list[RecognizerResult]:
        def sort_key(result):
            return (
                result.entity_type in cls._GENERIC_ENTITIES,
                -result.score,
                -(result.end - result.start),
            )

        chosen = []
        for result in sorted(results, key=sort_key):
            if not any(
                result.start < other.end and result.end > other.start
                for other in chosen
            ):
                chosen.append(result)
        return sorted(chosen, key=lambda result: result.start)

    def mask(self, text: str) -> MaskResult:
        counters: dict[str, int] = {}
        value_to_token: dict[tuple[str, str], str] = {}
        pieces = []
        entities = []
        offset = 0
        for chunk in _iter_text_chunks(text):
            with self._analyzer_lock:
                results = self._analyzer.analyze(
                    text=chunk, language="ja", score_threshold=self.score_threshold,
                    entities=self.filters,
                )
            results = [
                result for result in results
                if not (
                    result.entity_type in DENYLIST_ENTITIES
                    and chunk[result.start:result.end] in NER_DENYLIST
                )
            ]
            last = 0
            for result in self._resolve_overlaps(results):
                original = chunk[result.start:result.end]
                label = ENTITY_LABELS_JA.get(result.entity_type, result.entity_type)
                key = (result.entity_type, original)
                token = value_to_token.get(key)
                if token is None:
                    counters[label] = counters.get(label, 0) + 1
                    token = f"<{label}_{counters[label]}>"
                    value_to_token[key] = token
                pieces.extend((chunk[last:result.start], token))
                last = result.end
                entities.append(DetectedEntity(
                    entity_type=result.entity_type,
                    start=offset + result.start, end=offset + result.end,
                    score=round(result.score, 3), placeholder=token,
                ))
            pieces.append(chunk[last:])
            offset += len(chunk)
        return MaskResult(masked_text="".join(pieces), entities=entities)


_default_masker: JapanesePiiMasker | None = None
_masker_lock = Lock()


def get_masker() -> JapanesePiiMasker:
    """Load the model once per worker, even during concurrent first requests."""
    global _default_masker
    with _masker_lock:
        if _default_masker is None:
            _default_masker = JapanesePiiMasker()
        return _default_masker
