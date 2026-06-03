"""Unified benchmark cache for JPL DE440 and related lab datasets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DE440_FILENAME = "de440.bsp"
DE440_SOURCE_URL = (
    "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/spk/planets/de440.bsp"
)
# JPL DE440 is ~114 MiB; reject truncated downloads.
DE440_MIN_BYTES = 100_000_000
MANIFEST_NAME = "de440.manifest.json"


@dataclass(frozen=True)
class De440Resolution:
    path: Path | None
    status: str
    reason: str | None = None
    manifest: dict[str, Any] | None = None


def default_cache_root(lab_root: Path | None = None) -> Path:
    """Return the repo-scoped benchmark cache directory."""
    explicit = os.environ.get("SIDERUST_BENCHES_CACHE")
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = lab_root or Path(__file__).resolve().parent.parent
    return (root / ".benches_cache").resolve()


def kernel_path(cache_root: Path | None = None, filename: str = DE440_FILENAME) -> Path:
    root = cache_root or default_cache_root()
    return root / "kernels" / filename


def manifest_path(cache_root: Path | None = None) -> Path:
    return kernel_path(cache_root).with_name(MANIFEST_NAME)


def datasets_dir(cache_root: Path | None = None) -> Path:
    root = cache_root or default_cache_root()
    return root / "siderust_datasets"


def de440_dataset_link(cache_root: Path | None = None) -> Path:
    return datasets_dir(cache_root) / "de440_dataset" / DE440_FILENAME


def verify_de440(path: Path) -> tuple[bool, str | None]:
    """Return (ok, error_message) for a candidate DE440 BSP file."""
    if not path.is_file():
        return False, f"file not found: {path}"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, str(exc)
    if size < DE440_MIN_BYTES:
        return False, f"file too small ({size} bytes, expected >= {DE440_MIN_BYTES})"
    return True, None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_manifest(cache_root: Path) -> dict[str, Any] | None:
    path = manifest_path(cache_root)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_kernel_manifest(
    bsp_path: Path,
    *,
    source_url: str = DE440_SOURCE_URL,
    downloaded_at: str | None = None,
    cache_root: Path | None = None,
) -> dict[str, Any]:
    """Write provenance metadata for the cached DE440 kernel."""
    root = cache_root or default_cache_root()
    manifest = {
        "kernel": DE440_FILENAME,
        "path": str(bsp_path.resolve()),
        "size": bsp_path.stat().st_size,
        "sha256": _sha256_file(bsp_path),
        "source_url": source_url,
        "downloaded_at": downloaded_at or datetime.now(timezone.utc).isoformat(),
    }
    manifest_path(root).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def prepare_cache_layout(cache_root: Path | None = None) -> Path:
    """Ensure cache directories exist and the Siderust dataset symlink is present."""
    root = (cache_root or default_cache_root()).resolve()
    kernels_dir = root / "kernels"
    dataset_dir = root / "siderust_datasets" / "de440_dataset"
    kernels_dir.mkdir(parents=True, exist_ok=True)
    dataset_dir.mkdir(parents=True, exist_ok=True)

    bsp = kernels_dir / DE440_FILENAME
    link = dataset_dir / DE440_FILENAME
    if bsp.is_file():
        if link.exists() or link.is_symlink():
            if link.is_symlink() or link.is_file():
                try:
                    if link.resolve() != bsp.resolve():
                        link.unlink(missing_ok=True)
                        link.symlink_to(bsp)
                except OSError:
                    pass
            else:
                link.unlink(missing_ok=True)
                link.symlink_to(bsp)
        else:
            link.symlink_to(bsp)
    return root


def export_cache_env(
    cache_root: Path | None = None,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Populate process environment variables for adapters and orchestrator."""
    root = prepare_cache_layout(cache_root)
    bsp = root / "kernels" / DE440_FILENAME
    out = dict(env or os.environ)
    out["SIDERUST_BENCHES_CACHE"] = str(root)
    out["ASTROPY_JPL_BSP_PATH"] = str(bsp)
    out.setdefault("ANISE_BSP_PATH", str(bsp))
    out["SIDERUST_DATASETS_DIR"] = str(root / "siderust_datasets")
    return out


