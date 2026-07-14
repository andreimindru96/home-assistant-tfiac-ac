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

        async def send(
            message: str, host: str | None = None, **kwargs: object
        ) -> bytes:
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

        async def send(
            message: str, host: str | None = None, **kwargs: object
        ) -> bytes:
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

        async def send(
            message: str, host: str | None = None, **kwargs: object
        ) -> bytes:
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

        async def send(
            message: str, host: str | None = None, **kwargs: object
        ) -> bytes:
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

        async def send(
            message: str, host: str | None = None, **kwargs: object
        ) -> bytes:
            messages.append(message)
            return b"<msg />"

        client._send = send  # type: ignore[method-assign]

        await client.async_set_sleep_mode(True)

        self.assertIn("<Opt_ECO>off</Opt_ECO>", messages[0])
        self.assertIn(
            "<Opt_sleepMode>sleepMode1:1:2:3:4:5:6:7:8:9:10</Opt_sleepMode>",
            messages[0],
        )

    async def test_status_request_retries_after_timeout(self) -> None:
        client = TfiacClient("192.0.2.1", retries=1, retry_delay=0)
        attempts = 0

        async def send_once(message: str, host: str | None = None) -> bytes:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise TimeoutError
            return b"reply"

        client._send_once = send_once  # type: ignore[method-assign]

        response = await client._send("status")

        self.assertEqual(response, b"reply")
        self.assertEqual(attempts, 2)

    async def test_set_command_is_not_retried(self) -> None:
        client = TfiacClient("192.0.2.1", retries=3, retry_delay=0)
        client._status = _status()
        client._last_update = time()
        attempts = 0

        async def send_once(message: str, host: str | None = None) -> bytes:
            nonlocal attempts
            attempts += 1
            raise TimeoutError

        client._send_once = send_once  # type: ignore[method-assign]

        with self.assertRaises(TimeoutError):
            await client.async_set_state(options={"BeepEnable": "off"})

        self.assertEqual(attempts, 1)


if __name__ == "__main__":
    unittest.main()
