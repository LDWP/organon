"""Limiteur de débit partagé (par IP), pour protéger les routes coûteuses d'un afflux de trafic
(crawler ou abus). Module séparé de `api.app` pour que les routers de `api.routes.*` puissent
l'importer sans dépendance circulaire (`app.py` importe les routers, qui importeraient sinon
`app.py` en retour).

Backend mémoire du process (`Limiter` par défaut) : suffisant tant qu'Organon tourne en un seul
process Toolforge (voir `Procfile`) — pas de coordination inter-process à prévoir.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
