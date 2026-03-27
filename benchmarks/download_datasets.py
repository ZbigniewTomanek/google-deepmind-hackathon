"""Download and verify pinned benchmark datasets for Stage 1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmarks.benchmarks.longmemeval import LONGMEMEVAL_S_LOCK, DatasetLock, longmemeval_dataset_dir

DEFAULT_TIMEOUT_SECONDS = 120.0
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser for dataset downloads."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Force a re-download even if the pinned dataset file is already present and valid.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Network timeout in seconds for the download request. Default: {DEFAULT_TIMEOUT_SECONDS}.",
    )
    return parser


def sha256_for_file(path: Path) -> str:
    """Compute the SHA256 for an existing file."""

    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(DOWNLOAD_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def verify_dataset_file(path: Path, lock: DatasetLock) -> tuple[int, str]:
    """Verify a local dataset file against the committed lock."""

    size_bytes = path.stat().st_size
    checksum = sha256_for_file(path)
    if size_bytes != lock.size_bytes:
        raise RuntimeError(
            f"Size mismatch for {path}: expected {lock.size_bytes} bytes, got {size_bytes} bytes."
        )
    if checksum != lock.sha256:
        raise RuntimeError(
            f"SHA256 mismatch for {path}: expected {lock.sha256}, got {checksum}."
        )
    return size_bytes, checksum


def download_file(path: Path, lock: DatasetLock, timeout: float) -> tuple[int, str]:
    """Download a pinned artifact, verify it, and atomically move it into place."""

    request = Request(lock.source_url, headers={"Accept-Encoding": "identity", "User-Agent": "neocortex-benchmarks/1"})
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with urlopen(request, timeout=timeout) as response, NamedTemporaryFile(
            mode="wb",
            delete=False,
            dir=path.parent,
            prefix=f"{path.name}.",
            suffix=".part",
        ) as temp_file:
            temp_path = Path(temp_file.name)
            digest = hashlib.sha256()
            size_bytes = 0

            while chunk := response.read(DOWNLOAD_CHUNK_SIZE):
                temp_file.write(chunk)
                digest.update(chunk)
                size_bytes += len(chunk)

        checksum = digest.hexdigest()
        if size_bytes != lock.size_bytes:
            raise RuntimeError(
                f"Downloaded size mismatch for {path.name}: expected {lock.size_bytes} bytes, got {size_bytes} bytes."
            )
        if checksum != lock.sha256:
            raise RuntimeError(
                f"Downloaded SHA256 mismatch for {path.name}: expected {lock.sha256}, got {checksum}."
            )

        temp_path.replace(path)
        return size_bytes, checksum
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Failed to download {lock.source_url}: {exc}") from exc
    except Exception:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
        raise


def manifest_payload(lock: DatasetLock, size_bytes: int, checksum: str, retrieved_at: datetime) -> dict[str, object]:
    """Build the local manifest payload written next to the downloaded file."""

    return {
        **asdict(lock),
        "size_bytes": size_bytes,
        "sha256": checksum,
        "retrieved_at": retrieved_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
    }


def ensure_manifest(path: Path, lock: DatasetLock, size_bytes: int, checksum: str, retrieved_at: datetime) -> None:
    """Write or refresh the local manifest if it is missing or stale."""

    payload = manifest_payload(lock=lock, size_bytes=size_bytes, checksum=checksum, retrieved_at=retrieved_at)

    if path.exists():
        existing_payload = json.loads(path.read_text())
        if existing_payload == payload:
            return

    path.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n")


def download_longmemeval_s(refresh: bool, timeout: float) -> Path:
    """Ensure the pinned LongMemEval-S dataset exists locally and matches the committed lock."""

    dataset_dir = longmemeval_dataset_dir()
    dataset_path = dataset_dir / LONGMEMEVAL_S_LOCK.filename
    manifest_path = dataset_dir / "manifest.json"

    if dataset_path.exists() and not refresh:
        size_bytes, checksum = verify_dataset_file(dataset_path, LONGMEMEVAL_S_LOCK)
        ensure_manifest(
            manifest_path,
            LONGMEMEVAL_S_LOCK,
            size_bytes=size_bytes,
            checksum=checksum,
            retrieved_at=datetime.fromtimestamp(dataset_path.stat().st_mtime, tz=UTC),
        )
        print(f"Verified existing dataset: {dataset_path}")
        return dataset_path

    size_bytes, checksum = download_file(dataset_path, LONGMEMEVAL_S_LOCK, timeout=timeout)
    ensure_manifest(
        manifest_path,
        LONGMEMEVAL_S_LOCK,
        size_bytes=size_bytes,
        checksum=checksum,
        retrieved_at=datetime.now(tz=UTC),
    )
    print(f"Downloaded dataset: {dataset_path}")
    return dataset_path


def main() -> int:
    """CLI entry point."""

    args = build_parser().parse_args()
    download_longmemeval_s(refresh=args.refresh, timeout=args.timeout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
