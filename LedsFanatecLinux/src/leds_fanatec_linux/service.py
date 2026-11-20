"""Servicio de usuario para aplicar telemetría real a los LED Fanatec."""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import signal
import tempfile
import threading
import time

from .hardware import FanatecController, FanatecDiscovery, HardwareError
from .commands import COMMAND_PATH, read_test_command
from .patterns import FlagPattern, RpmPattern
from .profiles import ProfileStore
from .telemetry import AssettoCorsaTelemetryReader

LOG = logging.getLogger("leds_fanatec_linux")
POLL_INTERVAL = 1 / 35
HARDWARE_RETRY_INTERVAL = 2.0
STATUS_INTERVAL = 0.25
EDIT_SPEED_LIMIT_KMH = 1.0
TEST_DURATION = 3.0


class FanatecService:
    def __init__(
        self,
        *,
        reader: AssettoCorsaTelemetryReader | None = None,
        store: ProfileStore | None = None,
        discovery: FanatecDiscovery | None = None,
        state_path: Path | None = None,
        command_path: Path | None = None,
    ) -> None:
        self.reader = reader or AssettoCorsaTelemetryReader()
        self.store = store or ProfileStore()
        self.discovery = discovery or FanatecDiscovery()
        self.state_path = state_path or (
            Path.home() / ".local/state/LedsFanatecLinux/status.json"
        )
        self.command_path = command_path or COMMAND_PATH
        self.stop_event = threading.Event()
        self.rpm_pattern = RpmPattern()
        self.flag_pattern = FlagPattern()
        self.controller: FanatecController | None = None
        self._last_status_write = 0.0
        self._last_error: str | None = None
        self._last_command_id: str | None = None
        self._active_test: dict[str, object] | None = None
        self._applied_profile = None

    def _set_error(self, message: str | None) -> None:
        if message != self._last_error:
            if message:
                LOG.error("%s", message)
            self._last_error = message

    def _write_status(self, values: dict[str, object], *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_status_write < STATUS_INTERVAL:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=".status.", dir=self.state_path.parent
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(values, file, ensure_ascii=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_name, self.state_path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
        self._last_status_write = now

    def _find_hardware(self) -> None:
        try:
            devices = self.discovery.discover()
        except HardwareError as error:
            self.controller = None
            self._set_error(str(error))
            return
        if not devices:
            self._set_error("No se detecta un volante Fanatec compatible; se reintentará.")
            return
        if len(devices) != 1:
            self._set_error(
                f"Se detectaron {len(devices)} volantes; no se elegirá uno automáticamente."
            )
            return
        try:
            self.controller = FanatecController(devices[0])
            self.controller.turn_off()
            self.rpm_pattern.reset()
            self.flag_pattern.reset()
            self._set_error(None)
            LOG.info("Hardware preparado: %s (%d zonas RGB).", devices[0].hid_name, len(devices[0].zones))
        except HardwareError as error:
            self.controller = None
            self._set_error(str(error))

    @staticmethod
    def _is_edit_locked(telemetry) -> bool:
        return telemetry is not None and (
            telemetry.speed_kmh is None
            or telemetry.speed_kmh > EDIT_SPEED_LIMIT_KMH
        )

    def _profile_for_telemetry(self, telemetry):
        if self._applied_profile is None or not self._is_edit_locked(telemetry):
            self._applied_profile = self.store.load_active()
        return self._applied_profile

    def _accept_test_command(self, telemetry) -> None:
        try:
            command = read_test_command(self.command_path)
        except (OSError, ValueError) as error:
            self._set_error(f"Comando de prueba inválido: {error}")
            return
        if command is None or command["id"] == self._last_command_id:
            return
        self._last_command_id = str(command["id"])
        if self.controller is None:
            self._set_error("Prueba rechazada: el volante Fanatec no está disponible.")
            return
        if telemetry is not None and (
            telemetry.speed_kmh is None
            or telemetry.speed_kmh > EDIT_SPEED_LIMIT_KMH
        ):
            self._set_error("Prueba rechazada: el coche no está detenido.")
            return
        self._active_test = {
            **command,
            "started_at": time.monotonic(),
        }
        self.rpm_pattern.reset()
        self.flag_pattern.reset()
        LOG.info("Prueba de hardware iniciada: %s.", command["action"])

    def _render_test(self, profile, elapsed: float) -> None:
        if self.controller is None or self._active_test is None:
            return
        command = self._active_test
        black_rpm = {zone: (0, 0, 0) for zone in self.rpm_pattern.zones}
        black_flags = {zone: (0, 0, 0) for zone in self.flag_pattern.zones}
        action = command["action"]
        if action == "test_rpm":
            rpm = self.rpm_pattern.test_frame(profile, elapsed)
            flags = black_flags
        elif action == "test_rpm_max":
            rpm = self.rpm_pattern.test_frame(profile, elapsed, max_rpm=True)
            flags = black_flags
        else:
            rpm = black_rpm
            flags = self.flag_pattern.calculate_test(
                str(command["flag"]), now=elapsed
            )
        self.controller.write_frame({**rpm, **flags})

    def _render_active_test(self, profile, telemetry) -> bool:
        if self._active_test is None or self.controller is None:
            return False
        if telemetry is not None and self._is_edit_locked(telemetry):
            self._active_test = None
            self.rpm_pattern.reset()
            self.flag_pattern.reset()
            return False
        elapsed = time.monotonic() - float(self._active_test["started_at"])
        if elapsed >= TEST_DURATION:
            self._active_test = None
            self.rpm_pattern.reset()
            self.flag_pattern.reset()
            return False
        self._render_test(profile, elapsed)
        self.controller.write_speed(
            telemetry.speed_kmh if telemetry is not None else None
        )
        return True

    def _render(self, telemetry, profile) -> None:
        if self.controller is None:
            return
        if self._render_active_test(profile, telemetry):
            return
        rpm = self.rpm_pattern.calculate(
            telemetry.rpm,
            telemetry.max_rpm,
            profile,
            blink_on=(
                int(time.monotonic() / (profile.max_rpm_blink_ms / 2000)) % 2
                == 0
            ),
        )
        flags = self.flag_pattern.calculate(telemetry)
        self.controller.write_frame({**rpm, **flags})
        self.controller.write_speed(telemetry.speed_kmh)

    def run(self) -> None:
        profile = self.store.ensure_default()
        self._applied_profile = profile
        lock_path = self.state_path.parent / "service.lock"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a", encoding="ascii") as lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Ya hay otra instancia del servicio ejecutándose.") from error

            next_hardware_scan = 0.0
            last_sample = None
            last_idle = False
            LOG.info("Servicio de usuario iniciado.")
            self._write_status(
                {"running": True, "hardware": "searching", "telemetry": "waiting"},
                force=True,
            )
            try:
                while not self.stop_event.is_set():
                    now = time.monotonic()
                    if self.controller is None and now >= next_hardware_scan:
                        self._find_hardware()
                        next_hardware_scan = now + HARDWARE_RETRY_INTERVAL
                    if self.controller is not None and not self.controller.connected:
                        self.controller = None
                        next_hardware_scan = now
                    telemetry = self.reader.read()
                    profile = self._profile_for_telemetry(telemetry)
                    self._accept_test_command(telemetry)
                    if telemetry is None:
                        try:
                            testing = self._render_active_test(profile, None)
                        except HardwareError as error:
                            self.controller = None
                            self._active_test = None
                            next_hardware_scan = now + HARDWARE_RETRY_INTERVAL
                            self._set_error(str(error))
                            testing = False
                        if testing:
                            last_idle = False
                        else:
                            self.rpm_pattern.reset()
                            self.flag_pattern.reset()
                        if self.controller is not None and not testing and not last_idle:
                            try:
                                self.controller.turn_off()
                            except HardwareError as error:
                                self.controller = None
                                self._set_error(str(error))
                        if not testing:
                            last_idle = True
                        error_message = self.reader.last_error
                        if error_message:
                            self._set_error(error_message)
                        elif self.controller is not None:
                            self._set_error(None)
                        status: dict[str, object] = {
                            "running": True,
                            "hardware": "ready" if self.controller else "waiting",
                            "telemetry": "waiting",
                            "profile": profile.name,
                            "profile_id": profile.profile_id,
                            "profile_locked": False,
                            "test": (
                                {
                                    "action": self._active_test["action"],
                                    "flag": self._active_test["flag"],
                                }
                                if self._active_test is not None
                                else None
                            ),
                            "error": self._last_error,
                        }
                    else:
                        last_sample = telemetry
                        last_idle = False
                        try:
                            self._render(telemetry, profile)
                            if self.controller is not None:
                                self._set_error(None)
                        except HardwareError as error:
                            self.controller = None
                            next_hardware_scan = now + HARDWARE_RETRY_INTERVAL
                            self._set_error(str(error))
                        status = {
                            "running": True,
                            "hardware": "ready" if self.controller else "waiting",
                            "telemetry": "driving",
                            "simulator": telemetry.simulator,
                            "source": telemetry.source,
                            "updated_at": time.time(),
                            "rpm": telemetry.rpm,
                            "max_rpm": telemetry.max_rpm,
                            "speed_kmh": telemetry.speed_kmh,
                            "gear": telemetry.gear,
                            "throttle": telemetry.throttle,
                            "brake": telemetry.brake,
                            "flags_available": telemetry.flags_available,
                            "flags": sorted(telemetry.active_flags),
                            "profile": profile.name,
                            "profile_id": profile.profile_id,
                            "profile_locked": self._is_edit_locked(telemetry),
                            "test": (
                                {
                                    "action": self._active_test["action"],
                                    "flag": self._active_test["flag"],
                                }
                                if self._active_test is not None
                                else None
                            ),
                            "error": self._last_error,
                        }
                    self._write_status(status)
                    self.stop_event.wait(POLL_INTERVAL)
            finally:
                if self.controller is not None:
                    try:
                        self.controller.turn_off()
                    except HardwareError as error:
                        LOG.error("No se pudo apagar el volante al cerrar: %s", error)
                self._write_status(
                    {
                        "running": False,
                        "hardware": "stopped",
                        "telemetry": "stopped",
                        "last_sample_source": last_sample.source if last_sample else None,
                    },
                    force=True,
                )
                LOG.info("Servicio detenido; LED y display apagados.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Servicio de LEDs Fanatec")
    parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    service = FanatecService()
    signal.signal(signal.SIGTERM, lambda _signum, _frame: service.stop_event.set())
    signal.signal(signal.SIGINT, lambda _signum, _frame: service.stop_event.set())
    try:
        service.run()
    except RuntimeError as error:
        LOG.error("%s", error)
        raise SystemExit(1) from error


if __name__ == "__main__":
    main()
