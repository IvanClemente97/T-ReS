import tempfile
from pathlib import Path
import unittest

from leds_fanatec_linux.hardware import FanatecController, FanatecDevice
from leds_fanatec_linux.patterns import FLAG_ZONES, RPM_ZONES


class HardwareTests(unittest.TestCase):
    def test_display_truncates_kmh_to_integer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zones = {}
            for name in (*RPM_ZONES, *FLAG_ZONES):
                zone = root / name
                zone.mkdir()
                (zone / "multi_intensity").write_text("0 0 0", encoding="ascii")
                zones[name] = zone
            display = root / "display"
            display.touch()
            device = FanatecDevice(
                name="test",
                hid_name="Fanatec test",
                sysfs_path=root,
                zones=zones,
                display=display,
            )
            controller = FanatecController(device)
            controller.write_speed(88.9)
            self.assertEqual(display.read_text(encoding="ascii").strip(), "88")
            controller.write_speed(None)
            self.assertEqual(display.read_text(encoding="ascii"), "\n")


if __name__ == "__main__":
    unittest.main()
