"""Config flow SpoolyTracker : configuration UI, options et réauthentification."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    SpoolyTrackerApiClient,
    SpoolyTrackerAuthError,
    SpoolyTrackerConnectionError,
)
from .const import (
    CONF_API_TOKEN,
    CONF_BASE_URL,
    CONF_NAME,
    DEFAULT_ALLOW_AMBIGUOUS,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STRATEGY_METADATA,
    DEFAULT_STRATEGY_SELECT,
    DEFAULT_STRATEGY_SLOT,
    DOMAIN,
    OPT_ALLOW_AMBIGUOUS,
    OPT_SCAN_INTERVAL,
    OPT_STRATEGY_METADATA,
    OPT_STRATEGY_SELECT,
    OPT_STRATEGY_SLOT,
)

_LOGGER = logging.getLogger(__name__)


def _normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    # Retire un éventuel /public-api/v1 collé par l'utilisateur.
    if url.endswith("/public-api/v1"):
        url = url[: -len("/public-api/v1")]
    return url


async def _validate(hass, base_url: str, token: str) -> str | None:
    """Retourne None si OK, sinon un code d'erreur pour le formulaire."""
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return "invalid_url"

    session = async_get_clientsession(hass)
    client = SpoolyTrackerApiClient(base_url, token, session)
    try:
        await client.validate_token()
    except SpoolyTrackerAuthError:
        return "invalid_auth"
    except SpoolyTrackerConnectionError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001 - on ne casse jamais le flow
        _LOGGER.exception("Erreur inattendue pendant la validation SpoolyTracker")
        return "unknown"
    return None


class SpoolyTrackerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Gère l'ajout d'une instance SpoolyTracker."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_url = _normalize_base_url(user_input[CONF_BASE_URL])
            token = user_input[CONF_API_TOKEN].strip()

            await self.async_set_unique_id(base_url.lower())
            self._abort_if_unique_id_configured()

            error = await _validate(self.hass, base_url, token)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title=user_input.get(CONF_NAME) or DEFAULT_NAME,
                    data={
                        CONF_BASE_URL: base_url,
                        CONF_API_TOKEN: token,
                        CONF_NAME: user_input.get(CONF_NAME) or DEFAULT_NAME,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_BASE_URL): str,
                vol.Required(CONF_API_TOKEN): str,
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    # -- Réauthentification -----------------------------------------------------

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        base_url = self._reauth_entry.data[CONF_BASE_URL]

        if user_input is not None:
            token = user_input[CONF_API_TOKEN].strip()
            error = await _validate(self.hass, base_url, token)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={**self._reauth_entry.data, CONF_API_TOKEN: token},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_API_TOKEN): str}),
            errors=errors,
            description_placeholders={"base_url": base_url},
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> "SpoolyTrackerOptionsFlow":
        return SpoolyTrackerOptionsFlow()


class SpoolyTrackerOptionsFlow(OptionsFlow):
    """Options : intervalle de scan, stratégies de matching, ambiguïté."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    OPT_SCAN_INTERVAL,
                    default=opts.get(OPT_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=3600)),
                vol.Optional(
                    OPT_STRATEGY_SLOT,
                    default=opts.get(OPT_STRATEGY_SLOT, DEFAULT_STRATEGY_SLOT),
                ): bool,
                vol.Optional(
                    OPT_STRATEGY_SELECT,
                    default=opts.get(OPT_STRATEGY_SELECT, DEFAULT_STRATEGY_SELECT),
                ): bool,
                vol.Optional(
                    OPT_STRATEGY_METADATA,
                    default=opts.get(OPT_STRATEGY_METADATA, DEFAULT_STRATEGY_METADATA),
                ): bool,
                vol.Optional(
                    OPT_ALLOW_AMBIGUOUS,
                    default=opts.get(OPT_ALLOW_AMBIGUOUS, DEFAULT_ALLOW_AMBIGUOUS),
                ): bool,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
