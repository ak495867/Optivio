from datetime import UTC, datetime

import numpy as np

from options_agent.validation.online_rl import (
    LiveGuardrails,
    OnlineChampionChallenger,
    OnlineOutcome,
    PolicyRuntime,
)


def test_online_challenger_stays_shadow_until_gate():
    t = datetime(2026, 1, 1, tzinfo=UTC)
    champion = PolicyRuntime("c1", lambda _: .1)
    controller = OnlineChampionChallenger(champion, LiveGuardrails(min_observations=2, min_advantage=.01))
    challenger = PolicyRuntime("c2", lambda _: .2)
    controller.load_challenger(challenger)
    assert controller.propose_action(np.array([1.]), challenger) == .2
    controller.record_outcome(OnlineOutcome("c2", t, t, .02, .2))
    assert not controller.evaluate_and_promote().approved
    controller.record_outcome(OnlineOutcome("c2", t, t, .02, .2))
    decision = controller.evaluate_and_promote()
    assert decision.approved and controller.champion.version == "c2"


def test_live_action_is_clipped():
    controller = OnlineChampionChallenger(PolicyRuntime("c1", lambda _: 9), LiveGuardrails(max_action_abs=.5))
    assert controller.propose_action(np.array([0.]), controller.champion) == .5
