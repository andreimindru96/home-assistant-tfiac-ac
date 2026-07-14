"""CLI helper for local TFIAC devices."""

from __future__ import annotations

import argparse
import asyncio
import json

from .const import DEFAULT_RETRIES, HVAC_STR_TO_PROTOCOL
from .tfiac_client import TfiacClient, normalize_unit


CLI_OPTION_FIELDS = {
    "display": "Opt_display",
    "eco": "Opt_ECO",
    "super_mode": "Opt_super",
    "healthy": "Opt_healthy",
    "beep": "BeepEnable",
}


async def _run(args: argparse.Namespace) -> int:
    if args.command == "discover":
        devices = await TfiacClient.async_discover(timeout=args.timeout)
        print(json.dumps(devices, indent=2))
        return 0

    client = TfiacClient(
        args.host,
        timeout=args.timeout,
        retries=args.retries,
    )

    if args.command == "status":
        status = await client.async_update(force=True)
        print(
            json.dumps(
                {
                    "host": args.host,
                    "device_name": status.device_name,
                    "is_on": status.is_on,
                    "hvac_mode": status.base_mode,
                    "target_temp": status.target_temp,
                    "current_temp": status.current_temp,
                    "fan_mode": status.fan_mode,
                    "swing_mode": status.swing_mode,
                    "raw": status.raw,
                },
                indent=2,
            )
        )
        return 0

    protocol_temp = args.temperature
    if args.temperature is not None and args.protocol_unit and args.display_unit:
        display_unit = normalize_unit(args.display_unit)
        protocol_unit = normalize_unit(args.protocol_unit)
        if display_unit != protocol_unit:
            from .tfiac_client import convert_temperature

            protocol_temp = round(
                convert_temperature(args.temperature, display_unit, protocol_unit)
            )

    options = {
        field: value
        for argument, field in CLI_OPTION_FIELDS.items()
        if (value := getattr(args, argument)) is not None
    }

    status = await client.async_set_state(
        power={"on": True, "off": False}.get(args.power) if args.power else None,
        hvac_mode=HVAC_STR_TO_PROTOCOL.get(args.hvac) if args.hvac else None,
        target_temp=protocol_temp,
        fan_mode=args.fan,
        swing_mode=args.swing,
        options=options,
        sleep_mode={"on": True, "off": False}.get(args.sleep),
    )
    print(
        json.dumps(
            {
                "host": args.host,
                "device_name": status.device_name,
                "is_on": status.is_on,
                "hvac_mode": status.base_mode,
                "target_temp": status.target_temp,
                "current_temp": status.current_temp,
                "fan_mode": status.fan_mode,
                "swing_mode": status.swing_mode,
            },
            indent=2,
        )
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(description="Local controller for TFIAC AC units")
    subparsers = parser.add_subparsers(dest="command", required=True)

    discover = subparsers.add_parser("discover", help="Discover TFIAC devices")
    discover.add_argument("--timeout", type=float, default=3.0)

    status = subparsers.add_parser("status", help="Read current device state")
    status.add_argument("--host", required=True)
    status.add_argument("--timeout", type=float, default=5.0)
    status.add_argument("--retries", type=int, default=DEFAULT_RETRIES)

    set_cmd = subparsers.add_parser("set", help="Update the device state")
    set_cmd.add_argument("--host", required=True)
    set_cmd.add_argument("--timeout", type=float, default=5.0)
    set_cmd.add_argument("--retries", type=int, default=DEFAULT_RETRIES)
    set_cmd.add_argument("--power", choices=["on", "off"])
    set_cmd.add_argument("--hvac", choices=sorted(HVAC_STR_TO_PROTOCOL))
    set_cmd.add_argument("--temperature", type=float)
    set_cmd.add_argument("--fan", choices=["Auto", "Low", "Middle", "High"])
    set_cmd.add_argument("--swing", choices=["Off", "Vertical", "Horizontal", "Both"])
    set_cmd.add_argument("--display-unit", choices=["C", "F", "c", "f"], default="C")
    set_cmd.add_argument("--protocol-unit", choices=["C", "F", "c", "f"], default="F")
    set_cmd.add_argument("--display", "--Opt_display", choices=["on", "off"])
    set_cmd.add_argument("--eco", "--Opt_ECO", choices=["on", "off"])
    set_cmd.add_argument(
        "--super", "--Opt_super", dest="super_mode", choices=["on", "off"]
    )
    set_cmd.add_argument("--healthy", "--Opt_healthy", choices=["on", "off"])
    set_cmd.add_argument("--beep", "--BeepEnable", choices=["on", "off"])
    set_cmd.add_argument("--sleep", "--Opt_sleepMode", choices=["on", "off"])

    return parser


def main() -> int:
    """Run the CLI."""
    parser = build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
