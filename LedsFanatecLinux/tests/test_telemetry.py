import json
import os
from pathlib import Path
import tempfile
import time
import unittest

from leds_fanatec_linux.telemetry import (
    AssettoCorsaTelemetryReader,
    parse_rivals_snapshot,
    parse_tres_snapshot,
)


class TelemetryTests(unittest.TestCase):
    def test_reads_real_shape_from_rivals_bridge(self):
        sample = parse_rivals_snapshot(
            {
                "version": 4,
                "player_telemetry": {
                    "rpm": 7050,
                    "max_rpm": 15000,
                    "speed_kmh": 142.6,
                    "gear": 4,
                    "throttle": 0.8,
                    "brake": 0.0,
                    "is_in_pit_lane": False,
                    "pit_limiter_on": False,
                    "flags": 2,
                },
            },
            "Fanatec Rivals bridge",
            time.monotonic(),
        )
        self.assertEqual(sample.rpm, 7050)
        self.assertEqual(sample.max_rpm, 15000)
        self.assertEqual(sample.gear, 4)
        self.assertEqual(sample.active_flags, frozenset({"yellow"}))
        self.assertTrue(sample.flags_available)

    def test_tres_feed_preserves_unavailable_rpm_limit_and_flags(self):
        sample = parse_tres_snapshot(
            {
                "protocol_version": 1,
                "simulator": "assetto_corsa_2014",
                "published_at_unix_s": time.time(),
                "player": {
                    "rpm": 5100,
                    "speed_kmh": 90.5,
                    "gear": 3,
                    "throttle": 0.4,
                    "brake": 0.1,
                },
            },
            "T-ReS bridge",
            time.monotonic(),
        )
        self.assertEqual(sample.rpm, 5100)
        self.assertIsNone(sample.max_rpm)
        self.assertFalse(sample.flags_available)
        self.assertEqual(sample.active_flags, frozenset())

    def test_reader_rejects_stale_snapshot_without_fabricating_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rivals.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 4,
                        "player_telemetry": {
                            "rpm": 6000,
                            "max_rpm": 12000,
                            "speed_kmh": 100,
                            "gear": 3,
                            "flags": 0,
                        },
                    }
                ),
                encoding="utf-8",
            )
            old = time.time() - 10
            os.utime(path, (old, old))
            reader = AssettoCorsaTelemetryReader(
                feeds=(("Fanatec Rivals bridge", path),)
            )
            self.assertIsNone(reader.read())
            self.assertIn("obsoleto", reader.last_error)

    def test_missing_flags_field_does_not_discard_real_rpm_data(self):
        sample = parse_rivals_snapshot(
            {
                "version": 4,
                "player_telemetry": {
                    "rpm": 5000,
                    "max_rpm": 11000,
                    "speed_kmh": 50,
                    "gear": 2,
                },
            },
            "Fanatec Rivals bridge",
            time.monotonic(),
        )
        self.assertEqual(sample.rpm, 5000)
        self.assertFalse(sample.flags_available)

    def test_fractional_redline_is_rejected_instead_of_truncated(self):
        with self.assertRaisesRegex(ValueError, "max_rpm debe ser un entero"):
            parse_rivals_snapshot(
                {
                    "version": 4,
                    "player_telemetry": {
                        "rpm": 6000,
                        "max_rpm": 12000.5,
                        "speed_kmh": 100,
                        "gear": 3,
                        "flags": 0,
                    },
                },
                "Fanatec Rivals bridge",
                time.monotonic(),
            )


if __name__ == "__main__":
    unittest.main()
