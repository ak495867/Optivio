import numpy as np

from options_agent.models.optivio_hybrid import KronosStyleTokenizer, OptivioHybridModel
from options_agent.validation.evolutionary import (
    EvolutionConfig,
    OptivioEvolutionaryOptimizer,
)


def make_data():
    rng = np.random.default_rng(3)
    x = rng.normal(size=(24, 3, 8, 6))
    y = {
        name: rng.normal(size=(24, 3))
        for name in ("direction", "expected_move", "volatility", "liquidity")
    }
    return x, y


def test_hybrid_model_fits_and_predicts_options_heads():
    x, y = make_data()
    model = OptivioHybridModel(feature_dim=6, hidden_dim=8).fit(x, y)
    out = model.predict(x[:4])
    assert out.direction.shape == (4, 3)
    assert np.all(out.volatility >= 1e-6)
    assert np.all((out.liquidity >= 0) & (out.liquidity <= 1))


def test_tokenizer_cannot_transform_before_fit():
    tok = KronosStyleTokenizer()
    try:
        tok.transform(np.zeros((1, 2, 3)))
        assert False
    except RuntimeError:
        pass


def test_evolution_is_reproducible_and_bounded():
    cfg = EvolutionConfig(population=12, generations=5, elite=2, seed=9)

    def objective(v):
        return -float(np.sum((v - 0.25) ** 2))

    a = OptivioEvolutionaryOptimizer(np.zeros(3), np.ones(3), cfg).fit(objective)
    b = OptivioEvolutionaryOptimizer(np.zeros(3), np.ones(3), cfg).fit(objective)
    assert np.all(a.values >= 0) and np.all(a.values <= 1)
    assert np.allclose(a.values, b.values)
