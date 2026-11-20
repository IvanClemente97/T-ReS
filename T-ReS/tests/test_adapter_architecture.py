import unittest
from pathlib import Path

from t_res.adapters.assetto_corsa.paths import assetto_corsa_root_candidates
from t_res.adapters.registry import (
    adapter_registration,
    available_adapters,
    create_adapter,
)


class AdapterArchitectureTests(unittest.TestCase):
    def test_registry_only_lists_implemented_adapters(self):
        registrations = available_adapters()

        self.assertEqual(
            tuple(registration.simulator_id for registration in registrations),
            ("assetto_corsa_2014",),
        )
        self.assertEqual(
            adapter_registration("assetto_corsa_2014").display_name,
            "Assetto Corsa original (2014)",
        )
        self.assertEqual(
            type(create_adapter("assetto_corsa_2014")).__name__,
            "AssettoCorsaAdapter",
        )
        with self.assertRaisesRegex(ValueError, "No telemetry adapter is registered"):
            create_adapter("f1_25")

    def test_installation_paths_cover_linux_windows_and_macos_layouts(self):
        home = Path("/home/driver")
        self.assertEqual(
            assetto_corsa_root_candidates(
                platform_name="linux", home=home, environment={}
            ),
            (
                home / ".local/share/Steam/steamapps/common/assettocorsa",
                home / ".steam/steam/steamapps/common/assettocorsa",
            ),
        )
        self.assertEqual(
            assetto_corsa_root_candidates(
                platform_name="win32",
                home=home,
                environment={"PROGRAMFILES(X86)": "C:/Program Files (x86)"},
            ),
            (Path("C:/Program Files (x86)/Steam/steamapps/common/assettocorsa"),),
        )
        self.assertEqual(
            assetto_corsa_root_candidates(
                platform_name="darwin", home=home, environment={}
            ),
            (
                home / "Library/Application Support/Steam/steamapps/common/assettocorsa",
            ),
        )


if __name__ == "__main__":
    unittest.main()
