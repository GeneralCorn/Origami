from services.pricing import cost_usd


def test_dated_id_resolves_through_its_alias():
    dated, priced = cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0, 0, 0)
    assert priced
    assert dated == 1.00


def test_undated_sonnet_alias_is_priced():
    cost, priced = cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000, 0, 0)
    assert priced
    assert cost == 18.00


def test_unknown_model_is_flagged_not_guessed():
    cost, priced = cost_usd("some-local-vlm:7b", 500, 500, 0, 0)
    assert (cost, priced) == (0.0, False)


def test_cached_input_is_not_billed_at_the_base_rate():
    """LangChain's input_tokens already includes the cached tokens.

    Pricing the total flat would charge 10x for a cache hit, which is the
    single easiest way to make the ledger lie about a caching win.
    """
    naive, _ = cost_usd("claude-haiku-4-5", 100_000, 0, 0, 0)
    cached, _ = cost_usd("claude-haiku-4-5", 100_000, 0, 99_000, 0)

    assert naive == 0.10
    # 1,000 billable at 1x + 99,000 read at 0.1x = 10,900 effective tokens
    assert round(cached, 6) == round(10_900 / 1_000_000, 6)
    assert cached < naive


def test_cache_write_costs_more_than_plain_input():
    plain, _ = cost_usd("claude-haiku-4-5", 10_000, 0, 0, 0)
    written, _ = cost_usd("claude-haiku-4-5", 10_000, 0, 0, 10_000)
    assert round(written / plain, 4) == 1.25


def test_output_is_priced_separately():
    cost, _ = cost_usd("claude-haiku-4-5", 0, 1_000_000, 0, 0)
    assert cost == 5.00
