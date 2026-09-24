"""Systema Dipterorum (ChecklistBank dataset 1101), archivé.

Retiré du registre actif (voir organon.modules.bootstrap). Le jeu
n'expose aucun lien ni identifiant propre à la source, et diptera.org
n'a pas de page publique par taxon déductible : aucune citation
vérifiable sur Wikipédia, donc ni bioref ni classification. Ne
s'importe plus (`ChecklistBankModule` exige une URL de page du site
source) ; à ressortir seulement si la source publie de telles pages.
"""

from organon.core.models import RankName
from organon.core.registry import ModuleMeta, register_module
from organon.modules.checklistbank import ChecklistBankModule


class SystemaDipterorumModule(ChecklistBankModule):
    """Systema Dipterorum module."""

    meta = ModuleMeta(
        id="systema_dipterorum",
        can_classify=True,
        can_render_external_link=True,
        domains=["animal"],
    )
    dataset_id = "1101"  # alias "Systema Dipterorum", DOI 10.48580/d3bz, v7.2, via TaxonWorks
    label = "Systema Dipterorum"
    site_name = "Systema Dipterorum"
    # The dataset is Diptera only and its classification stops at
    # "order".
    fixed_chain = (
        RankName(name="Insecta", rank="classe"),
        RankName(name="Arthropoda", rank="embranchement"),
    )


register_module(SystemaDipterorumModule)
