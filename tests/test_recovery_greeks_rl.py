from datetime import UTC, datetime

import numpy as np

from options_agent.contracts import OptionRight
from options_agent.risk.greeks_engine import (
    calculate_greeks,
    implied_volatility,
    theoretical_price,
)
from options_agent.validation.offline_rl import LoggedTransition
from options_agent.validation.rl_champion import ConservativeChampionChallenger


def test_iv_round_trip_and_greeks():
    price = theoretical_price(100, 100, .02, 0, 1, .2, OptionRight.CALL)
    iv = implied_volatility(price, 100, 100, .02, 0, 1, OptionRight.CALL)
    result = calculate_greeks(price, 100, 100, .02, 0, 1, OptionRight.CALL, datetime(2026, 1, 1, tzinfo=UTC))
    assert iv is not None and abs(iv - .2) < 1e-5
    assert result.valid and result.vega is not None and result.vega > 0


def test_iv_rejects_impossible_price():
    assert implied_volatility(200, 100, 100, 0, 0, 1, OptionRight.CALL) is None


def test_challenger_must_pass_drawdown_and_support():
    states = [np.array([i]) for i in range(12)]
    transitions = [LoggedTransition(s, 1, .01 if i < 10 else -.02, s, False, 1.0, i) for i, s in enumerate(states)]
    framework = ConservativeChampionChallenger(min_advantage=-1.0, max_drawdown=.01)
    champion = framework.evaluate("champion", transitions, lambda _: 1)
    challenger = framework.evaluate("challenger", transitions, lambda _: 1)
    decision = framework.decide(champion, challenger)
    assert not decision.approved
