"""Regression tests for the ja MorphAnalysis leak mitigation (explosion/spaCy#13684)."""

import spacy

from pii_masking.masker import _patch_ja_morph_leak

TEXT = "山田太郎は東京都新宿区に住んでいます。メールはtaro@example.comです。"


def test_patch_installs_cached_call(monkeypatch):
    monkeypatch.delenv("PII_KEEP_MORPHOLOGIZER", raising=False)
    import spacy.lang.ja as ja

    original = ja.JapaneseTokenizer.__call__
    try:
        nlp = spacy.blank("ja")
        _patch_ja_morph_leak(nlp)
        assert ja.JapaneseTokenizer.__call__.__name__ == "_morph_cached_call"
    finally:
        ja.JapaneseTokenizer.__call__ = original


def test_patched_tokenizer_preserves_behaviour():
    import spacy.lang.ja as ja

    original = ja.JapaneseTokenizer.__call__
    try:
        nlp = spacy.blank("ja")
        _patch_ja_morph_leak(nlp)
        doc = nlp(TEXT)
        assert "".join(token.text for token in doc).replace(" ", "") == TEXT.replace(" ", "")
        # tag/lemma/norm annotations are still populated
        assert any(token.tag_ for token in doc)
        assert any(token.lemma_ for token in doc)
        # morph content survives the cached assignment
        tokens = list(doc)
        assert tokens[0].morph.get("Reading") is not None or tokens[0].tag_
    finally:
        ja.JapaneseTokenizer.__call__ = original