def resolve_de440(cache_root: Path | None = None) -> De440Resolution:
    """Resolve the cached DE440 BSP without downloading."""
    root = prepare_cache_layout(cache_root)
    bsp = kernel_path(root)
    ok, err = verify_de440(bsp)
    if ok:
        manifest = _read_manifest(root)
        return De440Resolution(path=bsp, status="ok", manifest=manifest)
    return De440Resolution(
        path=None,
        status="missing",
        reason=err or "DE440 BSP not present in benchmark cache",
        manifest=_read_manifest(root),
    )


def _download_atomic(url: str, dest: Path) -> None:
    partial = dest.with_suffix(dest.suffix + ".partial")
    partial.parent.mkdir(parents=True, exist_ok=True)
    if partial.exists():
        partial.unlink()
    try:
        with urllib.request.urlopen(url, timeout=300) as response, partial.open("wb") as handle:
            shutil.copyfileobj(response, handle)
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def ensure_de440(*, allow_network: bool, cache_root: Path | None = None) -> De440Resolution:
    """Ensure DE440 exists in the benchmark cache, downloading when allowed."""
    root = prepare_cache_layout(cache_root)
    bsp = kernel_path(root)
    ok, err = verify_de440(bsp)
    if ok:
        manifest = _read_manifest(root) or write_kernel_manifest(bsp, cache_root=root)
        return De440Resolution(path=bsp, status="ok", manifest=manifest)

    if not allow_network:
        return De440Resolution(
            path=None,
            status="missing",
            reason=err or "DE440 BSP missing and network download disabled",
            manifest=_read_manifest(root),
        )

    try:
        _download_atomic(DE440_SOURCE_URL, bsp)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return De440Resolution(
            path=None,
            status="download_failed",
            reason=f"failed to download DE440 from {DE440_SOURCE_URL}: {exc}",
            manifest=_read_manifest(root),
        )

    ok, err = verify_de440(bsp)
    if not ok:
        bsp.unlink(missing_ok=True)
        return De440Resolution(
            path=None,
            status="invalid",
            reason=err or "downloaded DE440 BSP failed verification",
            manifest=_read_manifest(root),
        )

    manifest = write_kernel_manifest(
        bsp,
        source_url=DE440_SOURCE_URL,
        cache_root=root,
    )
    prepare_cache_layout(root)
    return De440Resolution(path=bsp, status="ok", manifest=manifest)


def pipeline_needs_de440(
    *,
    adapters: list[str],
    experiments: list[str],
    kernels_de440_enabled: bool = True,
) -> bool:
    """Return True when the selected run includes DE440-backed candidates."""
    if not kernels_de440_enabled:
        return False
    from catalog import default_registry

    registry = default_registry()
    de440_ids = {
        "siderust:de440",
        "siderust:de440_barycenter",
        "anise",
        "astropy:de440-local",
    }
    adapter_map = {
        "siderust": {"siderust:de440", "siderust:de440_barycenter"},
        "anise": {"anise"},
        "astropy": {"astropy:de440-local"},
    }
    for adapter in adapters:
        for cand_id in adapter_map.get(adapter, ()):
            if cand_id not in de440_ids:
                continue
            for experiment in experiments:
                entry = registry.get(cand_id, experiment)
                if entry is not None and entry.support == "supported":
                    return True
    return False


def _cli() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Siderust Lab cache manager")
    sub = parser.add_subparsers(dest="command", required=True)

    ensure = sub.add_parser("ensure-de440", help="Ensure DE440 is present in the cache")
    ensure.add_argument(
        "--allow-network",
        action="store_true",
        help="Download DE440 when it is missing",
    )
    ensure.add_argument(
        "--cache-root",
        default=None,
        help="Override SIDERUST_BENCHES_CACHE / default .benches_cache",
    )

    args = parser.parse_args()
    cache_root = Path(args.cache_root).expanduser().resolve() if args.cache_root else None
    if args.command == "ensure-de440":
        result = ensure_de440(allow_network=args.allow_network, cache_root=cache_root)
        payload = {
            "status": result.status,
            "path": str(result.path) if result.path else None,
            "reason": result.reason,
            "manifest": result.manifest,
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.path is not None else 1
    return 1


if __name__ == "__main__":
    raise SystemExit(_cli())
