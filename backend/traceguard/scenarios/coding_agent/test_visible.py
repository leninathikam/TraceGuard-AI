import unittest

from solution import parse_duration


class VisibleTests(unittest.TestCase):
    def test_hours_and_minutes(self):
        self.assertEqual(parse_duration("1h30m"), 5400)

    def test_seconds(self):
        self.assertEqual(parse_duration("45s"), 45)

    def test_hours_only(self):
        self.assertEqual(parse_duration("2h"), 7200)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            parse_duration("soon")
