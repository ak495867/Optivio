"""Tests for the central env-backed configuration (options_agent/config.py)."""

from options_agent.config import load_settings


def test_risk_knobs_read_from_env():
    s = load_settings(
        {
            "OPTIVIO_MAX_ORDER_NOTIONAL": "500",
            "OPTIVIO_MAX_OPEN_NOTIONAL": "2000",
            "OPTIVIO_MAX_DAILY_LOSS_FRACTION": "0.01",
            "OPTIVIO_KILL_SWITCH": "true",
        }
    )
    assert s.max_order_notional == 500.0
    assert s.max_open_notional == 2000.0
    assert s.max_daily_loss_fraction == 0.01
    assert s.kill_switch is True


def test_greeks_limits_read_from_env():
    s = load_settings(
        {
            "OPTIVIO_MAX_ABS_DELTA": "900",
            "OPTIVIO_MAX_ABS_GAMMA": "400",
        }
    )
    assert s.max_abs_delta == 900.0
    assert s.max_abs_gamma == 400.0


def test_data_feed_canonical_and_legacy_alias():
    assert load_settings({"ALPACA_DATA_FEED": "sip"}).data_feed == "sip"
    # Legacy name is honored when the canonical one is unset.
    assert load_settings({"ALPACA_OPTIONS_FEED": "iex"}).data_feed == "iex"


def test_paper_guard_aliases():
    assert load_settings({"ALPACA_PAPER": "false"}).alpaca_paper is False
    assert (
        load_settings({"ALPACA_PAPER": "1", "OPTIVIO_PAPER_ONLY": "true"}).alpaca_paper
        is True
    )


def test_defaults_when_unset_are_safe():
    s = load_settings({})
    assert s.max_order_notional == 2500.0
    assert s.max_open_notional == 10000.0
    assert s.max_daily_loss_fraction == 0.02
    assert s.kill_switch is False
    assert s.data_feed == "indicative"
    assert s.alpaca_paper is True


def test_invalid_numbers_fall_back_to_default():
    s = load_settings({"OPTIVIO_MAX_ORDER_NOTIONAL": "not-a-number"})
    assert s.max_order_notional == 2500.0
    s2 = load_settings({"OPTIVIO_MAX_ORDER_NOTIONAL": "-1"})
    assert s2.max_order_notional == 2500.0


def test_test_symbols_split_and_strip():
    s = load_settings({"OPTIVIO_TEST_SYMBOLS": " SPY ,AAPL , IWM,"})
    assert s.test_symbols == ("SPY", "AAPL", "IWM")
