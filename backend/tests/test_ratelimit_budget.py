"""Global daily budget (R-31)."""

from lore.api.ratelimit import DailyBudget


def test_budget_caps_per_day_and_resets_the_next_day():
    b = DailyBudget()
    assert b.take("investigation", 2, today="2026-10-18")
    assert b.take("investigation", 2, today="2026-10-18")
    assert not b.take("investigation", 2, today="2026-10-18")
    assert b.remaining("investigation", 2, today="2026-10-18") == 0
    assert b.take("investigation", 2, today="2026-10-19")  # a new UTC day


def test_zero_means_no_cap_and_kinds_are_separate():
    b = DailyBudget()
    assert all(b.take("ask", 0, today="d") for _ in range(50))
    assert b.remaining("ask", 0, today="d") is None
    assert b.take("investigation", 1, today="d") and not b.take("investigation", 1, today="d")
    assert b.take("ask", 1, today="d")
