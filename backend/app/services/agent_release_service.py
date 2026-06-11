import json
import hashlib
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publishable_file_size(path: Path) -> int | None:
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
    except OSError:
        return None
    return size if size > 0 else None


def _manifest_sha256(value) -> str | None:
    if value is None:
        return None
    expected = str(value).strip().lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        return ""
    return expected


def _manifest_int(value) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _published_release_checksums(version: str) -> dict[str, str] | None:
    path = _release_file(version, "SHA256SUMS.txt")
    if not path.is_file():
        return None
    checksums: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError):
        return {}
    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = trimmed.split(None, 1)
        if len(parts) != 2:
            return {}
        checksum = _manifest_sha256(parts[0])
        filename = parts[1].strip().lstrip("*")
        if not checksum or not _is_safe_release_filename(filename):
            return {}
        if filename in checksums and checksums[filename] != checksum:
            return {}
        checksums[filename] = checksum
    return checksums


def _manifest_release_filenames(raw_files: list) -> set[str]:
    filenames: set[str] = set()
    for raw_file in raw_files:
        if not isinstance(raw_file, dict):
            continue
        filename = str(raw_file.get("filename") or "")
        if _is_safe_release_filename(filename):
            filenames.add(filename)
    return filenames


def _release_file_matches_manifest(path: Path, file: dict) -> bool:
    expected_sha256 = _manifest_sha256(file.get("sha256"))
    expected_size = _manifest_int(file.get("size_bytes"))
    if expected_size is not None and expected_size != path.stat().st_size:
        return False
    if expected_sha256 is not None and expected_sha256 != _sha256(path):
        return False
    return True


def _release_sort_key(release: dict) -> tuple[str, tuple[int, ...]]:
    return (str(release.get("published_at") or ""), version_tuple(str(release.get("version") or "")))


def published_agent_update_version() -> str | None:
    manifest_path = Path(settings.agent_download_dir) / settings.agent_release_manifest_filename
    if manifest_path.exists():
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
            raw_releases = data.get("versions", []) if isinstance(data, dict) else []
            releases = sorted([release for release in raw_releases if isinstance(release, dict)], key=_release_sort_key, reverse=True)
            for release in releases:
                version = str(release.get("version") or "")
                if not _is_safe_release_version(version):
                    continue
                raw_files = release.get("files", [])
                if not isinstance(raw_files, list):
                    continue
                published_checksums = _published_release_checksums(version)
                checksums_mismatch = (
                    published_checksums is not None
                    and set(published_checksums) != _manifest_release_filenames(raw_files)
                )
                for file in raw_files:
                    if not isinstance(file, dict):
                        continue
                    filename = str(file.get("filename") or "")
                    path = _release_file(version, filename)
                    actual_size = _publishable_file_size(path)
                    if (
                        file.get("kind") == "agent"
                        and _is_safe_release_filename(filename)
                        and not checksums_mismatch
                        and actual_size is not None
                        and _release_file_matches_manifest(path, file)
                        and (
                            published_checksums is None
                            or published_checksums.get(filename) == _sha256(path)
                        )
                    ):
                        return version
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
        else:
            return None

    path = Path(settings.agent_download_dir) / settings.agent_download_filename
    if _publishable_file_size(path) is not None:
        return settings.agent_latest_version
    return None


def published_agent_version() -> str:
    return published_agent_update_version() or settings.agent_latest_version
