"""Async local client for AC units that speak the TFIAC UDP/XML protocol."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from time import time
from typing import Any
from xml.etree import ElementTree

from .const import DEFAULT_PORT

SHORT_WAIT = 2
STATUS_MESSAGE = (
    '<msg msgid="SyncStatusReq" type="Control" seq="{seq}">'
    "<SyncStatusReq></SyncStatusReq>"
    "</msg>"
)
SET_MESSAGE = (
    '<msg msgid="SetMessage" type="Control" seq="{seq}">'
    "<SetMessage>{message}</SetMessage>"
    "</msg>"
)


def c_to_f(value: float) -> float:
    """Convert Celsius to Fahrenheit."""
    return (value * 9 / 5) + 32


def f_to_c(value: float) -> float:
    """Convert Fahrenheit to Celsius."""
    return (value - 32) * 5 / 9


def normalize_unit(value: str) -> str:
    """Normalize a unit configuration value."""
    upper = value.upper()
    if upper not in {"C", "F"}:
        raise ValueError(f"Unsupported temperature unit: {value}")
    return upper


def convert_temperature(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a temperature between C and F."""
    from_unit = normalize_unit(from_unit)
    to_unit = normalize_unit(to_unit)
    if from_unit == to_unit:
        return value
    return c_to_f(value) if from_unit == "C" else f_to_c(value)


def _format_temperature(value: float) -> str:
    """Format a temperature for the device payload."""
    if abs(value - round(value)) < 0.01:
        return str(int(round(value)))
    return f"{value:.1f}"


def _wind_flags_to_swing(horizontal: str, vertical: str) -> str:
    """Map protocol wind direction flags to a swing mode name."""
    h_on = horizontal == "on"
    v_on = vertical == "on"
    if h_on and v_on:
        return "Both"
    if h_on:
        return "Horizontal"
    if v_on:
        return "Vertical"
    return "Off"


def _swing_to_flags(mode: str) -> tuple[str, str]:
    """Map a swing mode name to protocol wind direction flags."""
    return {
        "Off": ("off", "off"),
        "Vertical": ("off", "on"),
        "Horizontal": ("on", "off"),
        "Both": ("on", "on"),
    }[mode]


@dataclass(slots=True)
class TfiacStatus:
    """Parsed device state."""

    device_name: str
    is_on: bool
    base_mode: str
    target_temp: float
    current_temp: float | None
    fan_mode: str
    swing_mode: str
    raw: dict[str, str]

    @classmethod
    def from_xml(cls, xml_payload: bytes | str) -> "TfiacStatus":
        """Parse a status response."""
        root = ElementTree.fromstring(xml_payload)
        status_node = root.find("statusUpdateMsg")
        if status_node is None:
            raise ValueError("Missing statusUpdateMsg in device response")

        values: dict[str, str] = {}
        for child in status_node:
            if child.tag:
                values[child.tag] = child.text or ""

        return cls.from_values(values)

    @classmethod
    def from_values(cls, values: Mapping[str, str]) -> "TfiacStatus":
        """Build a status object from protocol field values."""
        current = values.get("IndoorTemp")
        return cls(
            device_name=values.get("DeviceName", "TFIAC AC"),
            is_on=values.get("TurnOn", "").lower() == "on",
            base_mode=values.get("BaseMode", "selfFeel"),
            target_temp=float(values["SetTemp"]),
            current_temp=float(current) if current not in (None, "") else None,
            fan_mode=values.get("WindSpeed", "Auto"),
            swing_mode=_wind_flags_to_swing(
                values.get("WindDirection_H", "off"),
                values.get("WindDirection_V", "off"),
            ),
            raw=dict(values),
        )


