"""Configuration du mécanisme OAuth + compte bot dédié. Toutes les valeurs sensibles viennent de
l'environnement (service `envvars` Toolforge en production, jamais codées en dur), avec le
préfixe `ORGANON_`.

Distinct de `organon.core.config.GenerateOptions` : ce fichier couvre les secrets/paramètres de
déploiement de l'outil, pas les options de génération d'un article.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ORGANON_", extra="ignore")

    # OAuth 2.0 utilisateur (identification seule) — consumer public enregistré sur
    # meta.wikimedia.org, revue communautaire requise avant activation.
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_redirect_uri: str = ""
    oauth_authorize_url: str = "https://meta.wikimedia.org/w/rest.php/oauth2/authorize"
    oauth_token_url: str = "https://meta.wikimedia.org/w/rest.php/oauth2/access_token"
    oauth_profile_url: str = "https://meta.wikimedia.org/w/rest.php/oauth2/resource/profile"

    # Cookies signés (identifiants du flux + session utilisateur).
    session_secret_key: str = ""
    oauth_state_max_age_seconds: int = 600
    session_max_age_seconds: int = 28800  # 8h
    # Toolforge sert toujours en HTTPS ; à mettre à False uniquement pour du développement local
    # en http:// (jamais en production).
    cookie_secure: bool = True

    # Frontend à rejoindre après le callback OAuth (page d'accueil de l'outil en développement
    # par défaut, cf. organon/api/app.py pour l'origine CORS équivalente).
    frontend_post_login_url: str = "http://localhost:5173/"

    # Compte bot dédié (Bot Password) — jamais l'utilisateur qui déclenche l'action, toujours ce
    # compte technique séparé.
    bot_username: str = ""
    bot_password: str = ""
    wiki_api_url: str = "https://fr.wikipedia.org/w/api.php"
    user_agent: str = "Organon/0.1 (https://fr.wikipedia.org/wiki/Projet:Biologie/Taxobot)"

    # Page de permission — lecture fail-closed, cache TTL court. Le nom `.../Taxobot/user.json`
    # n'est pas un identifiant interne oublié : c'est un chemin de page wiki réel (sous l'espace
    # du projet, pas du logiciel), dont le nom définitif dépend d'une décision communautaire pas
    # encore prise — renommer cette chaîne isolément déciderait à la place de la communauté et
    # désynchroniserait ce champ de la même chaîne dans wiki_permissions.py et des tests.
    permission_page_title: str = "Wikipédia:Projet:Biologie/Taxobot/user.json"
    permission_cache_ttl_seconds: float = 300.0

    # Verrou explicite : reste à False tant que (a) le statut du bot n'a pas été tranché par la
    # communauté (question posée sur Discussion Projet:Biologie/Taxobot) et (b) la page de
    # permission n'est pas protégée en écriture par un administrateur frwiki. La partie
    # identification (OAuth seul, sans édition) fonctionne indépendamment de ce flag.
    bot_edit_enabled: bool = False

    # Correction Wikidata assistée (organon.modules.wikidata ne fait pour l'instant que lire et
    # diagnostiquer des écarts, jamais écrire) — contrairement au bot Taxobot ci-dessus, une
    # correction Wikidata doit être attribuée au compte de l'utilisateur lui-même (norme des
    # outils d'assistance comme QuickStatements, pas un compte bot séparé). Deux décisions
    # restent ouvertes avant toute implémentation d'écriture, volontairement non tranchées ici :
    # (1) enregistrer un consumer OAuth distinct de `oauth_client_id` ci-dessus, avec les droits
    # d'édition Wikibase (le consumer actuel n'a que le scope profil/identification) ; (2) le
    # mode de conservation du jeton d'accès entre le callback OAuth et l'action de correction —
    # `sign_session` ci-dessous ne fait que signer, jamais chiffrer, donc pas un stockage sûr
    # pour un jeton capable d'écrire sur Wikidata.
    wikidata_api_url: str = "https://www.wikidata.org/w/api.php"
    wikidata_edit_enabled: bool = False


_settings: AuthSettings | None = None


def get_auth_settings() -> AuthSettings:
    global _settings
    if _settings is None:
        _settings = AuthSettings()
    return _settings
