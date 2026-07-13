"""Client CLI d'Organon. Ne réimplémente **aucune** logique de génération : c'est un simple
client HTTP de l'API du site (locale en développement, ou le site déployé par défaut).
N'importe jamais `organon.core`/`organon.modules`.
"""

from __future__ import annotations

import json as jsonlib
import sys
from typing import Annotated

import httpx
import typer

DEFAULT_API_URL = "https://organon.toolforge.org/api/v1"

app = typer.Typer(add_completion=False, help="Génère un squelette d'article Wikipédia pour un taxon.")


@app.command()
def main(
    taxon: Annotated[str, typer.Argument(help="Nom scientifique du taxon")],
    api_url: Annotated[str, typer.Option(help="URL de base de l'API Organon")] = DEFAULT_API_URL,
    classification: Annotated[str, typer.Option(help="Module de classification à utiliser (vide = auto)")] = "",
    domaine: Annotated[str, typer.Option(help="Domaine du vivant (filtre les sources)")] = "*",
    force_regne: Annotated[str, typer.Option("--force-regne", help="Force le règne")] = "",
    force_rang: Annotated[str, typer.Option("--force-rang", help="Force le rang")] = "",
    auteurs: Annotated[str, typer.Option(help="Mode de traitement des auteurs : s, n ou n1")] = "n",
    liens_synonymes: Annotated[bool, typer.Option(help="Wikiliens autour des synonymes")] = True,
    liens_inf_sp: Annotated[bool, typer.Option(help="Wikiliens pour les taxons < espèce")] = False,
    suivre_synonymes: Annotated[bool, typer.Option(help="Suivre la cible d'un synonyme")] = True,
    trier_synonymes: Annotated[bool, typer.Option(help="Trier les synonymes alphabétiquement")] = True,
    inclure_invalides: Annotated[bool, typer.Option(help="Inclure les taxons invalides trouvés")] = False,
    juste_ext: Annotated[bool, typer.Option(help="Ne déterminer que les liens externes")] = False,
    selecteurs: Annotated[bool, typer.Option(help="Autoriser les règles ébauches/catégories/portails")] = True,
    plan: Annotated[bool, typer.Option(help="Générer un plan-type même sans information")] = False,
    article: Annotated[bool, typer.Option(help="Ne générer que le texte de l'article")] = False,
    seuil_colonnes: Annotated[int, typer.Option(help="Seuil de mise en colonnes des listes")] = 25,
    limite_listes: Annotated[int, typer.Option(help="Taille max des listes (<=0 = illimité)")] = -1,
    timeout: Annotated[float, typer.Option(help="Timeout par module (0 = aucun)")] = 0,
    off: Annotated[str, typer.Option(help="Modules à désactiver, séparés par des virgules")] = "",
    ua: Annotated[str, typer.Option(help="User-Agent personnalisé")] = "",
    marine_only: Annotated[bool, typer.Option(help="Limiter WoRMS aux taxons marins")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Sortie JSON brute plutôt que wikitexte")] = False,
    debug: Annotated[bool, typer.Option(help="Afficher les logs/avertissements de génération")] = False,
) -> None:
    payload = {
        "taxon": taxon,
        "classification": classification,
        "domaine": domaine,
        "force_regne": force_regne,
        "force_rang": force_rang,
        "auteurs": auteurs,
        "liens_synonymes": liens_synonymes,
        "liens_inf_sp": liens_inf_sp,
        "suivre_synonymes": suivre_synonymes,
        "trier_synonymes": trier_synonymes,
        "inclure_invalides": inclure_invalides,
        "juste_ext": juste_ext,
        "selecteurs": selecteurs,
        "plan": plan,
        "article": article,
        "seuil_colonnes": seuil_colonnes,
        "limite_listes": limite_listes,
        "timeout": timeout,
        "off": [m.strip() for m in off.split(",") if m.strip()],
        "ua": ua,
        "marine_only": marine_only,
    }

    try:
        resp = httpx.post(f"{api_url}/generate", json=payload, timeout=120.0)
    except httpx.HTTPError as exc:
        typer.echo(f"Erreur réseau : {exc}", err=True)
        raise typer.Exit(1) from exc

    if resp.status_code >= 400:
        detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith(
            "application/json"
        ) else resp.text
        typer.echo(f"Erreur ({resp.status_code}) : {detail}", err=True)
        raise typer.Exit(1)

    data = resp.json()

    if as_json:
        typer.echo(jsonlib.dumps(data, ensure_ascii=False, indent=2))
        return

    typer.echo(data["wikitext"])
    if data.get("external_links"):
        typer.echo("-----")
        for link in data["external_links"]:
            typer.echo(link["html"])
    if debug:
        typer.echo("-----", err=True)
        for line in data.get("logs", []):
            typer.echo(f"[log] {line}", err=True)
        for line in data.get("warnings", []):
            typer.echo(f"[warning] {line}", err=True)


if __name__ == "__main__":
    app()