class TfiacClient:
    """Local UDP client for TFIAC devices."""

    def __init__(
        self,
        host: str,
        *,
        port: int = DEFAULT_PORT,
        timeout: float = 5.0,
        min_update_interval: float = SHORT_WAIT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.min_update_interval = min_update_interval
        self._status: TfiacStatus | None = None
        self._last_update = 0.0

    @property
    def status(self) -> TfiacStatus | None:
        """Return the cached device status."""
        return self._status

    @property
    def seq(self) -> str:
        """Build a protocol sequence value."""
        return str(int(time() * 1000))[-7:]

    async def _send(self, message: str, host: str | None = None) -> bytes:
        """Send a UDP message and wait for a single reply."""
        target_host = host or self.host
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            await loop.sock_sendto(sock, message.encode(), (target_host, self.port))
            data, _ = await asyncio.wait_for(
                loop.sock_recvfrom(sock, 4096), self.timeout
            )
            return data
        finally:
            sock.close()

    async def async_update(self, *, force: bool = False) -> TfiacStatus:
        """Fetch the latest device status."""
        if (
            not force
            and self._status is not None
            and time() - self._last_update < self.min_update_interval
        ):
            return self._status

        response = await self._send(STATUS_MESSAGE.format(seq=self.seq))
        self._status = TfiacStatus.from_xml(response)
        self._last_update = time()
        return self._status

    async def async_set_state(
        self,
        *,
        power: bool | None = None,
        hvac_mode: str | None = None,
        target_temp: float | None = None,
        fan_mode: str | None = None,
        swing_mode: str | None = None,
        refresh_before: bool = False,
        refresh_after: bool = False,
    ) -> TfiacStatus:
        """Update the state by sending a full SetMessage payload."""
        status = await self.async_update(force=refresh_before)
        raw = dict(status.raw)

        raw["TurnOn"] = "on" if (power if power is not None else status.is_on) else "off"
        raw["BaseMode"] = hvac_mode or status.base_mode
        raw["SetTemp"] = _format_temperature(
            status.target_temp if target_temp is None else target_temp
        )
        raw["WindSpeed"] = fan_mode or status.fan_mode

        swing = swing_mode or status.swing_mode
        horizontal, vertical = _swing_to_flags(swing)
        raw["WindDirection_H"] = horizontal
        raw["WindDirection_V"] = vertical

        payload = (
            f"<TurnOn>{raw['TurnOn']}</TurnOn>"
            f"<BaseMode>{raw['BaseMode']}</BaseMode>"
            f"<SetTemp>{raw['SetTemp']}</SetTemp>"
            f"<WindSpeed>{raw['WindSpeed']}</WindSpeed>"
            f"<WindDirection_H>{raw['WindDirection_H']}</WindDirection_H>"
            f"<WindDirection_V>{raw['WindDirection_V']}</WindDirection_V>"
        )

        await self._send(SET_MESSAGE.format(seq=self.seq, message=payload))
        self._status = TfiacStatus.from_values(raw)
        self._last_update = time()

        if refresh_after:
            return await self.async_update(force=True)

        return self._status

    async def async_turn_off(self) -> TfiacStatus:
        """Turn the AC off."""
        return await self.async_set_state(power=False)

    async def async_turn_on(self) -> TfiacStatus:
        """Turn the AC on, preserving the last known operating mode."""
        status = await self.async_update()
        return await self.async_set_state(
            power=True,
            hvac_mode=status.base_mode or "selfFeel",
        )

    @staticmethod
    async def async_discover(
        *,
        port: int = DEFAULT_PORT,
        timeout: float = 3.0,
        broadcast_host: str = "255.255.255.255",
    ) -> list[dict[str, Any]]:
        """Broadcast a status query and collect all replies."""
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        responses: list[dict[str, Any]] = []
        seen_hosts: set[str] = set()
        message = STATUS_MESSAGE.format(seq=str(int(time() * 1000))[-7:]).encode()

        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            await loop.sock_sendto(sock, message, (broadcast_host, port))

            deadline = loop.time() + timeout
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                try:
                    data, (host, reply_port) = await asyncio.wait_for(
                        loop.sock_recvfrom(sock, 4096),
                        remaining,
                    )
                except TimeoutError:
                    break

                if host in seen_hosts:
                    continue
                seen_hosts.add(host)

                try:
                    status = TfiacStatus.from_xml(data)
                except Exception:
                    continue

                responses.append(
                    {
                        "host": host,
                        "port": reply_port,
                        "device_name": status.device_name,
                        "base_mode": status.base_mode,
                        "is_on": status.is_on,
                        "current_temp": status.current_temp,
                        "target_temp": status.target_temp,
                    }
                )
        finally:
            sock.close()

        return responses
