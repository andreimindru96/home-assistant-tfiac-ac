"""Home Assistant switch platform for TFIAC device options."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components.switch import PLATFORM_SCHEMA, SwitchEntity
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.exceptions import PlatformNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from .const import CONF_TIMEOUT, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL, DEFAULT_TIMEOUT
from .tfiac_client import (
    BINARY_OPTION_FIELDS,
    SLEEP_MODE_FIELD,
    TfiacClient,
    TfiacStatus,
)

_LOGGER = logging.getLogger(__name__)

OPTION_SWITCHES = {
    "Opt_display": ("Display", "mdi:led-on"),
    "Opt_ECO": ("Eco mode", "mdi:leaf"),
    "Opt_super": ("Turbo mode", "mdi:fan-plus"),
    "Opt_healthy": ("Health mode", "mdi:air-filter"),
    "Opt_antiMildew": ("Anti-mildew", "mdi:shield-check"),
    "CleannessEnable": ("Clean mode", "mdi:broom"),
    "BeepEnable": ("Beeper", "mdi:volume-high"),
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
    }
)


async def async_setup_platform(
    hass,
    config: ConfigType,
    async_add_entities,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up option switches for a local TFIAC device from YAML."""
    client = TfiacClient(config[CONF_HOST], timeout=config[CONF_TIMEOUT])
    try:
        status = await client.async_update(force=True)
    except Exception as err:
        raise PlatformNotReady(
            f"Unable to read TFIAC device at {client.host}: {err}"
        ) from err

    coordinator: DataUpdateCoordinator[TfiacStatus] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{config[CONF_NAME]} options",
        update_method=client.async_update,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )
    coordinator.async_set_updated_data(status)

    entities = [
        TfiacOptionSwitch(
            coordinator=coordinator,
            client=client,
            field=field,
            name=f"{config[CONF_NAME]} {label}",
            icon=icon,
        )
        for field, (label, icon) in OPTION_SWITCHES.items()
        if field in status.raw
    ]
    if SLEEP_MODE_FIELD in status.raw:
        entities.append(
            TfiacSleepModeSwitch(
                coordinator=coordinator,
                client=client,
                field=SLEEP_MODE_FIELD,
                name=f"{config[CONF_NAME]} Sleep mode",
                icon="mdi:weather-night",
            )
        )
    async_add_entities(entities)


class TfiacOptionSwitch(
    CoordinatorEntity[DataUpdateCoordinator[TfiacStatus]], SwitchEntity
):
    """Switch for a binary option reported by a TFIAC device."""

    def __init__(
        self,
        *,
        coordinator: DataUpdateCoordinator[TfiacStatus],
        client: TfiacClient,
        field: str,
        name: str,
        icon: str,
    ) -> None:
        if field not in BINARY_OPTION_FIELDS and field != SLEEP_MODE_FIELD:
            raise ValueError(f"Unsupported TFIAC option field: {field}")
        super().__init__(coordinator)
        self._client = client
        self._field = field
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{client.host}_{field}"
        self._attr_extra_state_attributes = {
            "protocol_field": field,
            "protocol_host": client.host,
        }

    @property
    def available(self) -> bool:
        """Return whether the device and this option are available."""
        return super().available and self._field in self.coordinator.data.raw

    @property
    def is_on(self) -> bool:
        """Return the current option state from coordinator memory."""
        return self.coordinator.data.raw.get(self._field) == "on"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the option."""
        await self._async_set_option("on")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the option."""
        await self._async_set_option("off")

    async def _async_set_option(self, value: str) -> None:
        """Send an option update and publish the optimistic device status."""
        status = await self._client.async_set_state(options={self._field: value})
        self.coordinator.async_set_updated_data(status)


class TfiacSleepModeSwitch(TfiacOptionSwitch):
    """Switch for the structured TFIAC sleep mode option."""

    @property
    def is_on(self) -> bool:
        """Return whether the structured sleep mode value is enabled."""
        value = self.coordinator.data.raw.get(self._field, "off")
        return value.split(":", 1)[0] != "off"

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable sleep mode."""
        await self._async_set_sleep_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable sleep mode."""
        await self._async_set_sleep_mode(False)

    async def _async_set_sleep_mode(self, enabled: bool) -> None:
        """Send a structured sleep mode update."""
        status = await self._client.async_set_sleep_mode(enabled)
        self.coordinator.async_set_updated_data(status)
