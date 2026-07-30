"""Lever 3: which model each call gets, across the full cross product.

resolve_model is pure, so this needs no key and no mocking.
"""

import itertools

import pytest

from config import HAIKU_MODEL, SONNET_MODEL
from services import llm
from services.llm import Purpose, resolve_model

_ROUTES = ["fast_fact", "normal_rag", "deep_research"]
_NEVER_SONNET = [
    Purpose.CLASSIFY, Purpose.FAST_FACT, Purpose.ANALYZE,
    Purpose.REVIEW, Purpose.CONTEXTUALIZE,
]


@pytest.mark.parametrize(
    "purpose,route,has_notes",
    list(itertools.product(_NEVER_SONNET, _ROUTES, [True, False])),
)
def test_everything_but_the_final_synthesis_is_locked_to_haiku(purpose, route, has_notes):
    assert resolve_model(purpose, route, has_notes=has_notes).model == HAIKU_MODEL


def test_analyze_never_escalates_even_on_deep_research():
    """The most repeated call, carrying the largest input block."""
    assert resolve_model(Purpose.ANALYZE, "deep_research").model == HAIKU_MODEL


def test_deep_research_final_is_a_sonnet_floor():
    assert resolve_model(Purpose.FINAL_RESPONSE, "deep_research", has_notes=True).model == SONNET_MODEL


def test_normal_rag_final_defaults_to_sonnet():
    assert resolve_model(Purpose.FINAL_RESPONSE, "normal_rag", has_notes=True).model == SONNET_MODEL


@pytest.mark.parametrize("route", _ROUTES)
def test_empty_notes_downgrade_the_final_synthesis(route):
    """With no notes there are no sources, so there is nothing to synthesize."""
    assert resolve_model(Purpose.FINAL_RESPONSE, route, has_notes=False).model == HAIKU_MODEL


def test_cheap_final_flag_moves_only_normal_rag(monkeypatch):
    monkeypatch.setattr(llm, "CHEAP_FINAL", True)
    assert resolve_model(Purpose.FINAL_RESPONSE, "normal_rag", has_notes=True).model == HAIKU_MODEL
    # deep_research stays a floor even with the flag on.
    assert resolve_model(Purpose.FINAL_RESPONSE, "deep_research", has_notes=True).model == SONNET_MODEL


def test_cheap_final_is_off_by_default():
    """A quality bet nobody can A/B must not be the default."""
    assert llm.CHEAP_FINAL is False


@pytest.mark.parametrize("purpose,max_tokens,temperature", [
    (Purpose.CLASSIFY, 10, 0.0),
    (Purpose.FAST_FACT, 1024, 0.3),
    (Purpose.ANALYZE, 2048, 0.0),
    (Purpose.REVIEW, 256, 0.0),
    (Purpose.CONTEXTUALIZE, 100, 0.0),
])
def test_output_ceilings_and_temperatures(purpose, max_tokens, temperature):
    spec = resolve_model(purpose, "normal_rag")
    assert (spec.max_tokens, spec.temperature) == (max_tokens, temperature)


def test_final_synthesis_ceiling_is_unchanged_by_the_model_choice():
    for route, has_notes in itertools.product(_ROUTES, [True, False]):
        spec = resolve_model(Purpose.FINAL_RESPONSE, route, has_notes=has_notes)
        assert (spec.max_tokens, spec.temperature) == (4096, 0.3)


def test_every_purpose_resolves():
    """A new Purpose must be given a spec, not fall through to a KeyError."""
    for purpose in Purpose:
        assert resolve_model(purpose, "normal_rag").model
