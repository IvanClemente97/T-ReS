"""Diagnóstico de solo lectura para el puente AC y el volante."""

from __future__ import annotations

import json
import os

from .hardware import EXPECTED_ZONES, FanatecDiscovery
from .telemetry import AssettoCorsaTelemetryReader


def main() -> None:
    devices = FanatecDiscovery().discover()
    print("Hardware:")
    if not devices:
        print("  No se detectó un volante Fanatec compatible.")
    for device in devices:
        missing = EXPECTED_ZONES - device.zones.keys()
        print(f"  {device.hid_name}: {len(device.zones)}/15 zonas, display={device.display}")
        if missing:
            print(f"  Zonas ausentes: {', '.join(sorted(missing))}")
        for zone, path in sorted(device.zones.items()):
            target = path / "multi_intensity"
            print(f"  {zone}: escritura={'sí' if target.exists() and os.access(target, os.W_OK) else 'no'}")

    reader = AssettoCorsaTelemetryReader()
    sample = reader.read()
    print("Telemetría:")
    if sample is None:
        print("  No hay una muestra fresca de Assetto Corsa.")
        if reader.last_error:
            print(f"  Diagnóstico: {reader.last_error}")
    else:
        print(
            json.dumps(
                {
                    "simulator": sample.simulator,
                    "source": sample.source,
                    "rpm": sample.rpm,
                    "max_rpm": sample.max_rpm,
                    "speed_kmh": sample.speed_kmh,
                    "gear": sample.gear,
                    "throttle": sample.throttle,
                    "brake": sample.brake,
                    "flags_available": sample.flags_available,
                    "flags": sorted(sample.active_flags),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
