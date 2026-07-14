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


if __name__ == "__main__":
    unittest.main()
