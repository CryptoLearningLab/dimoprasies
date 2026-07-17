from pathlib import Path
import unittest

from tender_radar.config import validate_repository_configs


class ConfigTests(unittest.TestCase):
    def test_repository_configs_validate(self) -> None:
        root = Path(__file__).resolve().parents[1]
        results = validate_repository_configs(root)
        self.assertTrue(results)
        failures = [result for result in results if not result.ok]
        self.assertEqual([], failures)
