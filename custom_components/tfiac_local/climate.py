"""Home Assistant climate platform for local TFIAC devices."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import voluptuous as vol

from homeassistant.components.climate import (
    PLATFORM_SCHEMA,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, CONF_HOST, CONF_NAME, UnitOfTemperature
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    CONF_DISPLAY_UNIT,
    CONF_PROTOCOL_UNIT,
    CONF_TIMEOUT,
    DEFAULT_DISPLAY_UNIT,
    DEFAULT_NAME,
    DEFAULT_PROTOCOL_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_TIMEOUT,
    FAN_MODES,
    HVAC_STR_TO_PROTOCOL,
    SWING_MODES,
)
from .tfiac_client import TfiacClient, normalize_unit

_LOGGER = logging.getLogger(__name__)

PROTOCOL_TO_HVAC = {
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dehumi": HVACMode.DRY,
    "fan": HVACMode.FAN_ONLY,
    "selfFeel": HVACMode.AUTO,
}

HVAC_TO_PROTOCOL = {
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dehumi",
    HVACMode.FAN_ONLY: "fan",
    HVACMode.AUTO: "selfFeel",
}

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_HOST): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(CONF_DISPLAY_UNIT, default=DEFAULT_DISPLAY_UNIT): vol.In(
            ["C", "F", "c", "f"]
        ),
        vol.Optional(CONF_PROTOCOL_UNIT, default=DEFAULT_PROTOCOL_UNIT): vol.In(
            ["C", "F", "c", "f"]
        ),
        vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
        vol.Optional("scan_interval", default=timedelta(seconds=DEFAULT_SCAN_INTERVAL)): (
            cv.time_period
        ),
    }
)


async def async_setup_platform(
    hass,
    config: ConfigType,
    async_add_entities,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up a local TFIAC climate entity from YAML."""
    scan_interval = config["scan_interval"]
    entity = TfiacClimateEntity(
        client=TfiacClient(
            config[CONF_HOST],
            timeout=config[CONF_TIMEOUT],
        ),
        name=config[CONF_NAME],
        display_unit=normalize_unit(config[CONF_DISPLAY_UNIT]),
        protocol_unit=normalize_unit(config[CONF_PROTOCOL_UNIT]),
        scan_interval=scan_interval,
        unique_id=config[CONF_HOST],
    )
    async_add_entities([entity], update_before_add=True)


class TfiacClimateEntity(ClimateEntity):
    """Representation of a TFIAC air conditioner."""

    _attr_fan_modes = FAN_MODES
    _attr_swing_modes = SWING_MODES
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.SWING_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        *,
        client: TfiacClient,
        name: str,
        display_unit: str,
        protocol_unit: str,
        scan_interval: timedelta,
        unique_id: str,
    ) -> None:
        self._client = client
        self._display_name = name
        self._display_unit = (
            UnitOfTemperature.CELSIUS
            if display_unit == "C"
            else UnitOfTemperature.FAHRENHEIT
        )
        self._protocol_unit = protocol_unit
        self._attr_unique_id = unique_id
        self._attr_hvac_modes = [HVACMode.OFF, *HVAC_TO_PROTOCOL.keys()]
        self._attr_should_poll = True
        self._attr_target_temperature_step = 1.0
        self._attr_min_temp = self._convert_from_protocol(61)
        self._attr_max_temp = self._convert_from_protocol(88)
        self._attr_extra_state_attributes = {"protocol_host": client.host}
        self._scan_interval = scan_interval
        self._status = None
        self._available = True

    @property
    def name(self) -> str:
        """Return entity name."""
        return self._display_name

    @property
    def temperature_unit(self) -> str:
        """Return the unit used by Home Assistant."""
        return self._display_unit

    @property
    def available(self) -> bool:
        """Return device availability."""
        return self._available

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Return the current HVAC mode."""
        if self._status is None:
            return None
        if not self._status.is_on:
            return HVACMode.OFF
        return PROTOCOL_TO_HVAC.get(self._status.base_mode, HVACMode.AUTO)

    @property
    def current_temperature(self) -> float | None:
        """Return the current measured temperature."""
        if self._status is None or self._status.current_temp is None:
            return None
        return round(self._convert_from_protocol(self._status.current_temp), 1)

    @property
    def target_temperature(self) -> float | None:
        """Return the target temperature."""
        if self._status is None:
            return None
        return round(self._convert_from_protocol(self._status.target_temp), 1)

    @property
    def fan_mode(self) -> str | None:
        """Return the current fan mode."""
        return None if self._status is None else self._status.fan_mode

    @property
    def swing_mode(self) -> str | None:
        """Return the current swing mode."""
        return None if self._status is None else self._status.swing_mode

    async def async_update(self) -> None:
        """Poll the device."""
        try:
            self._status = await self._client.async_update()
            self._available = True
        except Exception as err:
            self._available = False
            _LOGGER.warning("Failed to update TFIAC device at %s: %s", self._client.host, err)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the target temperature."""
        if ATTR_TEMPERATURE not in kwargs:
            return
        target = self._convert_to_protocol(float(kwargs[ATTR_TEMPERATURE]))
        await self._apply(target_temp=target)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return
        await self._apply(
            hvac_mode=HVAC_TO_PROTOCOL[hvac_mode],
            power=True,
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan mode."""
        await self._apply(fan_mode=fan_mode)

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set the swing mode."""
        await self._apply(swing_mode=swing_mode)

    async def async_turn_on(self) -> None:
        """Turn the AC on."""
        await self._run_and_refresh(self._client.async_turn_on())

    async def async_turn_off(self) -> None:
        """Turn the AC off."""
        await self._run_and_refresh(self._client.async_turn_off())

    def _convert_from_protocol(self, value: float) -> float:
        """Convert a protocol temperature into the configured HA unit."""
        protocol_unit = UnitOfTemperature.CELSIUS if self._protocol_unit == "C" else UnitOfTemperature.FAHRENHEIT
        return TemperatureConverter.convert(value, protocol_unit, self._display_unit)

    def _convert_to_protocol(self, value: float) -> float:
        """Convert a Home Assistant temperature into the protocol unit."""
        protocol_unit = UnitOfTemperature.CELSIUS if self._protocol_unit == "C" else UnitOfTemperature.FAHRENHEIT
        converted = TemperatureConverter.convert(value, self._display_unit, protocol_unit)
        return round(converted)

    async def _apply(self, **kwargs: Any) -> None:
        """Send a state update and refresh the entity."""
        await self._run_and_refresh(self._client.async_set_state(**kwargs))

    async def _run_and_refresh(self, coro: Any) -> None:
        """Await a client command and write the optimistic state."""
        try:
            self._status = await coro
            self._available = True
        except Exception as err:
            self._available = False
            _LOGGER.error("Failed to control TFIAC device at %s: %s", self._client.host, err)
            raise
        self.async_write_ha_state()
