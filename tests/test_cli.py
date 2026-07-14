"""Tests for the TFIAC command-line interface."""

import unittest

from custom_components.tfiac_local.cli import build_parser


class CliParserTest(unittest.TestCase):
    """Test CLI argument parsing."""

    def test_binary_option_names_and_raw_aliases(self) -> None:
        parser = build_parser()

        friendly = parser.parse_args(
            ["set", "--host", "192.0.2.1", "--beep", "off", "--eco", "on"]
        )
        raw = parser.parse_args(
            [
                "set",
                "--host",
                "192.0.2.1",
                "--BeepEnable",
                "off",
                "--Opt_ECO",
                "on",
            ]
        )

        self.assertEqual(friendly.beep, raw.beep)
        self.assertEqual(friendly.beep, "off")
        self.assertEqual(friendly.eco, raw.eco)
        self.assertEqual(friendly.eco, "on")

    def test_sleep_option(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["set", "--host", "192.0.2.1", "--sleep", "on"]
        )
        raw = parser.parse_args(
            ["set", "--host", "192.0.2.1", "--Opt_sleepMode", "on"]
        )

        self.assertEqual(args.sleep, "on")
        self.assertEqual(args.sleep, raw.sleep)


if __name__ == "__main__":
    unittest.main()
