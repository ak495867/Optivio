import numpy as np

from options_agent.execution.multileg import (
    Greeks,
    GreeksRiskGate,
    Leg,
    LegState,
    LifecycleEvent,
    strategy_state,
)
from options_agent.models.alternative_strategies import (
    GaussianHMM,
    PairsTradingModel,
    SurfaceArbitrageModel,
)
from options_agent.models.parallel_engine import ParallelSignalEngine


def test_parity_arbitrage_detects_edge():
    signal = SurfaceArbitrageModel(min_edge=0.01).put_call_parity(12, 8, 100, 100, 1)
    assert signal is not None and signal.kind == "put_call_parity"


def test_hmm_filters_probabilities():
    hmm = GaussianHMM(states=2, iterations=3).fit(
        np.r_[np.full(20, -0.1), np.full(20, 0.1)]
    )
    probs = hmm.filtered_probabilities(np.array([-0.1, 0.1]))
    assert probs.shape == (2, 2) and np.allclose(probs.sum(axis=1), 1)


def test_hmm_variance_is_per_state_not_summed():
    """The EM variance update must be a per-state element-wise weighted sum.
    A buggy (gamma.T @ squares).sum(axis=0) form sums every state's weighted
    contribution into each variance, inflating it by ~state count (4x for 4
    states). Fit on two clean, well-separated clusters and require each
    recovered variance to match that cluster's spread."""
    rng = np.random.default_rng(0)
    x = np.r_[rng.normal(-3, 1.0, 300), rng.normal(3, 1.0, 300)]
    hmm = GaussianHMM(states=2, iterations=20).fit(x)
    # Mixture recovered with clean separation; each state's variance ~ 1.0.
    assert np.allclose(sorted(hmm.variances), [1.0, 1.0], atol=0.15)
    assert float(hmm.variances.max()) < 2.5  # far below the old ~4x inflation


def test_pairs_model_signal():
    x = np.arange(20, dtype=float)
    y = 2 * x + np.r_[np.zeros(19), 5]
    model = PairsTradingModel(entry_z=1).fit(x, y)
    assert model.signal(x[-1], y[-1]) == -1


def test_parallel_engine_isolates_failure():
    engine = ParallelSignalEngine(
        {
            "ok": lambda _: (1.0, 0.8),
            "bad": lambda _: (_ for _ in ()).throw(RuntimeError()),
        },
        workers=2,
    )
    try:
        signals = engine.infer(None)
        assert len(signals) == 2 and any(s.error for s in signals)
    finally:
        engine.close()


def test_multileg_lifecycle_and_greeks_gate():
    leg = Leg("a", "A", 1, 2)
    leg.apply(LifecycleEvent.SUBMIT_ACK)
    leg.apply(LifecycleEvent.FILL, 1)
    assert (
        leg.state == LegState.PARTIALLY_FILLED
        and strategy_state([leg]) == "partially_filled"
    )
    ok, reason = GreeksRiskGate().approve(Greeks(), Greeks(delta=2000))
    assert not ok and "delta" in reason
