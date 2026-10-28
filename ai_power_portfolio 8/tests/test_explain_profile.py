"""Week 7 tests: LLM wrapper fallbacks and the profile explanation flow."""
import sqlite3
from types import SimpleNamespace

import pytest

from src.ai import llm
from src.ai.explain_profile import explain_and_save, template_explanation, generate_explanation
from src.config.settings import SCHEMA_SQL_PATH
from src.questionnaire.store import submit_questionnaire, get_profile


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(SCHEMA_SQL_PATH.read_text())
    yield c
    c.close()


def _answers(**kw):
    base = dict(investment_amount=10000, time_horizon_years=10, risk_tolerance=3,
                loss_reaction=3, primary_goal="combination", monthly_contribution=200)
    base.update(kw)
    return base


class FakeClient:
    """Stands in for anthropic.Anthropic()."""
    def __init__(self, text=None, error=None):
        self._text, self._error = text, error
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        if self._error:
            raise self._error
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])


def test_generate_text_returns_none_without_key(monkeypatch):
    monkeypatch.setattr(llm.settings, "ANTHROPIC_API_KEY", "")
    assert llm.generate_text("hi") is None


def test_generate_text_uses_injected_client():
    assert llm.generate_text("hi", client=FakeClient(text="  hello  ")) == "hello"


def test_generate_text_returns_none_when_call_fails():
    assert llm.generate_text("hi", client=FakeClient(error=RuntimeError("boom"))) is None


def test_template_explanation_mentions_profile_and_disclaimer(conn):
    key = submit_questionnaire(conn, "u1", _answers())["user_profile_key"]
    text = template_explanation(get_profile(conn, key))
    assert "not personalized financial advice" in text
    assert get_profile(conn, key)["profile_name"] in text


def test_generate_explanation_falls_back_to_template(conn, monkeypatch):
    monkeypatch.setattr("src.ai.explain_profile.generate_text", lambda *a, **k: None)
    key = submit_questionnaire(conn, "u1", _answers())["user_profile_key"]
    text, source = generate_explanation(get_profile(conn, key))
    assert source == "template" and text


def test_generate_explanation_uses_llm_text_when_available(conn, monkeypatch):
    monkeypatch.setattr("src.ai.explain_profile.generate_text", lambda *a, **k: "LLM wrote this.")
    key = submit_questionnaire(conn, "u1", _answers())["user_profile_key"]
    text, source = generate_explanation(get_profile(conn, key))
    assert (text, source) == ("LLM wrote this.", "llm")


def test_explain_and_save_writes_to_warehouse(conn, monkeypatch):
    monkeypatch.setattr("src.ai.explain_profile.generate_text", lambda *a, **k: None)
    key = submit_questionnaire(conn, "u1", _answers())["user_profile_key"]
    assert get_profile(conn, key)["ai_explanation"] is None
    result = explain_and_save(conn, key)
    assert get_profile(conn, key)["ai_explanation"] == result["explanation"]
