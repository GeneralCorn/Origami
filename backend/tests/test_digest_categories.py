"""The digest heading is chosen by model output, so it is a closed set.

The analyze prompt invites the VLM to invent a category, and that string
was interpolated straight into a "## {heading}" line.
"""

from services.digest import CATEGORY_ORDER, _category_slug, _format_category, normalize_category


def test_a_known_category_normalises_to_its_slug():
    assert normalize_category("Social Media") == "social_media"


def test_an_invented_category_files_under_other():
    assert normalize_category("cryptozoology") == "other"


def test_a_newline_cannot_write_markdown_structure():
    assert normalize_category("other\n\n## Injected") == "other"


def test_a_non_string_category_does_not_raise():
    assert normalize_category(["news"]) == "other"
    assert normalize_category(None) == "other"


def test_every_category_round_trips_through_its_heading():
    for category in CATEGORY_ORDER:
        assert _category_slug(_format_category(category)) == category
