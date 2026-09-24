"""Commons image selection.

Cross the taxon's Commons category with the quality and featured
distinctions of each file, filter by permissive license, then flag those
already used by Wikidata (P18), before proposing anything.

The taxobox rendering (`sections.render_taxobox`) leaves the image field
as a comment (`<!-- insérez une image -->`): a selection rewrites
nothing server-side; the frontend replaces that comment in the already
generated wikitext (see `web-app/src/App.jsx`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from urllib.parse import quote

from organon.modules.commons_images.adapter import CommonsImagesAdapter

# Accepted licenses: CC BY-SA 4.0 or more permissive (CC0, public
# domain), as slugs returned by extmetadata.License ("cc-by-sa-4.0",
# "cc0", "pd"). Any other value (CC BY alone, CC BY-SA before 4.0, fair
# use, no license) is excluded: better to suggest nothing than a
# doubtful image.
ALLOWED_LICENSES = {"cc0", "pd", "cc-by-sa-4.0"}

# Commons distinctions (extmetadata.Assessments) making a file a notable
# image (Quality images, Featured pictures).
_NOTABLE_ASSESSMENTS = {"quality", "featured"}

# A gallery of more than a few thumbnails no longer helps the decision;
# the rest stays reachable through the link to the full category.
_MAX_SUGGESTIONS = 12


@dataclass
class ImageSuggestion:
    """A suggested image with its license and distinctions."""

    file_name: str
    thumb_url: str
    page_url: str
    license_code: str
    license_label: str
    assessments: list[str]
    is_wikidata_image: bool = False


@dataclass
class ImageSearchResult:
    """Suggestions for a taxon, with the category and search URLs."""

    taxon: str
    category_title: str
    search_url: str
    # None if the taxon's Commons category has no member file (nothing
    # to show): the frontend then falls back on `search_url`.
    category_url: str | None = None
    suggestions: list[ImageSuggestion] = field(default_factory=list)


def _license_compatible(extmetadata: dict) -> tuple[str, str] | None:
    """Return (code, label) if the license is allowed, else None."""
    license_code = (extmetadata.get("License", {}).get("value") or "").strip().lower()
    if license_code not in ALLOWED_LICENSES:
        return None
    license_label = extmetadata.get("LicenseShortName", {}).get("value") or license_code
    return license_code, license_label


def _assessments(extmetadata: dict) -> list[str]:
    """Return the Commons distinctions of a file."""
    raw = extmetadata.get("Assessments", {}).get("value") or ""
    return [a for a in raw.split("|") if a]


async def find_images(taxon: str, adapter: CommonsImagesAdapter) -> ImageSearchResult:
    """Return the image suggestions for a taxon.

    Entry point of `GET /api/v1/commons-images` (see
    `organon.api.routes.commons_images`).
    """
    category_title = f"Category:{taxon}"
    search_url = f"https://commons.wikimedia.org/w/index.php?search={quote(taxon)}"

    files = await adapter.category_files(category_title)
    result = ImageSearchResult(taxon=taxon, category_title=category_title, search_url=search_url)
    if not files:
        return result

    category_slug = quote(category_title.replace(" ", "_"))
    result.category_url = f"https://commons.wikimedia.org/wiki/{category_slug}"

    infos, wikidata_file = await asyncio.gather(
        adapter.imageinfo(files), adapter.wikidata_image(taxon)
    )

    suggestions = []
    for title, info in infos.items():
        extmetadata = info.get("extmetadata") or {}
        assessments = _assessments(extmetadata)
        if not (_NOTABLE_ASSESSMENTS & set(assessments)):
            continue
        license = _license_compatible(extmetadata)
        if license is None:
            continue
        license_code, license_label = license
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
