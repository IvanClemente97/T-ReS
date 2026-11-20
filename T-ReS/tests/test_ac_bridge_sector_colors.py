import importlib.util
from pathlib import Path
import sys
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


if __name__ == "__main__":
    unittest.main()
