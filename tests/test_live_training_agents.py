import numpy as np

from options_agent.orchestration.agent_hub import IndependentAgentHub
from options_agent.training.pipelines import build_offline_rl_dataset, train_hmm


def _rows() -> list[dict[str, object]]:
    return [
        {"asof_ns": i, "available_at_ns": i, "value": float(i) / 10, "action": i % 2, "reward": 0.1 * i, "behavior_probability": 0.5}
        for i in range(8)
    ]


def test_hmm_pipeline_splits_by_availability():
    result = train_hmm(_rows(), "value", "fixture", 5)
    assert result.train_rows == 6
    assert result.validation_rows == 2
    assert result.manifest.row_count == 8


def test_offline_rl_pipeline_keeps_validation_out_of_transitions():
    result = build_offline_rl_dataset(_rows(), "fixture", 5, ("value",), lambda _: 0)
    assert result.train_rows == 6
    assert len(result.transitions) == 6


def test_independent_agents_isolate_failures():
    def good(_: object):
        return None

    def bad(_: object):
        raise RuntimeError("boom")

    hub = IndependentAgentHub({"good": good, "bad": bad}, workers=2)
    results = hub.infer(np.asarray([1.0]))
    hub.close()
    assert [item.agent_id for item in results] == ["bad", "good"]
    assert results[0].error == "RuntimeError"
    assert results[1].error is None
