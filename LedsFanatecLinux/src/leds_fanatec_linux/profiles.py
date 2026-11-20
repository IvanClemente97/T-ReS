"""Persistencia local de perfiles, independiente de la GUI y del servicio."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import uuid

from .models import LedProfile, default_profile


class ProfileStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path.home() / ".config" / "LedsFanatecLinux" / "profiles"
        self.root.mkdir(parents=True, exist_ok=True)
        self.active_path = self.root.parent / "active_profile.json"

    def list_profiles(self) -> list[LedProfile]:
        profiles = []
        for path in sorted(self.root.glob("*.json")):
            try:
                profiles.append(self._read_profile(path))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                raise ValueError(f"No se pudo leer el perfil {path.name}: {error}") from error
        return profiles

    def get(self, profile_id: str) -> LedProfile:
        path = self._profile_path(profile_id)
        profile = self._read_profile(path)
        if profile.profile_id != profile_id:
            raise ValueError("El ID guardado no coincide con el nombre del archivo.")
        return profile

    def _read_profile(self, path: Path) -> LedProfile:
        data = json.loads(path.read_text(encoding="utf-8"))
        profile = LedProfile.from_dict(data)
        if data.get("schema_version") != 3:
            self.save(profile)
        return profile

    def save(self, profile: LedProfile) -> None:
        self._write_json(self._profile_path(profile.profile_id), profile.to_dict())

    def ensure_default(self) -> LedProfile:
        profiles = self.list_profiles()
        if profiles:
            active = self.active_profile_id()
            if active:
                return self.get(active)
            self.activate(profiles[0].profile_id)
            return profiles[0]
        profile = default_profile()
        self.save(profile)
        self.activate(profile.profile_id)
        return profile

    def active_profile_id(self) -> str | None:
        try:
            data = json.loads(self.active_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(data, dict):
            raise ValueError("El archivo de perfil activo tiene un formato inválido.")
        value = data.get("active_profile_id")
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("El identificador del perfil activo no es válido.")
        uuid.UUID(value)
        return value

    def load_active(self) -> LedProfile:
        profile_id = self.active_profile_id()
        if profile_id is None:
            return self.ensure_default()
        return self.get(profile_id)

    def activate(self, profile_id: str) -> None:
        self.get(profile_id)
        self._write_json(self.active_path, {"active_profile_id": profile_id})

    def delete(self, profile_id: str) -> None:
        if self.active_profile_id() == profile_id:
            raise ValueError("Activa otro perfil antes de borrar el perfil activo.")
        self._profile_path(profile_id).unlink(missing_ok=True)

    def import_file(self, source: Path) -> LedProfile:
        imported = LedProfile.from_dict(json.loads(source.read_text(encoding="utf-8")))
        profile = LedProfile(
            profile_id=str(uuid.uuid4()),
            name=imported.name,
            rpm_colors=imported.rpm_colors,
            max_rpm_colors=imported.max_rpm_colors,
            sequence=imported.sequence,
            max_rpm_blink_ms=imported.max_rpm_blink_ms,
        )
        self.save(profile)
        return profile

    def export_file(self, profile_id: str, destination: Path) -> None:
        self._write_json(destination, self.get(profile_id).to_dict())

    def _profile_path(self, profile_id: str) -> Path:
        uuid.UUID(profile_id)
        return self.root / f"{profile_id}.json"

    @staticmethod
    def _write_json(path: Path, data: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
