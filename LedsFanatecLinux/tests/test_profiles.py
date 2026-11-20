import tempfile
import json
from pathlib import Path
import unittest
import uuid

from leds_fanatec_linux.models import LedProfile, default_profile
from leds_fanatec_linux.profiles import ProfileStore


class ProfileStoreTests(unittest.TestCase):
    def test_profile_crud_import_export_and_active_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles")
            first = default_profile("Perfil uno")
            store.save(first)
            self.assertEqual(store.ensure_default(), first)
            self.assertEqual(store.load_active(), first)

            second = default_profile("Perfil dos")
            store.save(second)
            store.activate(second.profile_id)
            with self.assertRaisesRegex(ValueError, "Activa otro perfil"):
                store.delete(second.profile_id)

            export = Path(directory) / "export.json"
            store.export_file(second.profile_id, export)
            imported = store.import_file(export)
            self.assertNotEqual(imported.profile_id, second.profile_id)
            self.assertEqual(imported.rpm_colors, second.rpm_colors)
            self.assertEqual(imported.max_rpm_colors, second.max_rpm_colors)

            store.delete(first.profile_id)
            self.assertEqual(len(store.list_profiles()), 2)

    def test_v1_profiles_migrate_legacy_shift_color_and_drop_manual_limit(self):
        profile_id = str(uuid.uuid4())
        legacy = {
            "schema_version": 1,
            "profile_id": profile_id,
            "name": "Legacy",
            "rpm_colors": ["#00FF00"] * 9,
            "shift_color": "#FF00CC",
            "sequence": "outer_to_center",
            "flag_colors": {},
            "fallback_max_rpm": 9000,
        }
        profile = LedProfile.from_dict(legacy)
        self.assertEqual(profile.max_rpm_colors, ("#FF00CC",) * 9)
        self.assertEqual(profile.sequence, "outer_to_center")
        serialized = profile.to_dict()
        self.assertEqual(serialized["schema_version"], 3)
        self.assertNotIn("fallback_max_rpm", serialized)
        self.assertNotIn("flag_colors", serialized)

    def test_loading_v1_profile_from_disk_keeps_existing_colors(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "profiles"
            root.mkdir()
            profile_id = str(uuid.uuid4())
            legacy = {
                "schema_version": 1,
                "profile_id": profile_id,
                "name": "Migrado",
                "rpm_colors": ["#123456"] * 9,
                "shift_color": "#ABCDEF",
                "sequence": "left_to_right",
                "flag_colors": {},
                "fallback_max_rpm": 12000,
            }
            (root / f"{profile_id}.json").write_text(json.dumps(legacy))
            profile = ProfileStore(root).get(profile_id)
            self.assertEqual(profile.rpm_colors, ("#123456",) * 9)
            self.assertEqual(profile.max_rpm_colors, ("#ABCDEF",) * 9)
            self.assertEqual(
                json.loads((root / f"{profile_id}.json").read_text())["schema_version"],
                3,
            )

    def test_v2_profiles_keep_max_colors_and_gain_default_blink_period(self):
        profile_id = str(uuid.uuid4())
        profile = LedProfile.from_dict(
            {
                "schema_version": 2,
                "profile_id": profile_id,
                "name": "Version 2",
                "rpm_colors": ["#00FF00"] * 9,
                "max_rpm_colors": ["#FF00CC"] * 9,
                "sequence": "left_to_right",
            }
        )
        self.assertEqual(profile.max_rpm_colors, ("#FF00CC",) * 9)
        self.assertEqual(profile.max_rpm_blink_ms, 500)
        self.assertEqual(profile.to_dict()["schema_version"], 3)

    def test_custom_max_rpm_blink_period_survives_profile_import_export(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ProfileStore(Path(directory) / "profiles")
            profile = LedProfile(
                profile_id=str(uuid.uuid4()),
                name="Blink",
                rpm_colors=("#00FF00",) * 9,
                max_rpm_colors=("#8000FF",) * 9,
                sequence="left_to_right",
                max_rpm_blink_ms=750,
            )
            store.save(profile)
            export = Path(directory) / "blink.json"
            store.export_file(profile.profile_id, export)
            imported = store.import_file(export)
            self.assertEqual(imported.max_rpm_blink_ms, 750)


if __name__ == "__main__":
    unittest.main()
