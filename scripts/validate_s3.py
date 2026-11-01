"""Live round-trip and concurrency validation without collection or paid analysis."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory

from database_s3 import ROOT, LATEST_KEY, S3, TransferError, atomic_json, pull, push, state_path


def structure(path):
    with sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True) as connection:
        schema = connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        counts = {name: connection.execute('SELECT COUNT(*) FROM "' + name.replace('"', '""') + '"').fetchone()[0]
                  for name, _ in schema}
    return schema, counts


def main():
    config = json.loads((ROOT / 'infrastructure/storage-config.json').read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile')
    args = parser.parse_args()
    client = S3(os.environ.get('INVEST_OS_DATA_BUCKET') or config['bucket'],
                os.environ.get('AWS_REGION') or config['region'], args.profile)
    with TemporaryDirectory() as directory:
        original, restored = Path(directory) / 'original.sqlite', Path(directory) / 'restored.sqlite'
        pull(client, original)
        print('Downloaded and validated current snapshot.', flush=True)
        before = structure(original)
        uploaded = push(client, original)
        print('Published consistent snapshot through conditional upload.', flush=True)
        downloaded = pull(client, restored)
        print('Restored published snapshot; comparing schema and row counts.', flush=True)
        if downloaded['sha256'] != uploaded['sha256'] or structure(restored) != before:
            raise RuntimeError('Round trip changed database checksum, schema, or row counts')
        state = json.loads(state_path(original).read_text())
        state['etag'] = '"intentionally-obsolete-validation-etag"'
        atomic_json(state_path(original), state)
        try:
            push(client, original)
        except TransferError as error:
            if 'changed since download' not in str(error):
                raise
        else:
            raise RuntimeError('AWS unexpectedly accepted a stale upload')
        remote = client.call('head-object', '--key', LATEST_KEY)
        if remote['ETag'] != json.loads(state_path(restored).read_text())['etag']:
            raise RuntimeError('Remote database changed during stale-write validation')
        print(json.dumps({'round_trip': 'passed', 'stale_upload': 'rejected',
                          'tables_verified': len(before[0]), 'sha256': downloaded['sha256'],
                          'compressed_bytes': uploaded['compressed_bytes']}))


if __name__ == '__main__':
    main()
