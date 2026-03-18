"""Deterministic workload packaging helpers."""

from __future__ import annotations

import base64
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from greenference.image import Image
from greenference.workload import Workload

_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


@dataclass(slots=True)
class PackagedWorkload:
    archive_name: str
    archive_bytes: bytes
    included_paths: list[str]
    dockerfile_text: str

    @property
    def archive_b64(self) -> str:
        return base64.b64encode(self.archive_bytes).decode()


def package_workload(module_path: Path, workload: Workload) -> PackagedWorkload:
    source_paths = _collect_context_paths(module_path, workload)
    dockerfile_text = _render_dockerfile(workload)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_text(archive, "Dockerfile", dockerfile_text)
        for path in sorted(source_paths):
            source = Path(path)
            _write_file(archive, source, Path(path).as_posix())
    archive_name = f"{module_path.stem}-{workload.name}-context.zip"
    return PackagedWorkload(
        archive_name=archive_name,
        archive_bytes=buffer.getvalue(),
        included_paths=sorted(source_paths),
        dockerfile_text=dockerfile_text,
    )


def _collect_context_paths(module_path: Path, workload: Workload) -> set[str]:
    cwd = Path.cwd().resolve()
    module_path = module_path.resolve()
    included: set[str] = set()
    candidates = [module_path, *[Path(item) for item in workload.context_paths]]
    if isinstance(workload.image, Image):
        candidates.extend(Path(item) for item in workload.image.build_context_paths)
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else (cwd / candidate).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"context path not found: {candidate}")
        if resolved.is_dir():
            for file_path in sorted(path for path in resolved.rglob("*") if path.is_file()):
                included.add(_relative_to_cwd(file_path, cwd))
        else:
            included.add(_relative_to_cwd(resolved, cwd))
    return included


def _relative_to_cwd(path: Path, cwd: Path) -> str:
    try:
        return path.resolve().relative_to(cwd).as_posix()
    except ValueError as exc:
        raise ValueError(f"context path must be inside current working directory: {path}") from exc


def _render_dockerfile(workload: Workload) -> str:
    if isinstance(workload.image, Image):
        return str(workload.image)
    return f"FROM {workload.image}\n"


def _write_text(archive: zipfile.ZipFile, name: str, content: str) -> None:
    info = zipfile.ZipInfo(name)
    info.date_time = _ZIP_TIMESTAMP
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, content.encode())


def _write_file(archive: zipfile.ZipFile, source: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname)
    info.date_time = _ZIP_TIMESTAMP
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, source.read_bytes())
