"""World Catalogue of Opiliones (ChecklistBank dataset 2256), archivé.

Retiré du registre actif (voir organon.modules.bootstrap). Le jeu
n'expose aucun lien ni identifiant propre à la source, et wcolite.com
n'a pas de page publique par taxon déductible : aucune citation
vérifiable sur Wikipédia, donc ni bioref ni classification. Ne
s'importe plus (`ChecklistBankModule` exige une URL de page du site
source) ; à ressortir seulement si la source publie de telles pages.
"""

from organon.core.models import RankName
from organon.core.registry import ModuleMeta, register_module
from organon.modules.checklistbank import ChecklistBankModule


class WcoModule(ChecklistBankModule):
    """World Catalogue of Opiliones module."""

    meta = ModuleMeta(
        id="wco",
        can_classify=True,
        can_render_external_link=True,
        domains=["arachnide"],
        priority=990,
    )
    dataset_id = "2256"  # alias "WCO", DOI 10.48580/d4pt, resynced from TaxonWorks
    label = "WCO"
    site_name = "World Catalogue of Opiliones"
    # The dataset is Opiliones only and its classification stops at
    # "order".
    fixed_chain = (
        RankName(name="Arachnida", rank="classe"),
        RankName(name="Arthropoda", rank="embranchement"),
    )


register_module(WcoModule)
