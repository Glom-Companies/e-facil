"""Réglages communs : aucun test n'appelle une vraie IA ni ne touche au cache réel."""
import pytest

from app import extraction as E


@pytest.fixture(autouse=True)
def sans_ia_reelle(monkeypatch, tmp_path):
    for cle in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GROQ_API_KEY"):
        monkeypatch.delenv(cle, raising=False)
    monkeypatch.setattr(E, "CACHE", tmp_path / "cache_extraction.json")
