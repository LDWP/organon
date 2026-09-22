"""_load (organon/core/rendering/authors.py) doit garder en cache les trois fichiers d'auteurs
(botanistes, procaryotes, zoologistes) simultanément, pas un seul à la fois."""

from pathlib import Path

import organon.core.rendering.authors as authors_module


def test_load_caches_all_three_author_files(monkeypatch):
    authors_module._load.cache_clear()
    original_open = Path.open
    opened: list[str] = []

    def counting_open(self, *args, **kwargs):
        opened.append(self.name)
        return original_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", counting_open)

    authors_module._load_botanists()
    authors_module._load_prokaryotes()
    authors_module._load_zoologists()
    authors_module._load_botanists()

    assert len(opened) == 3, f"disque lu {len(opened)} fois, attendu 3 (un par fichier distinct)"
