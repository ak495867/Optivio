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
    price = theoretical_price(100, 100, 0.02, 0, 1, 0.2, OptionRight.CALL)
    iv = implied_volatility(price, 100, 100, 0.02, 0, 1, OptionRight.CALL)
    result = calculate_greeks(
        price, 100, 100, 0.02, 0, 1, OptionRight.CALL, datetime(2026, 1, 1, tzinfo=UTC)
    )
    assert iv is not None and abs(iv - 0.2) < 1e-5
    assert result.valid and result.vega is not None and result.vega > 0


def test_iv_rejects_impossible_price():
    assert implied_volatility(200, 100, 100, 0, 0, 1, OptionRight.CALL) is None


def test_challenger_must_pass_drawdown_and_support():
    states = [np.array([i]) for i in range(12)]
    transitions = [
        LoggedTransition(s, 1, 0.01 if i < 10 else -0.02, s, False, 1.0, i)
        for i, s in enumerate(states)
    ]
    framework = ConservativeChampionChallenger(min_advantage=-1.0, max_drawdown=0.01)
    champion = framework.evaluate("champion", transitions, lambda _: 1)
    challenger = framework.evaluate("challenger", transitions, lambda _: 1)
    decision = framework.decide(champion, challenger)
    assert not decision.approved


def test_degenerate_challenger_is_never_promoted():
    """A challenger backed by too few supported transitions must be rejected even if
    its (coincidental) metrics look attractive — no magic -1.0 drawdown sentinel."""

    def build(n):
        return [
            LoggedTransition(np.array([1.0]), 1, 0.01, np.array([1.0]), False, 1.0, i)
            for i in range(n)
        ]

    framework = ConservativeChampionChallenger(
        min_supported_transitions=20, min_advantage=-10.0
    )
    # Champion: plenty of supported steps with a small positive edge.
    champion = framework.evaluate("champion", build(50), lambda _: 1)
    # Challenger: only 5 supported steps — not enough evidence to promote.
    challenger = framework.evaluate("challenger", build(5), lambda _: 1)
    decision = framework.decide(champion, challenger)
    assert not decision.approved
    assert not np.isfinite(challenger.cumulative_return)


def test_rl_dataset_next_state_respects_reward_horizon():
    """next_state must reflect the state AFTER reward_horizon bars, not the immediate
    next row — prevents one-bar look-ahead leaking the next row into training."""

    from options_agent.training.pipelines import build_offline_rl_dataset

    rows = [
        {
            "asof_ns": i,
            "available_at_ns": i,
            "value": float(i),
            "action": 1,
            "reward": 0.1,
            "behavior_probability": 0.5,
        }
        for i in range(10)
    ]
    result = build_offline_rl_dataset(
        rows, "fixture", 7, ("value",), lambda _: 1, reward_horizon=2
    )
    transitions = result.transitions
    # Transition i observes the state 2 bars later (no look-ahead into row i+1).
    assert transitions[0].next_state[0] == 2.0
    assert transitions[3].next_state[0] == 5.0
    # Row 7 is train[7], outcome index 9 -> exists (last train row). Row 8+ are
    # validation, which is excluded - so transitions end at train index 7.
    # The final horizon rows within train are terminal (self-loop, done=True).
    assert transitions[7].done and transitions[7].next_state[0] == 7.0
