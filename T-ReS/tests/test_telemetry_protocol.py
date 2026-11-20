import json
from pathlib import Path
import tempfile
import time
import unittest

from t_res.adapters.assetto_corsa.source import read_snapshot
from t_res.domain.models import TelemetryValidationError, classify_sector, parse_snapshot
from t_res.dashboard.widgets import _pedal_percent


def snapshot_payload(**updates):
    payload = {
        "protocol_version": 1,
        "simulator": "assetto_corsa_2014",
        "published_at_unix_s": 1000.0,
        "track": "monza",
        "layout": None,
        "session_type": None,
        "lap_times_complete": False,
        "player": {
            "source": "assetto_corsa_shared_memory",
            "speed_kmh": 215.0,
            "throttle": 0.85,
            "brake": 0.0,
            "gear": 5,
            "rpm": 8000,
            "completed_laps": 3,
            "total_laps": 12,
            "track_position": 0.5,
            "current_lap_time_ms": 45000,
            "last_lap_time_ms": None,
            "best_lap_time_ms": None,
            "current_sector_index": 1,
            "last_sector_time_ms": None,
            "sector_colors": [None, None, None],
            "availability": {"speed_kmh": "available", "last_lap_time_ms": "unavailable"},
        },
        "cars": [
            {
                "car_id": 0,
                "source": "assetto_corsa_python_api",
                "is_player": True,
                "driver_name": "Driver",
                "car_name": "Car",
                "lap_count": 3,
                "official_position": 1,
                "realtime_position": 1,
                "best_lap_time_ms": None,
                "world_x": 12.5,
                "world_z": -6.0,
            }
        ],
    }
    payload.update(updates)
    return json.dumps(payload)


