from unittest.mock import Mock

import pytest
import spacy
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine, NlpEngineProvider

from pii_masking.masker import JapanesePiiMasker
import pii_masking.config as config


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    for name in ("SPACY_MODEL", "PII_SCORE_THRESHOLD", "PII_FILTERS", "API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config, "DOTENV_PATH", tmp_path / ".env")


@pytest.fixture
def masker(monkeypatch):
    """Exercise real Presidio patterns with only the heavy NLP model bypassed."""
    tokenizer = spacy.blank("en")
    nlp_engine = Mock(spec=NlpEngine)
    nlp_engine.is_loaded.return_value = True
    nlp_engine.get_supported_languages.return_value = ["ja"]
    nlp_engine.get_supported_entities.return_value = []
    nlp_engine.nlp = {"ja": tokenizer}

    def process_text(text, language):
        tokens = tokenizer(text)
        return NlpArtifacts(
            entities=[], tokens=tokens,
            tokens_indices=[token.idx for token in tokens],
            lemmas=[token.text for token in tokens],
            nlp_engine=None, language=language,
        )

    nlp_engine.process_text.side_effect = process_text
    monkeypatch.setattr(spacy.util, "is_package", lambda name: True)
    monkeypatch.setattr(NlpEngineProvider, "create_engine", lambda self: nlp_engine)
    return JapanesePiiMasker()
