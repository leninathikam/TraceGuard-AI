"""Held-out tests. They are never shown to the diagnosis model, so they catch repairs
that only special-case the visible tests."""

import unittest

from solution import parse_duration


class HiddenTests(unittest.TestCase):
    def test_all_units(self):
        self.assertEqual(parse_duration("1h5m10s"), 3910)

    def test_minutes_only(self):
        self.assertEqual(parse_duration("10m"), 600)

    def test_zero(self):
        self.assertEqual(parse_duration("0s"), 0)

    def test_empty_raises(self):
        with self.assertRaises(ValueError):
            parse_duration("")

    def test_unknown_unit_raises(self):
        with self.assertRaises(ValueError):
            parse_duration("5x")

    def test_trailing_garbage_raises(self):
        with self.assertRaises(ValueError):
            parse_duration("1h30mfoo")
