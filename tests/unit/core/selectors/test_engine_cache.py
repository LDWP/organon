"""load_ruleset (organon/core/selectors/engine.py) doit garder les rulesets en cache : le YAML
n'est lu/reparse qu'une fois par fichier, pas à chaque appel."""

from pathlib import Path

import organon.core.selectors.engine as engine_module


def test_load_ruleset_reads_disk_only_once_per_name(monkeypatch):
    engine_module.load_ruleset.cache_clear()
    original_open = Path.open
    opened: list[str] = []

    def counting_open(self, *args, **kwargs):
        opened.append(self.name)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    first = engine_module.load_ruleset("categories")
    engine_module.load_ruleset("categories")
    engine_module.load_ruleset("categories")

    assert len(opened) == 1, f"disque lu {len(opened)} fois, attendu 1 (mis en cache)"
    assert first is not None
