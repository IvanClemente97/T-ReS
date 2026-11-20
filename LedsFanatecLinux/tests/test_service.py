import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from leds_fanatec_linux.commands import send_test_command
from leds_fanatec_linux.models import default_profile
from leds_fanatec_linux.patterns import FLAG_ZONES, RPM_ZONES
from leds_fanatec_linux.profiles import ProfileStore
from leds_fanatec_linux.service import FanatecService
from leds_fanatec_linux.telemetry import parse_rivals_snapshot


def telemetry(*, speed=0, rpm=9000, max_rpm=10000):
    return parse_rivals_snapshot(
        {
            "version": 4,
            "player_telemetry": {
                "rpm": rpm,
                "max_rpm": max_rpm,
                "speed_kmh": speed,
                "gear": 1,
                "throttle": 0,
                "brake": 0,
                "is_in_pit_lane": False,
                "pit_limiter_on": False,
                "flags": 0,
            },
        },
        "Fanatec Rivals bridge",
        1.0,
    )


class FakeController:
    def __init__(self):
        self.frame = None
        self.speed = None

    def write_frame(self, frame):
        self.frame = frame

    def write_speed(self, speed):
        self.speed = speed


class ServiceTests(unittest.TestCase):
    def _service(self, directory):
        root = Path(directory)
        store = ProfileStore(root / "profiles")
        store.ensure_default()
        return FanatecService(
            store=store,
            state_path=root / "status.json",
            command_path=root / "command.json",
        )

    def test_edit_lock_allows_stationary_paused_car_and_rejects_motion_or_unknown_speed(self):
        self.assertFalse(FanatecService._is_edit_locked(telemetry(speed=0)))
        self.assertFalse(FanatecService._is_edit_locked(telemetry(speed=1)))
        self.assertTrue(FanatecService._is_edit_locked(telemetry(speed=1.1)))
        self.assertTrue(
            FanatecService._is_edit_locked(telemetry(speed=None))
        )
        self.assertFalse(FanatecService._is_edit_locked(None))

    def test_tests_work_without_telemetry_and_are_rejected_while_moving(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.controller = FakeController()
            send_test_command("test_rpm_max", path=service.command_path)
            service._accept_test_command(None)
            self.assertEqual(service._active_test["action"], "test_rpm_max")

        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            service.controller = FakeController()
            send_test_command("test_flag", "yellow", path=service.command_path)
            service._accept_test_command(telemetry(speed=25))
            self.assertIsNone(service._active_test)
            self.assertIn("rechazada", service._last_error)

    def test_flag_led_test_renders_without_simulator_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            controller = FakeController()
            service.controller = controller
            send_test_command("test_flag", "double_yellow", path=service.command_path)
            service._accept_test_command(None)
            service._active_test["started_at"] = time.monotonic() - 0.1
            self.assertTrue(
                service._render_active_test(service.store.load_active(), None)
            )
            self.assertIsNone(controller.speed)
            self.assertEqual(
                set(controller.frame[zone] for zone in FLAG_ZONES),
                {(255, 255, 0), (0, 0, 0)},
            )

    def test_active_profile_changes_are_deferred_until_the_car_is_stationary(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            original = service.store.load_active()
            next_profile = default_profile("Perfil nuevo")
            service.store.save(next_profile)
            service.store.activate(next_profile.profile_id)
            service._applied_profile = original

            during_motion = service._profile_for_telemetry(telemetry(speed=25))
            self.assertEqual(during_motion.profile_id, original.profile_id)
            while_stopped = service._profile_for_telemetry(telemetry(speed=0))
            self.assertEqual(while_stopped.profile_id, next_profile.profile_id)

    def test_service_uses_only_telemetry_max_rpm_and_active_profile_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self._service(directory)
            profile = service.store.load_active()
            controller = FakeController()
            service.controller = controller
            service._render(telemetry(max_rpm=None), profile)
            self.assertEqual(
                {controller.frame[zone] for zone in RPM_ZONES},
                {(0, 0, 0)},
            )
            with patch("leds_fanatec_linux.service.time.monotonic", return_value=0):
                service._render(telemetry(rpm=10000, max_rpm=10000), profile)
            self.assertEqual(
                {controller.frame[zone] for zone in RPM_ZONES},
                {(128, 0, 255)},
            )
            self.assertEqual(set(controller.frame).intersection(FLAG_ZONES), set(FLAG_ZONES))


if __name__ == "__main__":
    unittest.main()
