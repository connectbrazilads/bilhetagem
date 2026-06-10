import json
from pathlib import Path

from app.core.config import settings


def version_tuple(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in version.split("."):
        digits = "".join(char for char in part if char.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def is_newer_version(latest: str, current: str | None) -> bool:
    if not current:
        return True
    latest_parts = version_tuple(latest)
    current_parts = version_tuple(current)
    size = max(len(latest_parts), len(current_parts))
    latest_parts = latest_parts + (0,) * (size - len(latest_parts))
    current_parts = current_parts + (0,) * (size - len(current_parts))
    return latest_parts > current_parts


def _release_file(version: str, filename: str) -> Path:
    root = Path(settings.agent_download_dir)
    versioned = root / version / filename
    if versioned.exists():
        return versioned
    return root / filename


def _is_safe_release_version(version: str) -> bool:
    return bool(version) and Path(version).name == version and "/" not in version and "\\" not in version


def _is_safe_release_filename(filename: str) -> bool:
    return bool(filename) and Path(filename).name == filename and "/" not in filename and "\\" not in filename


def _release_sort_key(release: dict) -> tuple[str, tuple[int, ...]]:
    return (str(release.get("published_at") or ""), version_tuple(str(release.get("version") or "")))


def published_agent_version() -> str:
    manifest_path = Path(settings.agent_download_dir) / settings.agent_release_manifest_filename
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            raw_releases = data.get("versions", []) if isinstance(data, dict) else []
            releases = sorted([release for release in raw_releases if isinstance(release, dict)], key=_release_sort_key, reverse=True)
            for release in releases:
                version = str(release.get("version") or "")
                if not _is_safe_release_version(version):
                    continue
                raw_files = release.get("files", [])
                if not isinstance(raw_files, list):
                    continue
                for file in raw_files:
                    if not isinstance(file, dict):
                        continue
                    filename = str(file.get("filename") or "")
                    if file.get("kind") == "agent" and _is_safe_release_filename(filename) and _release_file(version, filename).is_file():
                        return version
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return settings.agent_latest_version
