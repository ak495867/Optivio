from pathlib import Path

import pytest

from options_agent.models.research_models import HiveAdapter


def _write(module_file: Path, source: str) -> Path:
    module_file.parent.mkdir(parents=True, exist_ok=True)
    module_file.write_text(source, encoding="utf-8")
    return module_file


def test_hive_load_rejects_absolute_path():
    with pytest.raises(ValueError, match="bare filename"):
        HiveAdapter().load(str(Path("C:/Windows/evil.py")))


def test_hive_load_rejects_traversal(tmp_path: Path, monkeypatch):
    import options_agent.models.research_models as rm

    monkeypatch.setattr(rm, "_HIVE_MODULE_DIR", tmp_path)
    _write(tmp_path / "evil.py", "raise RuntimeError('RCE')\n")
    with pytest.raises(ValueError, match="bare filename"):
        HiveAdapter().load("../evil.py")


def test_hive_load_requires_provenance_marker(tmp_path: Path, monkeypatch):
    import options_agent.models.research_models as rm

    monkeypatch.setattr(rm, "_HIVE_MODULE_DIR", tmp_path)
    _write(tmp_path / "model.py", "x = 1\n")
    with pytest.raises(ValueError, match="provenance marker"):
        HiveAdapter().load("model.py")


def test_hive_load_valid_module(tmp_path: Path, monkeypatch):
    import options_agent.models.research_models as rm

    monkeypatch.setattr(rm, "_HIVE_MODULE_DIR", tmp_path)
    _write(tmp_path / "model.py", "# optivio-hive-model\nMAGIC = 42\n")

    adapter = HiveAdapter().load("model.py")
    assert adapter.model.MAGIC == 42
