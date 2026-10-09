"""Unit tests for export_data.py (stdlib unittest; no new dependency).

    python visualisation/scripts/test_export_data.py -v
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import export_data as ex  # noqa: E402

FIXTURES = ex.REPO_ROOT / "out" / "fixtures"


def _reject_constant(name):
    raise ValueError(f"non-strict JSON constant {name}")


class ExportDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = ex.Config()

    def test_fallback_without_dev2_tables(self):
        """Only C1/C2 present: provisional receivers, toe pending, no fake numbers."""
        with tempfile.TemporaryDirectory() as tmp:
            for name in (ex.contracts_data.C1_FILE, ex.contracts_data.C2_FILE):
                shutil.copy(FIXTURES / name, Path(tmp) / name)
            payload = ex.build_payload(Path(tmp), self.cfg)
        self.assertEqual(payload["status"], {"receivers": "provisional", "toe": "pending",
                                             "offense": "pending", "instead": "provisional"})
        self.assertTrue(payload["sources"]["routes"].startswith("features.build_route_features("))
        self.assertEqual(payload["offense"], [])
        self.assertTrue(payload["receivers"])
        for row in payload["receivers"]:
            self.assertIsNone(row["toe"])
            self.assertIsNone(row["x_targets"])
            self.assertIsNone(row["toe_per_100_routes"])
            self.assertFalse(row["meets_minimum"])  # fixtures have < 40 routes per receiver
        self.assertTrue(any("pending" in n for n in payload["notes"]))
        ex.check_payload(payload)

    def test_c4_c5a_c6_passthrough(self):
        """C3-C6 present: values pass through unchanged; coverage-family splits dropped."""
        payload = ex.build_payload(FIXTURES, self.cfg, fixtures=True)
        self.assertEqual(payload["status"], {"receivers": "c4", "toe": "available",
                                             "offense": "available", "instead": "c6"})
        self.assertEqual(payload["sources"]["receivers"], "out/fixtures/c4_receiver_toe.parquet")
        self.assertEqual(payload["sources"]["offense"], "out/fixtures/c5a_offense.parquet")
        self.assertEqual(payload["sources"]["instead"], "out/fixtures/c6_instead.parquet")
        self.assertTrue(payload["fixtures"])
        self.assertEqual({r["split"] for r in payload["receivers"]} - set(ex.SPLITS), set())

        c4 = ex.pd.read_parquet(FIXTURES / ex.cm.C4_FILE)
        self.assertIn("Cover-3", set(c4["split"]))
        expected = c4[c4["split"].isin(ex.SPLITS)].set_index(["nflId", "split"])["toe"]
        self.assertEqual(len(payload["receivers"]), len(expected))
        for row in payload["receivers"]:
            self.assertAlmostEqual(row["toe"], expected[(row["nflId"], row["split"])], places=4)
        c5a = ex.pd.read_parquet(FIXTURES / ex.cm.C5A_FILE)
        self.assertEqual(len(payload["offense"]), len(c5a))
        c6 = ex.pd.read_parquet(FIXTURES / ex.cm.C6_FILE)
        self.assertEqual(payload["counts"]["ignored_open_events"], len(c6))
        ex.check_payload(payload)

    def test_write_strict_json(self):
        payload = ex.build_payload(FIXTURES, self.cfg, fixtures=True)
        payload["receivers"][0]["toe_per_100_routes"] = ex._clean(float("nan"))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "dashboard.json"
            size = ex.write_payload(payload, out)
            text = out.read_text()
            self.assertEqual(size, len(text.encode("utf-8")))
            self.assertLess(size, ex.MAX_BYTES)
            data = json.loads(text, parse_constant=_reject_constant)
            self.assertIsNone(data["receivers"][0]["toe_per_100_routes"])
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["dashboard.json"])

    def test_check_payload_rejects_bad_rows(self):
        payload = ex.build_payload(FIXTURES, self.cfg, fixtures=True)
        bad = copy.deepcopy(payload)
        bad["receivers"][0]["targets"] = bad["receivers"][0]["routes"] + 1
        with self.assertRaises(AssertionError):
            ex.check_payload(bad)
        bad = copy.deepcopy(payload)
        bad["status"]["toe"] = "pending"
        with self.assertRaises(AssertionError):
            ex.check_payload(bad)


if __name__ == "__main__":
    unittest.main()
