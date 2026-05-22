from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import EvchargoApi, EvchargoApiError, EvchargoAuthError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS
from .value import first_value

_LOGGER = logging.getLogger(__name__)


class EvchargoDataUpdateCoordinator(DataUpdateCoordinator[dict]):
    """Coordinate Evchargo API updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: EvchargoApi,
        charger_id: str,
        *,
        update_interval_seconds: int = DEFAULT_SCAN_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Evchargo {charger_id}",
            config_entry=config_entry,
            update_interval=timedelta(seconds=update_interval_seconds),
            always_update=True,
        )
        self.api = api
        self.charger_id = charger_id
        self._charging_enabled: bool | None = None

    @property
    def charging_enabled(self) -> bool | None:
        """Return the Home Assistant charging control state."""
        return self._charging_enabled

    async def async_set_charging_enabled(self, enabled: bool) -> None:
        """Execute charging control and keep HA state in sync with the charger."""
        previous_state = self._charging_enabled
        self._charging_enabled = enabled
        try:
            if enabled:
                await self.api.async_start_charging(self.charger_id)
            else:
                await self.api.async_stop_charging(self.charger_id)
        except EvchargoApiError:
            self._charging_enabled = previous_state
            raise

        await self.async_refresh()

    async def _async_update_data(self) -> dict:
        try:
            data = await self.api.async_get_overview(self.charger_id)
            await self._async_reconcile_charging_state(data)
            return data
        except EvchargoAuthError as err:
            raise ConfigEntryAuthFailed from err
        except EvchargoApiError as err:
            raise UpdateFailed(f"Error communicating with Evchargo API: {err}") from err

    async def _async_reconcile_charging_state(self, data: dict[str, Any]) -> None:
        """Reset stale HA charging state once charging is no longer active."""
        actual_state = _coerce_bool(
            first_value(
                data,
                "detail.cpInCharging",
                "detail.isCharging",
                "detail.charging",
                "detail.inCharging",
            )
        )

        if self._charging_enabled is None:
            self._charging_enabled = actual_state
            return

        if actual_state is True and self._charging_enabled is False:
            self._charging_enabled = True
            return

        if self._charging_enabled and actual_state is False:
            _LOGGER.info(
                "Resetting Home Assistant charging state because the charger no longer reports active charging"
            )
            self._charging_enabled = False
            try:
                await self.api.async_stop_charging(self.charger_id)
            except EvchargoApiError:
                _LOGGER.warning(
                    "Failed to clear stale Evchargo charging state after charging stopped",
                    exc_info=True,
                )


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    return None
