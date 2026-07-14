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


if __name__ == "__main__":
    unittest.main()
