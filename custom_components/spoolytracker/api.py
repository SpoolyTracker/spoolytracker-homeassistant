"""Client HTTP asynchrone pour l'API publique SpoolyTracker.

Couche fine et facilement adaptable : toutes les URL viennent de `const.py`,
les réponses `{ "data": ... }` sont déballées, et les erreurs sont converties en
exceptions typées consommables par le reste de l'intégration.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientResponseError

from .const import (
    API_BASE_PATH,
    DEFAULT_TIMEOUT,
    EP_ANALYTICS_CONSUMPTION,
    EP_ANALYTICS_STOCK,
    EP_CONSUMPTION,
    EP_FILAMENT,
    EP_FILAMENT_STOCK,
    EP_FILAMENTS,
)

_LOGGER = logging.getLogger(__name__)


class SpoolyTrackerError(Exception):
    """Erreur de base de l'API SpoolyTracker."""


class SpoolyTrackerConnectionError(SpoolyTrackerError):
    """Problème réseau : hôte injoignable, timeout, DNS, TLS…"""


class SpoolyTrackerAuthError(SpoolyTrackerError):
    """Token invalide ou permissions (scope) insuffisantes — HTTP 401/403."""


class SpoolyTrackerApiError(SpoolyTrackerError):
    """Réponse HTTP non-2xx autre qu'une erreur d'authentification."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


class SpoolyTrackerApiClient:
    """Client asynchrone minimal pour l'API publique SpoolyTracker."""

    def __init__(
        self,
        base_url: str,
        token: str,
        session: aiohttp.ClientSession,
        *,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        # On normalise pour éviter les doubles slashs et un /public-api/v1 en trop.
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._session = session
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    # -- Construction d'URL / requêtes -----------------------------------------

    def _url(self, resource: str) -> str:
        return f"{self._base_url}{API_BASE_PATH}{resource}"

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/json",
        }

    async def _request(
        self,
        method: str,
        resource: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> Any:
        """Exécute une requête et renvoie le contenu déballé de `data`."""
        url = self._url(resource)
        try:
            async with self._session.request(
                method,
                url,
                headers=self._headers,
                json=json,
                timeout=self._timeout,
            ) as resp:
                # 401/403 = token/scope -> exception d'auth pour déclencher le reauth.
                if resp.status in (401, 403):
                    text = await _safe_text(resp)
                    _LOGGER.debug("Auth refusée (%s) sur %s", resp.status, url)
                    raise SpoolyTrackerAuthError(text or "Authentification refusée")

                if resp.status >= 400:
                    text = await _safe_text(resp)
                    raise SpoolyTrackerApiError(resp.status, text or resp.reason or "")

                if resp.status == 204 or resp.content_length == 0:
                    return None

                payload = await resp.json(content_type=None)
        except ClientResponseError as err:  # pragma: no cover - filet de sécurité
            raise SpoolyTrackerApiError(err.status, err.message) from err
        except (ClientError, asyncio.TimeoutError) as err:
            raise SpoolyTrackerConnectionError(str(err) or type(err).__name__) from err

        # L'API enveloppe tout dans {"data": ...}. On tolère l'absence d'enveloppe.
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # -- API publique -----------------------------------------------------------

    async def validate_token(self) -> bool:
        """Valide le token en appelant un endpoint léger (analytics/stock).

        Lève SpoolyTrackerAuthError si le token est invalide/insuffisant, ou
        SpoolyTrackerConnectionError si l'instance est injoignable.
        """
        await self._request("GET", EP_ANALYTICS_STOCK)
        return True

    async def get_spools(self) -> list[dict[str, Any]]:
        """Liste des bobines (filaments)."""
        data = await self._request("GET", EP_FILAMENTS)
        return data if isinstance(data, list) else []

    async def get_spool(self, spool_id: int | str) -> dict[str, Any]:
        """Détail d'une bobine."""
        return await self._request(
            "GET", EP_FILAMENT.format(spool_id=spool_id)
        )

    async def get_stats(self) -> dict[str, Any]:
        """Statistiques de stock agrégées (analytics/stock)."""
        data = await self._request("GET", EP_ANALYTICS_STOCK)
        return data if isinstance(data, dict) else {}

    async def get_consumption_history(self) -> list[dict[str, Any]]:
        """Historique des consommations."""
        data = await self._request("GET", EP_CONSUMPTION)
        return data if isinstance(data, list) else []

    async def get_consumption_analytics(self) -> dict[str, Any]:
        """Agrégats de consommation."""
        data = await self._request("GET", EP_ANALYTICS_CONSUMPTION)
        return data if isinstance(data, dict) else {}

    async def log_consumption(
        self,
        spool_id: int | str,
        grams_used: float,
        *,
        notes: str | None = None,
        external_job_id: str | None = None,
        consumption_type: str = "PRINT",
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Enregistre une consommation sur une bobine.

        Le corps réellement accepté par l'API est
        `{filamentId, amount, type, notes, externalJobId, date, ...}`.
        `extra` permet d'ajouter des champs additionnels (compat future) sans
        toucher au client.
        """
        body: dict[str, Any] = {
            "filamentId": int(spool_id),
            "amount": float(grams_used),
            "type": consumption_type,
        }
        if notes:
            body["notes"] = notes
        if external_job_id:
            body["externalJobId"] = external_job_id
        if extra:
            body.update(extra)

        return await self._request("POST", EP_CONSUMPTION, json=body)

    async def update_stock(
        self, spool_id: int | str, weight_remaining: float
    ) -> dict[str, Any]:
        """Met à jour le poids restant d'une bobine (PATCH stock)."""
        return await self._request(
            "PATCH",
            EP_FILAMENT_STOCK.format(spool_id=spool_id),
            json={"weightRemaining": float(weight_remaining)},
        )

    # TODO(API SpoolyTracker) : get_projects() — endpoint public projets absent.
    # async def get_projects(self) -> list[dict[str, Any]]:
    #     data = await self._request("GET", EP_PROJECTS)
    #     return data if isinstance(data, list) else []


async def _safe_text(resp: aiohttp.ClientResponse) -> str:
    """Lit le corps d'erreur sans jamais lever."""
    try:
        return (await resp.text())[:300]
    except Exception:  # pragma: no cover - défensif
        return ""