class TelemetryProtocolTests(unittest.TestCase):
    def test_reads_live_bridge_snapshot_with_shared_module_collision(self):
        payload = json.loads(snapshot_payload())
        payload["published_at_unix_s"] = time.time()
        payload["player"].pop("source")
        payload["player"]["physics_packet_id"] = 10
        payload["player"]["graphics_packet_id"] = 20
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            snapshot = read_snapshot(path)

        self.assertEqual(snapshot.player.source, "assetto_corsa_shared_memory")
        self.assertEqual(len(snapshot.cars), 1)

    def test_missing_source_without_shared_memory_evidence_is_rejected(self):
        payload = json.loads(snapshot_payload())
        payload["published_at_unix_s"] = time.time()
        payload["player"].pop("source")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(TelemetryValidationError, "source is unavailable"):
                read_snapshot(path)

    def test_missing_values_stay_unavailable_and_laps_use_real_counts(self):
        snapshot = parse_snapshot(snapshot_payload(), now=1000.5)

        self.assertEqual(snapshot.player.brake, 0.0)
        self.assertIsNone(snapshot.player.last_lap_time_ms)
        self.assertEqual(
            snapshot.player.availability["last_lap_time_ms"].value, "unavailable"
        )
        self.assertEqual(snapshot.laps_remaining, 9)
        self.assertIsNone(snapshot.fastest_lap_car_id)
        self.assertEqual(snapshot.sources, frozenset({
            "assetto_corsa_shared_memory", "assetto_corsa_python_api"
        }))

    def test_optional_car_metadata_is_validated_and_missing_metadata_stays_empty(self):
        payload = json.loads(snapshot_payload())
        payload["cars"][0].update({
            "track_position": 0.25,
            "speed_kmh": 140.0,
            "display_name": "Ferrari SF15-T",
            "finished": False,
            "brand": "Ferrari",
            "vehicle_class": "GT3",
            "team_name": "Scuderia Ferrari",
            "team_color": "#C8102E",
        })

        car = parse_snapshot(json.dumps(payload), now=1000.0).cars[0]
        self.assertEqual(car.track_position, 0.25)
        self.assertEqual(car.speed_kmh, 140.0)
        self.assertEqual(car.display_name, "Ferrari SF15-T")
        self.assertIs(car.finished, False)
        self.assertEqual(car.brand, "Ferrari")
        self.assertEqual(car.vehicle_class, "GT3")
        self.assertEqual(car.team_name, "Scuderia Ferrari")
        self.assertEqual(car.team_color, "#C8102E")

        del payload["cars"][0]["team_color"]
        self.assertIsNone(parse_snapshot(json.dumps(payload), now=1000.0).cars[0].team_color)

    def test_optional_display_name_and_finished_state_are_validated(self):
        payload = json.loads(snapshot_payload())
        payload["cars"][0]["finished"] = "finished"

        with self.assertRaisesRegex(TelemetryValidationError, "finished must be boolean"):
            parse_snapshot(json.dumps(payload), now=1000.0)

        payload["cars"][0]["finished"] = True
        car = parse_snapshot(json.dumps(payload), now=1000.0).cars[0]
        self.assertIs(car.finished, True)
        self.assertIsNone(car.display_name)

    def test_invalid_team_color_is_rejected(self):
        payload = json.loads(snapshot_payload())
        payload["cars"][0]["team_color"] = "red"

        with self.assertRaisesRegex(TelemetryValidationError, "#RRGGBB"):
            parse_snapshot(json.dumps(payload), now=1000.0)

    def test_common_parser_accepts_other_simulator_ids_but_adapter_can_pin_one(self):
        payload = json.loads(snapshot_payload())
        payload["simulator"] = "f1_25"
        serialized = json.dumps(payload)

        snapshot = parse_snapshot(serialized, now=1000.0)
        self.assertEqual(snapshot.simulator, "f1_25")
        self.assertEqual(
            parse_snapshot(
                serialized, now=1000.0, expected_simulator="f1_25"
            ).simulator,
            "f1_25",
        )
        with self.assertRaisesRegex(TelemetryValidationError, "selected simulator"):
            parse_snapshot(
                serialized, now=1000.0, expected_simulator="assetto_corsa_2014"
            )

    def test_timed_or_unknown_lap_session_does_not_show_remaining_laps(self):
        payload = json.loads(snapshot_payload())
        payload["player"]["total_laps"] = None

        self.assertIsNone(parse_snapshot(json.dumps(payload), now=1000.0).laps_remaining)

    def test_stale_snapshot_is_rejected(self):
        with self.assertRaisesRegex(TelemetryValidationError, "stale"):
            parse_snapshot(snapshot_payload(), now=1003.0)

    def test_invalid_pedal_and_map_signal_values_are_rejected(self):
        payload = json.loads(snapshot_payload())
        payload["player"]["throttle"] = 1.2
        with self.assertRaisesRegex(TelemetryValidationError, "above its valid range"):
            parse_snapshot(json.dumps(payload), now=1000.0)

        payload["player"]["throttle"] = 0.5
        payload["player"]["sector_colors"] = ["red"]
        with self.assertRaisesRegex(TelemetryValidationError, "not permitted"):
            parse_snapshot(json.dumps(payload), now=1000.0)

    def test_fastest_driver_requires_all_driver_times(self):
        payload = json.loads(snapshot_payload())
        payload["lap_times_complete"] = True
        payload["cars"][0]["best_lap_time_ms"] = 90000
        payload["cars"].append({
            "car_id": 1,
            "source": "assetto_corsa_python_api",
            "is_player": False,
            "driver_name": "Rival",
            "car_name": "Other car",
            "lap_count": 3,
            "official_position": 2,
            "realtime_position": 2,
            "best_lap_time_ms": 91000,
            "world_x": None,
            "world_z": None,
        })

        snapshot = parse_snapshot(json.dumps(payload), now=1000.0)
        self.assertEqual(snapshot.fastest_lap_car_id, 0)

        payload["cars"][1]["best_lap_time_ms"] = None
        with self.assertRaisesRegex(TelemetryValidationError, "every car"):
            parse_snapshot(json.dumps(payload), now=1000.0)

    def test_sector_color_requires_actual_timing_and_reference(self):
        self.assertIsNone(classify_sector(None, 30000, 29000))
        self.assertEqual(classify_sector(29000, 30000, 29000), "purple")
        self.assertEqual(classify_sector(29500, 30000, None), "green")
        self.assertEqual(classify_sector(30500, 30000, None), "yellow")

    def test_pedal_units_are_rendered_as_percent(self):
        self.assertEqual(_pedal_percent(0.85), 85.0)
        self.assertEqual(_pedal_percent(0.0), 0.0)
        self.assertIsNone(_pedal_percent(None))


if __name__ == "__main__":
    unittest.main()
