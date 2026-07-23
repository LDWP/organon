"""Point d'import unique qui enregistre tous les modules disponibles dans le registre (voir
organon.core.registry). Remplace le scan de répertoire `scandir("./modules")` de l'ancien
`cherche_modules()` : ici, ajouter un module au Phase 2+ signifie ajouter une ligne d'import
ici, explicite et visible dans les diffs — pas un fichier découvert « par magie » au démarrage.

Les modules sous `organon.modules._archive` ne sont volontairement pas importés ici : leur code
reste dans le dépôt mais ils ne s'enregistrent plus (voir le docstring de chacun pour le motif
du retrait)."""

from __future__ import annotations

from organon.modules.algaebase import module as _algaebase  # noqa: F401
from organon.modules.cites import module as _cites  # noqa: F401
from organon.modules.col import module as _col  # noqa: F401
from organon.modules.eflora import module as _eflora  # noqa: F401
from organon.modules.eol import module as _eol  # noqa: F401
from organon.modules.externe import module as _externe  # noqa: F401
from organon.modules.gbif import module as _gbif  # noqa: F401
from organon.modules.indexfungorum import module as _indexfungorum  # noqa: F401
from organon.modules.ipni import module as _ipni  # noqa: F401
from organon.modules.irmng import module as _irmng  # noqa: F401
from organon.modules.itis import module as _itis  # noqa: F401
from organon.modules.mnhn import module as _mnhn  # noqa: F401
from organon.modules.msw import module as _msw  # noqa: F401
from organon.modules.ncbi import module as _ncbi  # noqa: F401
from organon.modules.oepp import module as _oepp  # noqa: F401
from organon.modules.powo import module as _powo  # noqa: F401
from organon.modules.telametro import module as _telametro  # noqa: F401
from organon.modules.tpdb import module as _tpdb  # noqa: F401
from organon.modules.tropicos import module as _tropicos  # noqa: F401
from organon.modules.vascan import module as _vascan  # noqa: F401
from organon.modules.wrms import module as _wrms  # noqa: F401


def ensure_modules_registered() -> None:
    """No-op explicite : le simple fait d'importer ce module suffit (les modules
    s'enregistrent via le décorateur @register_module au moment de l'import), cette fonction
    existe pour donner un point d'appel explicite et lisible côté appelant."""
