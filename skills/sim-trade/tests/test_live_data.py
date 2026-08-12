from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from simtrade_core.market_data import EastMoneyQuoteProvider


@unittest.skipUnless(os.environ.get("SIMTRADE_LIVE_TEST") == "1", "set SIMTRADE_LIVE_TEST=1 for read-only provider test")
class LiveDataTest(unittest.TestCase):
    def test_live_quote_has_strict_schema(self) -> None:
        snapshot = EastMoneyQuoteProvider().get_quote("600519")
        self.assertEqual([], snapshot.schema_issues(), snapshot.as_dict())


if __name__ == "__main__":
    unittest.main()
