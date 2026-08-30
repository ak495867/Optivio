import numpy as np

from options_agent.models.optivio_hybrid import OptivioHybridModel
from options_agent.models.pipeline import OptivioSignalPipeline


def test_pipeline_produces_regime_scaled_portfolio_decision():
    rng = np.random.default_rng(11)
    x = rng.normal(size=(12, 2, 6, 4))
    y = {name: rng.normal(size=(12, 2)) for name in ("direction", "expected_move", "volatility", "liquidity")}
    model = OptivioHybridModel(feature_dim=4, hidden_dim=6).fit(x, y)
    decision = OptivioSignalPipeline(model).decide(x[:1], trend=.02, realized_volatility=.01)
    assert decision.regime == "trending_up"
    assert decision.target_weights.shape == (2,)
    assert np.all(np.abs(decision.target_weights) <= .20 + 1e-12)
