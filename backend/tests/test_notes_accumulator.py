"""research_notes is the only unbounded accumulator in the pipeline.

The full list is re-sent into every later analyze prompt, every review
prompt, and the final synthesis, so a duplicate on deep_research is paid
for up to four times.
"""

from services.agent import NOTES_CAP, _merge_notes


def test_exact_duplicates_are_dropped():
    existing = ["Transformers use scaled dot-product attention."]
    kept = _merge_notes(existing, [
        "Transformers use scaled dot-product attention.",
        "The model was trained on 8 GPUs.",
    ])
    assert kept == ["The model was trained on 8 GPUs."]


def test_duplicates_within_one_batch_are_dropped():
    kept = _merge_notes([], ["same finding here", "same finding here", "other finding"])
    assert kept == ["same finding here", "other finding"]


def test_matching_ignores_case_and_whitespace():
    kept = _merge_notes(["The  loss   is  hinge loss."], ["the loss is hinge loss."])
    assert kept == []


def test_first_seen_order_is_preserved():
    kept = _merge_notes([], ["alpha finding", "beta finding", "gamma finding"])
    assert kept == ["alpha finding", "beta finding", "gamma finding"]


def test_distinct_notes_are_all_kept():
    candidates = [f"finding number {i} about scaling" for i in range(5)]
    assert _merge_notes([], candidates) == candidates


def test_a_normal_turn_never_reaches_the_cap():
    """Three analyze passes at a generous ten notes each."""
    assert NOTES_CAP > 3 * 10


def test_the_cap_bounds_a_pathological_output():
    candidates = [f"pathological finding {i}" for i in range(NOTES_CAP + 25)]
    assert len(_merge_notes([], candidates)) == NOTES_CAP


def test_a_full_list_accepts_nothing_further():
    existing = [f"finding {i}" for i in range(NOTES_CAP)]
    assert _merge_notes(existing, ["a genuinely new finding"]) == []
