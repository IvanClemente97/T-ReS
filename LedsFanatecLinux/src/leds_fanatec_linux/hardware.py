"""Acceso limitado a Fanatec mediante el driver Linux hid_fanatec/sysfs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .patterns import FLAG_ZONES, RPM_ZONES

EXPECTED_ZONES = frozenset((*RPM_ZONES, *FLAG_ZONES))
SYSFS_CLASS = Path("/sys/class/ftec_wheel")
SYSFS_DRIVER = Path("/sys/module/hid_fanatec/drivers/hid:fanatec")


class HardwareError(RuntimeError):
    """El hardware no está disponible o el driver rechazó una operación."""


@dataclass(frozen=True, slots=True)
class FanatecDevice:
    name: str
    hid_name: str
    sysfs_path: Path
    zones: dict[str, Path]
    display: Path


class FanatecDiscovery:
    def __init__(
        self,
        sysfs_class: Path = SYSFS_CLASS,
        sysfs_driver: Path = SYSFS_DRIVER,
    ) -> None:
        self.sysfs_class = sysfs_class
        self.sysfs_driver = sysfs_driver

    def discover(self) -> list[FanatecDevice]:
        devices = []
        try:
            entries = sorted(self.sysfs_class.iterdir())
        except FileNotFoundError:
            return []
        except OSError as error:
            raise HardwareError(f"No se pudo consultar {self.sysfs_class}: {error}") from error

        for entry in entries:
            try:
                real_path = entry.resolve(strict=True)
                properties = self._properties(real_path / "device/uevent")
                if properties.get("DRIVER") != "fanatec":
                    continue
                parts = properties.get("HID_ID", "").split(":")
                if len(parts) != 3 or int(parts[1], 16) != 0x0EB7 or int(parts[2], 16) != 0x0004:
                    continue
                zones = {}
                for zone_path in real_path.glob("*:RGB:*"):
                    zone = zone_path.resolve(strict=True)
                    name = zone.name.rsplit(":", 1)[-1]
                    if name in EXPECTED_ZONES and (zone / "multi_intensity").is_file():
                        zones[name] = zone
                display = self.sysfs_driver / real_path.name / "display"
                if display.is_file():
                    devices.append(
                        FanatecDevice(
                            name=real_path.name,
                            hid_name=properties.get("HID_NAME", real_path.name),
                            sysfs_path=real_path,
                            zones=zones,
                            display=display,
                        )
                    )
            except (FileNotFoundError, PermissionError, OSError, ValueError):
                continue
        return devices

    @staticmethod
    def _properties(path: Path) -> dict[str, str]:
        result = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                result[key] = value
        return result


class FanatecController:
    def __init__(self, device: FanatecDevice) -> None:
        missing = EXPECTED_ZONES - device.zones.keys()
        if missing:
            raise HardwareError(f"Faltan zonas Fanatec: {', '.join(sorted(missing))}.")
        self.device = device
        self._last_frame: dict[str, tuple[int, int, int]] = {}
        self._last_display: int | None = None

    @property
    def connected(self) -> bool:
        return self.device.sysfs_path.exists()

    @staticmethod
    def _write(path: Path, value: str) -> None:
        try:
            path.write_text(value, encoding="ascii")
        except PermissionError as error:
            raise HardwareError(f"Sin permiso para escribir {path}.") from error
        except OSError as error:
            raise HardwareError(f"No se pudo escribir {path}: {error}") from error

    def write_frame(self, frame: dict[str, tuple[int, int, int]]) -> None:
        for zone_name, color in frame.items():
            if zone_name not in self.device.zones:
                raise HardwareError(f"Zona desconocida: {zone_name}.")
            if len(color) != 3 or any(type(channel) is not int or not 0 <= channel <= 255 for channel in color):
                raise ValueError(f"Color RGB inválido para {zone_name}.")
            if self._last_frame.get(zone_name) == color:
                continue
            path = self.device.zones[zone_name] / "multi_intensity"
            self._write(path, f"{color[0]} {color[1]} {color[2]}")
            self._last_frame[zone_name] = color

    def write_speed(self, speed_kmh: float | None) -> None:
        value = None
        if speed_kmh is not None and 0 <= speed_kmh < 1000:
            value = int(speed_kmh)
        if value == self._last_display:
            return
        self._write(self.device.display, "\n" if value is None else str(value) + "\n")
        self._last_display = value

    def turn_off(self) -> None:
        self.write_frame({zone: (0, 0, 0) for zone in EXPECTED_ZONES})
        self.write_speed(None)
