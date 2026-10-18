import json

from lore.observability import RunMetrics, Timer, estimate_cost, log_event


def test_estimate_cost_uses_price_table_and_defaults_for_unknown_models():
    assert estimate_cost("gemini-3.8-flash", 1_000_000, 0) == 0.75
    assert estimate_cost("gemini-3.5-flash-lite", 0, 1_000_000) == 2.5
    assert estimate_cost("some-new-model", 0, 1_000_000) == 12.0


def test_log_event_prints_one_json_line(capsys):
    log_event(event="x", n=1)
    line = json.loads(capsys.readouterr().out)
    assert line["event"] == "x" and line["n"] == 1 and "ts" in line


def test_timer_and_run_metrics():
    with Timer() as t:
        pass
    assert t.ms >= 0
    m = RunMetrics("inv:1")
    m.step()
    m.model_call("gemini-3-flash-preview", 1000, 100)
    m.root_cause_found()
    s = m.summary()
    assert (s.investigation_id, s.steps, s.model_calls, s.tokens_in) == ("inv:1", 1, 1, 1000)
    assert s.cost_usd > 0 and s.time_to_root_cause_ms is not None
