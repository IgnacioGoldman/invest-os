# SQLite persistence in S3

The shared stock database lives in a private, AES256-encrypted S3 bucket in
`eu-central-1`. Git contains application code, normalized issuer facts, public
static exports, and the simulation ledger. The local SQLite working copy and
its S3 download baseline are ignored by Git.

Each serialized data workflow restores `database/latest.sqlite.gz`, checks its
SHA256 and SQLite integrity, runs collection and validation, then persists a
consistent compressed SQLite backup to S3 before committing public exports.
SQLite's backup API includes committed WAL data. Workflow failures never fall
back to an empty database. All database writers retain the shared `pages`
concurrency group. Writes from other machines use S3 ETag preconditions to
reject stale baselines, even if they are outside the workflow queue.

`backups/YYYY-MM-DD.sqlite.gz` retains the first successfully published snapshot
of each UTC day. Subsequent refreshes never overwrite that day's backup. S3
lifecycle expires backups after seven days; deletion is asynchronous and can
briefly retain extra copies. The current database never expires. Versioning is
disabled so overwritten current objects do not accumulate hidden versions.
Incomplete multipart uploads expire after one day.

## Infrastructure and authentication

`infrastructure/storage.json` defines the bucket, encryption, public-access
blocks, HTTPS-only and conditional-write policies, lifecycle rules, and GitHub
OIDC roles. Bucket deletion and replacement retain the stored data. The data
role can only read/write database objects; it cannot delete objects or manage
infrastructure. GitHub trust is restricted to this repository's `main` branch.

Bootstrap from a local AWS CLI session with S3, IAM and CloudFormation setup
permissions:

```sh
aws login --profile invest-os --region eu-central-1
python3 scripts/deploy_s3.py --profile invest-os --configure-github
python3 scripts/database_s3.py push --initialize --profile invest-os
```

`--initialize` is only for the initial migration and fails if a remote database
already exists. Before seeding, verify that the local database includes the
latest published data and preserve a local backup. Do not initialize a fresh
empty database or reset the simulation ledger. No Gemini credentials are needed.

The deployment helper creates/updates the CloudFormation stack, reuses any
existing GitHub OIDC provider, writes non-secret outputs to
`infrastructure/storage-config.json`, and optionally configures GitHub repository
variables. Keep that config in Git. Subsequent changes can be deployed through
the manual **Manage S3 database infrastructure** workflow. That workflow uses
the separate infrastructure role. Changes to that deployment role, the runtime permissions boundary, or the owned OIDC provider require the local bootstrap identity; routine bucket and runtime-role updates use GitHub. Resource deletion is not part of deployment.

Required repository variables are `INVEST_OS_DATA_BUCKET`, `AWS_REGION`,
`AWS_DATA_ROLE_ARN`, `AWS_INFRA_ROLE_ARN`, and `AWS_STORAGE_STACK`. OIDC supplies
temporary credentials; no AWS access keys are stored as repository secrets.
The transfer script uses Python 3.11+ and AWS CLI v2 with conditional S3 writes
(the installed 2.34.22 is supported). It never loads application `.env` files.

## Local backfills

Close any backend/collector writing to SQLite before restoring a snapshot. Pull
into a new file if you need to preserve local work:

```sh
python3 scripts/database_s3.py pull --profile invest-os --database /tmp/invest-os.sqlite
```

To deliberately replace the default local database after saving local changes:

```sh
python3 scripts/database_s3.py pull --profile invest-os --replace-local
```

Run the existing collectors against the restored working database, regenerate
and validate static exports, then persist the database:

```sh
python3 scripts/database_s3.py push --profile invest-os
```

Commit the corresponding publishable JSON and facts as usual. The adjacent
`data/invest_os.sqlite.s3.json` file records the downloaded bucket and ETag;
preserve it during collection. Uploads without a baseline fail. If another
writer updated S3, the upload fails without overwriting their database: save
your local work, pull a new copy, and reapply the backfill. Never bypass this
check by fetching just a newer ETag for an older database.

## Recovery and partial failures

To restore a daily backup, first download the current database into a separate
working file, retaining its `.s3.json` baseline. Download the selected backup
with `aws s3api get-object`, verify its metadata SHA256 against the decompressed
file, and replace only that separate working database. Upload it with the
normal `push` command. The upload checks the current baseline and validates the
restored SQLite file before publishing. Keep a copy of the replaced current
database until recovery is verified.

S3 and Git do not share a transaction. Database upload precedes Git publication,
so a failed Git push/build can leave S3 newer than the website. The next refresh
restores that durable database and regenerates the exports. Review failures
before manually deploying old static data. Simulation checkpoints still require
a successful S3 upload and Git checkpoint before any paid analysis step; the
simulation ledger remains in Git and its existing attempt markers are preserved.

Stopping future LFS uploads does not delete historic GitHub LFS objects or reclaim
their billed storage. Request GitHub Support's assistance to purge retired
objects after the migration is verified. Do not delete/recreate the repository
or rewrite its history as part of this migration.

## Validation

```sh
python3 -m unittest discover -s scripts -p 'test_database_s3.py'
aws cloudformation validate-template --template-body file://infrastructure/storage.json
```

After bootstrap, restore to a temporary location, compare the SHA256, schema,
and table row counts with the source snapshot, and check the bucket's public
access, encryption, lifecycle and role trust policies. Exercise a conditional
write with an obsolete ETag and confirm that AWS rejects it. Do not run the
paid analysis phase as a persistence test.
