"""Transfer consistent SQLite snapshots using AWS CLI credentials, never application secrets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LATEST_KEY = "database/latest.sqlite.gz"
REQUIRED_TABLES = {"stock_open_data_snapshots", "historical_prices"}


class TransferError(RuntimeError):
    pass


class AwsError(TransferError):
    def __init__(self, message: str):
        super().__init__(message)
        self.precondition_failed = "PreconditionFailed" in message or "ConditionalRequestConflict" in message


class S3:
    def __init__(self, bucket: str, region: str, profile: str | None = None):
        self.bucket, self.region, self.profile = bucket, region, profile

    def call(self, operation: str, *arguments: str) -> dict:
        command = ["aws", "--region", self.region, "--no-cli-pager", "--output", "json"]
        if self.profile:
            command += ["--profile", self.profile]
        result = subprocess.run(
            command + ["s3api", operation, "--bucket", self.bucket, *arguments],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise AwsError(result.stderr.strip())
        return json.loads(result.stdout or "{}")

    def get(self, key: str, destination: Path) -> dict:
        return self.call("get-object", "--key", key, str(destination))

    def put(self, key: str, source: Path, metadata: dict, *, etag: str | None = None) -> dict:
        return self.call(
            "put-object", "--key", key, "--body", str(source),
            "--content-type", "application/gzip", "--server-side-encryption", "AES256",
            "--checksum-algorithm", "SHA256", "--metadata", json.dumps(metadata),
            *( ["--if-match", etag] if etag else ["--if-none-match", "*"] ),
        )


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_database(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise TransferError(f"SQLite database is missing or empty: {path}")
    with sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        if connection.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise TransferError("SQLite integrity check failed")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not REQUIRED_TABLES <= tables:
            raise TransferError("Snapshot is missing required stock tables")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, indent=2)
        stream.write("\n")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def state_path(database: Path) -> Path:
    return database.with_name(database.name + ".s3.json")


def write_state(database: Path, s3: S3, etag: str, checksum: str) -> None:
    atomic_json(state_path(database), {
        "bucket": s3.bucket, "region": s3.region, "key": LATEST_KEY,
        "etag": etag, "sha256": checksum,
    })


def pull(s3: S3, database: Path, *, replace_local: bool = False) -> dict:
    # Explicit replacement is required even when a sidecar exists: it is never safe
    # to infer that a developer has no uncommitted backfill or open WAL transaction.
    if database.exists() and not replace_local:
        raise TransferError("Local database exists. Back it up and use --replace-local to replace it explicitly.")
    if any(Path(str(database) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise TransferError("Close SQLite writers and checkpoint/remove SQLite sidecars before pulling.")
    database.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=database.parent) as directory:
        archive, restored = Path(directory) / "snapshot.gz", Path(directory) / "snapshot.sqlite"
        response = s3.get(LATEST_KEY, archive)
        expected = response.get("Metadata", {}).get("sha256")
        if not expected or not response.get("ETag"):
            raise TransferError("Remote snapshot is missing its checksum or ETag")
        with gzip.open(archive, "rb") as source, restored.open("wb") as destination:
            shutil.copyfileobj(source, destination)
        if digest(restored) != expected:
            raise TransferError("Remote snapshot checksum does not match; local database preserved")
        validate_database(restored)
        os.replace(restored, database)
        write_state(database, s3, response["ETag"], expected)
    return {"operation": "pull", "sha256": expected, "bytes": database.stat().st_size}


def push(s3: S3, database: Path, *, initialize: bool = False, day: str | None = None) -> dict:
    if initialize:
        etag = None  # Only succeeds when the remote object does not exist.
    else:
        baseline = json.loads(state_path(database).read_text())
        if (baseline.get("bucket"), baseline.get("region"), baseline.get("key")) != (s3.bucket, s3.region, LATEST_KEY):
            raise TransferError("Download baseline belongs to a different S3 location")
        etag = baseline.get("etag")
        if not etag:
            raise TransferError("Download baseline has no ETag; pull before pushing")
    validate_database(database)
    with tempfile.TemporaryDirectory() as directory:
        snapshot, archive = Path(directory) / "snapshot.sqlite", Path(directory) / "snapshot.gz"
        # SQLite's backup API includes committed WAL contents and creates a
        # transactionally consistent file, unlike copying a live database file.
        with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as source:
            with sqlite3.connect(snapshot) as destination:
                source.backup(destination)
        validate_database(snapshot)
        checksum = digest(snapshot)
        with snapshot.open("rb") as source, archive.open("wb") as destination:
            with gzip.GzipFile(filename="", fileobj=destination, mode="wb", mtime=0, compresslevel=6) as compressed:
                shutil.copyfileobj(source, compressed)
        metadata = {"sha256": checksum, "format": "sqlite-gzip-v1"}
        try:
            response = s3.put(LATEST_KEY, archive, metadata, etag=etag)
        except AwsError as error:
            if error.precondition_failed:
                raise TransferError("S3 database changed since download (or is already initialized). Preserve local work, pull a fresh copy and reapply changes.") from error
            raise
        # Save the new baseline immediately: a subsequent backup failure must not
        # leave a successful primary upload with an obsolete local ETag.
        write_state(database, s3, response["ETag"], checksum)
        backup_key = f"backups/{day or datetime.now(timezone.utc).date().isoformat()}.sqlite.gz"
        try:
            s3.put(backup_key, archive, metadata)
        except AwsError as error:
            if not error.precondition_failed:
                raise
        return {"operation": "push", "sha256": checksum, "compressed_bytes": archive.stat().st_size,
                "daily_backup": backup_key}


def main() -> int:
    config_path = ROOT / "infrastructure/storage-config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("pull", "push"))
    parser.add_argument("--database", type=Path, default=ROOT / "data/invest_os.sqlite")
    parser.add_argument("--bucket", default=os.environ.get("INVEST_OS_DATA_BUCKET") or config.get("bucket"))
    parser.add_argument("--region", default=os.environ.get("AWS_REGION") or config.get("region", "eu-central-1"))
    parser.add_argument("--profile")
    parser.add_argument("--replace-local", action="store_true")
    parser.add_argument("--initialize", action="store_true", help="One-time seed; cannot overwrite an existing remote database")
    args = parser.parse_args()
    if not args.bucket:
        parser.error("Set INVEST_OS_DATA_BUCKET or deploy infrastructure/storage.json first")
    if (args.operation == "pull" and args.initialize) or (args.operation == "push" and args.replace_local):
        parser.error("--initialize is for push; --replace-local is for pull")
    s3 = S3(args.bucket, args.region, args.profile)
    try:
        result = (pull(s3, args.database, replace_local=args.replace_local) if args.operation == "pull"
                  else push(s3, args.database, initialize=args.initialize))
    except (TransferError, OSError, ValueError, sqlite3.Error, EOFError) as error:
        print(f"Database transfer failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"bucket": args.bucket, **result}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
