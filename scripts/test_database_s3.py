"""Offline persistence regressions. Does not import application settings or credentials."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from database_s3 import AwsError, LATEST_KEY, ROOT, S3, TransferError, digest, pull, push, state_path


class MemoryS3:
    bucket = "test-private-database"
    region = "eu-central-1"

    def __init__(self):
        self.objects = {}
        self.fail_key = None

    def put(self, key, source, metadata, *, etag=None):
        if key == self.fail_key:
            raise AwsError("AccessDenied")
        previous = self.objects.get(key)
        if (etag and (not previous or previous["ETag"] != etag)) or (not etag and previous):
            raise AwsError("PreconditionFailed")
        content = source.read_bytes()
        current = {'ETag': '"' + hashlib.sha256(content).hexdigest() + '"',
                   'Metadata': deepcopy(metadata), 'body': content}
        self.objects[key] = current
        return {"ETag": current["ETag"]}

    def get(self, key, destination):
        if key not in self.objects:
            raise AwsError("NoSuchKey")
        current = self.objects[key]
        destination.write_bytes(current["body"])
        return {"ETag": current["ETag"], "Metadata": deepcopy(current["Metadata"])}


def make_database(path):
    with sqlite3.connect(path) as connection:
        connection.executescript("""
            CREATE TABLE stock_open_data_snapshots (ticker TEXT PRIMARY KEY, payload TEXT);
            CREATE TABLE historical_prices (ticker TEXT, price REAL);
            INSERT INTO stock_open_data_snapshots VALUES ('AAA', '{"source":"fixture"}');
            INSERT INTO historical_prices VALUES ('AAA', 10);
        """)


class DatabaseS3Tests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.database = self.root / "local.sqlite"
        make_database(self.database)
        self.s3 = MemoryS3()

    def seed(self):
        return push(self.s3, self.database, initialize=True, day="2026-11-01")

    def change(self, path, price):
        with sqlite3.connect(path) as connection:
            connection.execute("UPDATE historical_prices SET price=?", (price,))

    def test_round_trip_preserves_rows_and_checksum(self):
        uploaded = self.seed()
        restored = self.root / "restored.sqlite"
        downloaded = pull(self.s3, restored)
        self.assertEqual(uploaded["sha256"], downloaded["sha256"])
        self.assertEqual(digest(restored), uploaded["sha256"])
        with sqlite3.connect(restored) as connection:
            self.assertEqual(connection.execute("SELECT price FROM historical_prices").fetchone(), (10,))
        self.assertEqual(json.loads(state_path(restored).read_text())["etag"], self.s3.objects[LATEST_KEY]["ETag"])

    def test_initialize_cannot_overwrite_remote(self):
        self.seed()
        original = deepcopy(self.s3.objects)
        self.change(self.database, 20)
        with self.assertRaisesRegex(TransferError, "already initialized"):
            self.seed()
        self.assertEqual(self.s3.objects, original)

    def test_stale_writer_cannot_erase_a_newer_refresh(self):
        self.seed()
        stale = self.root / "stale.sqlite"
        pull(self.s3, stale)
        self.change(self.database, 20)
        push(self.s3, self.database, day="2026-11-01")
        current = deepcopy(self.s3.objects)
        self.change(stale, 30)
        with self.assertRaisesRegex(TransferError, "changed since download"):
            push(self.s3, stale)
        self.assertEqual(self.s3.objects, current)
        with sqlite3.connect(stale) as connection:
            self.assertEqual(connection.execute("SELECT price FROM historical_prices").fetchone(), (30,))

    def test_daily_backup_is_not_duplicated_or_overwritten(self):
        self.seed()
        backup = deepcopy(self.s3.objects['backups/2026-11-01.sqlite.gz'])
        self.change(self.database, 20)
        push(self.s3, self.database, day="2026-11-01")
        self.assertEqual(self.s3.objects['backups/2026-11-01.sqlite.gz'], backup)
        push(self.s3, self.database, day="2026-11-02")
        self.assertEqual(len(self.s3.objects), 3)

    def test_checksum_failure_preserves_existing_local_database_and_state(self):
        self.seed()
        before = self.database.read_bytes(), state_path(self.database).read_bytes()
        self.s3.objects[LATEST_KEY]['Metadata']['sha256'] = '0' * 64
        with self.assertRaisesRegex(TransferError, "checksum"):
            pull(self.s3, self.database, replace_local=True)
        self.assertEqual((self.database.read_bytes(), state_path(self.database).read_bytes()), before)

    def test_corrupt_archive_never_replaces_database(self):
        self.seed()
        self.s3.objects[LATEST_KEY]['body'] = b'not gzip'
        before = digest(self.database)
        with self.assertRaises(gzip.BadGzipFile):
            pull(self.s3, self.database, replace_local=True)
        self.assertEqual(digest(self.database), before)

    def test_missing_checksum_is_rejected(self):
        self.seed()
        self.s3.objects[LATEST_KEY]['Metadata'].clear()
        with self.assertRaisesRegex(TransferError, "missing"):
            pull(self.s3, self.root / "missing.sqlite")

    def test_missing_remote_does_not_create_empty_baseline(self):
        missing = self.root / "missing.sqlite"
        with self.assertRaisesRegex(AwsError, "NoSuchKey"):
            pull(self.s3, missing)
        self.assertFalse(missing.exists())
        self.assertFalse(state_path(missing).exists())

    def test_existing_local_database_requires_explicit_replacement(self):
        self.seed()
        with self.assertRaisesRegex(TransferError, "--replace-local"):
            pull(self.s3, self.database)

    def test_pull_refuses_sqlite_sidecars_even_with_replacement(self):
        self.seed()
        Path(str(self.database) + '-wal').touch()
        with self.assertRaisesRegex(TransferError, "Close SQLite writers"):
            pull(self.s3, self.database, replace_local=True)

    def test_push_requires_download_baseline(self):
        with self.assertRaises(FileNotFoundError):
            push(self.s3, self.database)
        self.assertFalse(self.s3.objects)

    def test_baseline_cannot_be_reused_for_a_different_bucket(self):
        self.seed()
        self.s3.bucket = 'other-bucket'
        with self.assertRaisesRegex(TransferError, "different S3"):
            push(self.s3, self.database)

    def test_failed_primary_upload_does_not_advance_baseline(self):
        self.seed()
        before = state_path(self.database).read_bytes()
        self.change(self.database, 20)
        self.s3.fail_key = LATEST_KEY
        with self.assertRaisesRegex(AwsError, 'AccessDenied'):
            push(self.s3, self.database)
        self.assertEqual(state_path(self.database).read_bytes(), before)

    def test_failed_backup_keeps_primary_baseline_recoverable(self):
        self.seed()
        self.change(self.database, 20)
        self.s3.fail_key = 'backups/2026-11-02.sqlite.gz'
        with self.assertRaisesRegex(AwsError, 'AccessDenied'):
            push(self.s3, self.database, day='2026-11-02')
        self.assertEqual(json.loads(state_path(self.database).read_text())['etag'], self.s3.objects[LATEST_KEY]['ETag'])
        self.s3.fail_key = None
        push(self.s3, self.database, day='2026-11-02')
        self.assertIn('backups/2026-11-02.sqlite.gz', self.s3.objects)

    def test_backup_includes_committed_wal_changes(self):
        connection = sqlite3.connect(self.database)
        self.addCleanup(connection.close)
        connection.execute('PRAGMA journal_mode=WAL')
        connection.execute('UPDATE historical_prices SET price=99')
        connection.commit()
        self.seed()
        restored = self.root / 'wal-restored.sqlite'
        pull(self.s3, restored)
        with sqlite3.connect(restored) as downloaded:
            self.assertEqual(downloaded.execute('SELECT price FROM historical_prices').fetchone(), (99,))

    def test_invalid_database_is_never_uploaded(self):
        self.database.write_bytes(b'not sqlite')
        with self.assertRaises(sqlite3.Error):
            self.seed()
        self.assertFalse(self.s3.objects)

    def test_empty_application_schema_is_rejected(self):
        self.database.unlink()
        with sqlite3.connect(self.database) as connection:
            connection.execute('CREATE TABLE unrelated (id INTEGER)')
        with self.assertRaisesRegex(TransferError, 'required stock tables'):
            self.seed()
        self.assertFalse(self.s3.objects)

    def test_aws_cli_enforces_conditional_and_encrypted_writes(self):
        with patch('database_s3.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = '{"ETag":"new"}'
            client = S3('bucket', 'eu-central-1', 'developer')
            client.put(LATEST_KEY, self.database, {'sha256': 'test'}, etag='"old"')
            arguments = run.call_args.args[0]
            self.assertEqual(arguments[arguments.index('--if-match') + 1], '"old"')
            self.assertIn('--checksum-algorithm', arguments)
            self.assertIn('AES256', arguments)
            self.assertNotIn('shell', run.call_args.kwargs)
            client.put('backups/day.sqlite.gz', self.database, {})
            self.assertIn('--if-none-match', run.call_args.args[0])


class InfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.resources = json.loads((ROOT / 'infrastructure/storage.json').read_text())['Resources']

    def test_latest_has_no_expiry_and_backups_have_bounded_retention(self):
        bucket = self.resources['DatabaseBucket']
        self.assertEqual(bucket['DeletionPolicy'], 'Retain')
        self.assertEqual(bucket['UpdateReplacePolicy'], 'Retain')
        rules = bucket['Properties']['LifecycleConfiguration']['Rules']
        expirations = [r for r in rules if 'ExpirationInDays' in r]
        self.assertEqual([(r['Prefix'], r['ExpirationInDays']) for r in expirations], [('backups/', 7)])
        self.assertTrue(all(bucket['Properties']['PublicAccessBlockConfiguration'].values()))

    def test_runtime_role_cannot_manage_infrastructure_or_delete_objects(self):
        role = self.resources['DataRole']['Properties']
        statements = role['Policies'][0]['PolicyDocument']['Statement']
        actions = {action for statement in statements for action in statement['Action']}
        self.assertEqual(actions, {'s3:GetObject', 's3:PutObject'})
        trust = role['AssumeRolePolicyDocument']['Statement'][0]
        self.assertEqual(trust['Condition']['StringEquals']['token.actions.githubusercontent.com:sub'],
                         {'Fn::Sub': 'repo:${GitHubRepository}:ref:refs/heads/main'})

    def test_deployer_cannot_expand_its_own_or_runtime_maximum_permissions(self):
        statements = self.resources['InfrastructureRole']['Properties']['Policies'][0]['PolicyDocument']['Statement']
        writes = next(s for s in statements if 'iam:PutRolePolicy' in s['Action'])
        self.assertEqual(writes['Resource'], [{'Fn::Sub': 'arn:${AWS::Partition}:iam::${AWS::AccountId}:role/invest-os-data-github'}])
        self.assertEqual(self.resources['DataRole']['Properties']['PermissionsBoundary'], {'Ref': 'DataPermissionsBoundary'})
        self.assertFalse(any('iam:DeleteRolePermissionsBoundary' in s['Action'] or 'iam:CreatePolicyVersion' in s['Action']
                             for s in statements))
        creation = next(s for s in statements if 'iam:CreateRole' in s['Action'])
        self.assertEqual(creation['Condition']['StringEquals']['iam:PermissionsBoundary'], {'Ref': 'DataPermissionsBoundary'})


if __name__ == '__main__':
    unittest.main()
