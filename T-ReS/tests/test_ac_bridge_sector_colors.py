import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


BRIDGE_PATH = (
    Path(__file__).parents[1] / "integrations" / "assetto_corsa" / "TReS.py"
)


def load_bridge():
    fake_ac = types.ModuleType("ac")
    fake_ac.log = lambda _message: None
    fake_acsys = types.ModuleType("acsys")
    fake_acsys.CS = types.SimpleNamespace()
    fake_shared_memory = types.ModuleType("t_res_ac_shared_memory")
    fake_shared_memory.ACSharedMemoryReader = object
    with patch.dict(sys.modules, {
        "ac": fake_ac,
        "acsys": fake_acsys,
        "t_res_ac_shared_memory": fake_shared_memory,
    }):
        spec = importlib.util.spec_from_file_location("t_res_test_bridge", BRIDGE_PATH)
        bridge = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bridge)
    return bridge


class BridgeSectorColorTests(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()
        self.bridge._last_lap = None
        self.bridge._last_sector = None
        self.bridge._last_track_key = None
        self.bridge._personal_best_sectors = [None] * 16
        self.bridge._sector_colors = [None] * 16

    def sample(self, lap, sector, last_sector_ms):
        player = {
            "completed_laps": lap,
            "current_sector_index": sector,
            "last_sector_time_ms": last_sector_ms,
        }
        self.bridge._update_sector_colors(player, ("monza", None))
        return player["sector_colors"]

    def test_completed_sectors_use_player_personal_best_and_reset_each_lap(self):
        self.sample(0, 0, None)
        self.assertEqual(self.sample(0, 1, 30000)[0], "green")
        self.assertEqual(self.sample(0, 2, 31000)[1], "green")
        self.assertEqual(self.sample(1, 0, 32000), [None] * 16)
        self.assertEqual(self.sample(1, 1, 29000)[0], "green")
        self.assertEqual(self.sample(1, 2, 31500)[1], "yellow")

    def test_sector_status_does_not_claim_session_purple_without_a_reference(self):
        self.sample(0, 0, None)
        colors = self.sample(0, 1, 28000)

        self.assertNotIn("purple", colors)

    def test_best_lap_and_race_finished_use_the_game_api_values(self):
        values = {
            (0, "BestLap"): 92345,
            (0, "RaceFinished"): 1,
            (1, "BestLap"): 0,
            (1, "RaceFinished"): 0,
        }
        self.bridge._car_value = lambda car_id, name: values[(car_id, name)]

        self.assertEqual(
            self.bridge._best_lap_time_ms(0, {"best_lap_time_ms": 95000}), 92345
        )
        self.assertEqual(
            self.bridge._best_lap_time_ms(1, {"best_lap_time_ms": 95000}), None
        )
        self.assertIs(self.bridge._race_finished(0), True)
        self.assertIs(self.bridge._race_finished(1), False)

    def test_best_lap_falls_back_to_shared_memory_for_player_only(self):
        self.bridge._car_value = lambda _car_id, _name: None

        self.assertEqual(
            self.bridge._best_lap_time_ms(0, {"best_lap_time_ms": 93000}), 93000
        )
        self.assertIsNone(self.bridge._best_lap_time_ms(1, {"best_lap_time_ms": 93000}))

    def test_reads_assetto_corsa_metadata_with_literal_newlines_in_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ui_car.json"
            path.write_text('{"name":"Ferrari\nSF15-T"}', encoding="utf-8")

            metadata = self.bridge._read_json(str(path))

        self.assertEqual(metadata["name"], "Ferrari\nSF15-T")

    def test_preserves_lmp_subclasses_for_separate_leaderboards(self):
        self.assertEqual(
            self.bridge._vehicle_category({"tags": ["#LMP1"]}), "LMP1"
        )
        self.assertEqual(
            self.bridge._vehicle_category({"tags": ["#LMP2"]}), "LMP2"
        )


if __name__ == "__main__":
    unittest.main()
