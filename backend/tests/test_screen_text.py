"""The static half of "keep the bytes, fix the ranking".

Status bars and control labels are on every capture of an application and
say nothing about why the capture was taken. They stay in the record and
leave the embed text.
"""

import pytest

from services.screen_text import content_lines, derive_title, is_chrome, is_status_bar


@pytest.mark.parametrize("line", ["9:41", "09:41", "9:41 AM", "9.41 pm", "100%", "87 %", "5G", "LTE", "Wi-Fi", "WiFi"])
def test_status_bar_tokens_are_recognised(line):
    assert is_status_bar(line)


@pytest.mark.parametrize("line", ["9:41 ⚡ 5G 100%", "5G 100%", "9:41 AM  LTE  63%", "•••"])
def test_a_status_row_read_as_one_line_is_recognised(line):
    assert is_status_bar(line)


@pytest.mark.parametrize("line", ["5G networks explained", "Battery at 100% after 40 minutes", "At 9:41 the market opened"])
def test_prose_that_mentions_status_words_is_content(line):
    assert not is_status_bar(line)


@pytest.mark.parametrize("line", ["Back", "Done", "See All", "cancel", "Share", "Play", "›", "..."])
def test_control_labels_are_chrome(line):
    assert is_chrome(line)


@pytest.mark.parametrize("line", ["Share this recipe with a friend", "Back to the Future", "Play it again, Sam"])
def test_sentences_containing_control_words_are_content(line):
    assert not is_chrome(line)


def test_content_lines_keep_order_and_drop_chrome():
    lines = ["9:41", "5G 100%", "Back", "Netflix", "Severance", "Season 2, Episode 3", "Play", "Download"]

    assert content_lines(lines) == ["Netflix", "Severance", "Season 2, Episode 3"]


def test_content_lines_collapse_consecutive_duplicates_only():
    lines = ["Severance", "Severance", "Season 2", "Severance"]

    assert content_lines(lines) == ["Severance", "Season 2", "Severance"]


def test_content_lines_apply_the_length_floor():
    assert content_lines(["hi", "NVDA", "a"], min_chars=3) == ["NVDA"]
    assert content_lines(["hi", "NVDA", "a"], min_chars=1) == ["hi", "NVDA", "a"]


def test_whitespace_is_normalised():
    assert content_lines(["Play   Download  |  My List"]) == ["Play Download | My List"]


def test_derive_title_skips_chrome_and_needs_a_letter():
    assert derive_title(["9:41", "Back", "12345", "Attention Is All You Need", "abstract"]) == "Attention Is All You Need"


def test_derive_title_truncates():
    assert len(derive_title(["x" * 200])) == 80


def test_derive_title_is_empty_when_nothing_qualifies():
    assert derive_title(["9:41", "100%"]) == ""
