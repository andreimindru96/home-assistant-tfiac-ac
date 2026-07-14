"""Tests for the local TFIAC client."""

import unittest
from time import time

from custom_components.tfiac_local.tfiac_client import TfiacClient, TfiacStatus


def _status() -> TfiacStatus:
    return TfiacStatus.from_values(
        {
            "DeviceName": "Test AC",
            "TurnOn": "on",
            "BaseMode": "cool",
            "SetTemp": "70",
            "WindSpeed": "Auto",
            "WindDirection_H": "off",
            "WindDirection_V": "on",
            "Opt_ECO": "off",
            "Opt_sleepMode": "off:1:2:3:4:5:6:7:8:9:10",
            "BeepEnable": "on",
        }
    )


class TfiacClientTest(unittest.IsolatedAsyncioTestCase):
    """Test state update payloads."""

    async def test_set_state_sends_and_caches_binary_options(self) -> None:
        client = TfiacClient("192.0.2.1")
        client._status = _status()
        client._last_update = time()
        messages: list[str] = []

        async def send(message: str, host: str | None = None) -> bytes:
            messages.append(message)
            return b"<msg />"

        client._send = send  # type: ignore[method-assign]

        status = await client.async_set_state(
            options={"BeepEnable": "off", "Opt_ECO": "on"}
        )

        self.assertIn("<BeepEnable>off</BeepEnable>", messages[0])
        self.assertIn("<Opt_ECO>on</Opt_ECO>", messages[0])
        self.assertEqual(status.raw["BeepEnable"], "off")
        self.assertEqual(status.raw["Opt_ECO"], "on")

    async def test_rejects_unsupported_options_before_network_access(self) -> None:
        client = TfiacClient("192.0.2.1")

        with self.assertRaisesRegex(ValueError, "Unsupported option field"):
            await client.async_set_state(options={"DeviceName": "changed"})

    async def test_rejects_non_binary_values(self) -> None:
        client = TfiacClient("192.0.2.1")

        with self.assertRaisesRegex(ValueError, "must be 'on' or 'off'"):
            await client.async_set_state(options={"BeepEnable": "disabled"})

    async def test_accepts_cleaning_options(self) -> None:
        client = TfiacClient("192.0.2.1")
        client._status = _status()
        client._last_update = time()
        messages: list[str] = []

        async def send(message: str, host: str | None = None) -> bytes:
            messages.append(message)
            return b"<msg />"

        client._send = send  # type: ignore[method-assign]

        await client.async_set_state(
            options={"CleannessEnable": "on", "Opt_antiMildew": "on"}
        )

        self.assertIn("<CleannessEnable>on</CleannessEnable>", messages[0])
        self.assertIn("<Opt_antiMildew>on</Opt_antiMildew>", messages[0])

    async def test_sleep_mode_preserves_schedule(self) -> None:
        client = TfiacClient("192.0.2.1")
        client._status = _status()
        client._last_update = time()
        messages: list[str] = []

        async def send(message: str, host: str | None = None) -> bytes:
            messages.append(message)
            return b"<msg />"

        client._send = send  # type: ignore[method-assign]

        status = await client.async_set_sleep_mode(True)

        expected = "sleepMode1:1:2:3:4:5:6:7:8:9:10"
        self.assertIn(f"<Opt_sleepMode>{expected}</Opt_sleepMode>", messages[0])
        self.assertEqual(status.raw["Opt_sleepMode"], expected)

    async def test_eco_mode_disables_sleep_mode(self) -> None:
        client = TfiacClient("192.0.2.1")
        client._status = _status()
        client._status.raw["Opt_sleepMode"] = "sleepMode1:0:0:0:0:0:0:0:0:0:0"
        client._last_update = time()
        messages: list[str] = []

        async def send(message: str, host: str | None = None) -> bytes:
            messages.append(message)
            return b"<msg />"

        client._send = send  # type: ignore[method-assign]

        await client.async_set_state(options={"Opt_ECO": "on"})

        self.assertIn("<Opt_ECO>on</Opt_ECO>", messages[0])
        self.assertIn(
            "<Opt_sleepMode>off:0:0:0:0:0:0:0:0:0:0</Opt_sleepMode>",
            messages[0],
        )

    async def test_sleep_mode_disables_eco_mode(self) -> None:
        client = TfiacClient("192.0.2.1")
        client._status = _status()
        client._status.raw["Opt_ECO"] = "on"
        client._last_update = time()
        messages: list[str] = []

        async def send(message: str, host: str | None = None) -> bytes:
            messages.append(message)
            return b"<msg />"

        client._send = send  # type: ignore[method-assign]

        await client.async_set_sleep_mode(True)

        self.assertIn("<Opt_ECO>off</Opt_ECO>", messages[0])
        self.assertIn(
            "<Opt_sleepMode>sleepMode1:1:2:3:4:5:6:7:8:9:10</Opt_sleepMode>",
            messages[0],
        )


if __name__ == "__main__":
    unittest.main()
