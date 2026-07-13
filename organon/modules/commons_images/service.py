"""Logique de sélection d'images Commons : croise la catégorie Commons du taxon avec les
distinctions qualité/featured de chaque fichier, filtre par licence permissive, puis marque
celles déjà utilisées par Wikidata (P18) — avant de proposer quoi que ce soit à l'utilisateur.

Le rendu de la taxobox (`organon.core.rendering.sections.render_taxobox`) laisse volontairement
le champ image en commentaire (`<!-- insérez une image -->`) : une sélection ici ne réécrit rien
côté serveur, elle est appliquée par simple remplacement de ce commentaire dans le wikitexte déjà
généré, côté frontend (voir `web-app/App.jsx`) — inutile de relancer un rendu ou de faire
persister l'état d'une génération en cours côté API pour un choix aussi local."""

from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import quote

from organon.modules.commons_images.adapter import CommonsImagesAdapter

# Licences acceptées : CC BY-SA 4.0, ou plus permissif (CC0, domaine public). Slugs tels que
# renvoyés par extmetadata.License (ex. "cc-by-sa-4.0", "cc0", "pd" — vérifiés en direct sur
# l'API, voir organon.modules.commons_images.adapter). Toute autre valeur (CC BY seul, CC BY-SA
# antérieur à 4.0, fair-use, licence absente...) est exclue : mieux vaut ne rien suggérer qu'une
# image à la licence douteuse.
ALLOWED_LICENSES = {"cc0", "pd", "cc-by-sa-4.0"}

# Distinctions Commons (extmetadata.Assessments) qui font d'un fichier une image "remarquable"
# au sens de la consigne (Quality images / Featured pictures on Wikimedia Commons).
_NOTABLE_ASSESSMENTS = {"quality", "featured"}

# Une galerie de plus de quelques vignettes n'aide plus la décision ; les fichiers restants
# restent accessibles via le lien vers la catégorie complète.
_MAX_SUGGESTIONS = 12


@dataclass
class ImageSuggestion:
    file_name: str
    thumb_url: str
    page_url: str
    license_code: str
    license_label: str
    assessments: list[str]
    is_wikidata_image: bool = False


@dataclass
class ImageSearchResult:
    taxon: str
    category_title: str
    search_url: str
    category_url: str | None = None
    """None si la catégorie Commons du taxon n'a aucun fichier membre (rien à y montrer) —
    le frontend replie alors son invitation à parcourir Commons sur `search_url`."""
    suggestions: list[ImageSuggestion] = field(default_factory=list)


def _licence_compatible(extmetadata: dict) -> tuple[str, str] | None:
    license_code = (extmetadata.get("License", {}).get("value") or "").strip().lower()
    if license_code not in ALLOWED_LICENSES:
        return None
    license_label = extmetadata.get("LicenseShortName", {}).get("value") or license_code
    return license_code, license_label


def _assessments(extmetadata: dict) -> list[str]:
    raw = extmetadata.get("Assessments", {}).get("value") or ""
    return [a for a in raw.split("|") if a]


async def find_images(taxon: str, adapter: CommonsImagesAdapter) -> ImageSearchResult:
    """Point d'entrée de la route `GET /api/v1/commons-images` (voir
    `organon.api.routes.commons_images`)."""
    category_title = f"Category:{taxon}"
    search_url = f"https://commons.wikimedia.org/w/index.php?search={quote(taxon)}"

    files = await adapter.category_files(category_title)
    result = ImageSearchResult(taxon=taxon, category_title=category_title, search_url=search_url)
    if not files:
        return result

    category_slug = quote(category_title.replace(" ", "_"))
    result.category_url = f"https://commons.wikimedia.org/wiki/{category_slug}"

    infos = await adapter.imageinfo(files)
    wikidata_file = await adapter.wikidata_image(taxon)

    suggestions = []
    for title, info in infos.items():
        extmetadata = info.get("extmetadata") or {}
        assessments = _assessments(extmetadata)
        if not (_NOTABLE_ASSESSMENTS & set(assessments)):
            continue
        licence = _licence_compatible(extmetadata)
        if licence is None:
            continue
        license_code, license_label = licence
        file_name = title.removeprefix("File:")
        suggestions.append(
            ImageSuggestion(
                file_name=file_name,
                thumb_url=info.get("thumburl") or info.get("url", ""),
                page_url=info.get("descriptionurl", ""),
                license_code=license_code,
                license_label=license_label,
                assessments=assessments,
                is_wikidata_image=bool(wikidata_file) and wikidata_file == file_name,
            )
        )

    suggestions.sort(key=lambda s: s.file_name)
    result.suggestions = suggestions[:_MAX_SUGGESTIONS]
    return result
