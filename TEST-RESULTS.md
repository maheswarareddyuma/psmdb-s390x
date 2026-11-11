# Test results: Percona Server for MongoDB 8.3.13-4 on s390x

**All 2,954 test files in Percona's and MongoDB's suites passed** on IBM Z (s390x, big-endian). One core test needed a re-run after the test harness's TLS certificates were generated; see below.

## Environment

| | |
|---|---|
| Build | `psmdb-8.3.13-4` + [s390x patch](patches/psmdb-8.3.13-4-s390x.patch), `--config=psmdb_opt_release`, allocator `tcmalloc-gperf` |
| Binaries | the same ones shipped in the [v8.3.13-4 release](https://github.com/maheswarareddyuma/psmdb-s390x/releases/tag/v8.3.13-4) |
| Machine | LinuxONE Community Cloud VM (z/VM), 2 vCPU, 4 GB RAM + 16 GB swap |
| OS | RHEL 9.8, kernel 5.14.0-687.58.1.el9_8.s390x, OpenSSL 3.5.8 |
| Test runner | MongoDB resmoke from the same source tree, `--jobs=1`, via [`run-tests.sh`](run-tests.sh) |
| Date | 2026-11-07 / 08 |

## Results

Counts are test files (`.js`). Resmoke's own totals are higher because they also count fixture setup/teardown and per-test hooks such as collection validation; none of those failed.

| Suite | Source | Tests | Passed | Failed | Time |
|---|---|---:|---:|---:|---:|
| `percona_no_passthrough_with_mongod` | Percona | 1 | 1 | 0 | 5 s |
| `tde_cbc` | Percona: encryption at rest, AES256-CBC | 2 | 2 | 0 | 15 s |
| `tde_gcm` | Percona: encryption at rest, AES256-GCM | 2 | 2 | 0 | 10 s |
| `audit` | Percona: audit log | 30 | 30 | 0 | 2 min |
| `redaction` | Percona: log redaction | 7 | 7 | 0 | 19 s |
| `backup` | Percona: hot backup | 9 | 9 | 0 | 18 s |
| `backup_tde_cbc` | Percona: hot backup, encrypted (CBC) | 11 | 11 | 0 | 1 min |
| `backup_tde_gcm` | Percona: hot backup, encrypted (GCM) | 11 | 11 | 0 | 50 s |
| `core_tde_cbc` | MongoDB core tests with Percona encryption at rest | 1,439 | 1,439 | 0* | 19 min |
| `core` | MongoDB core tests | 1,441 | 1,441 | 0* | 21 min |
| **Total** | | **2,954** | **2,954** | **0** | |

\* `jstests/core/testing/certs_are_generated.js` failed in the full run because the test harness's TLS certificates (`<installDir>/x509/`) hadn't been generated. It checks the harness, not the server. It passed in both suites when re-run after generating the certificates (`*.certs_rerun.json`). `run-tests.sh` now generates them automatically.

## Replica set with authentication, and hot backup to S3

[`rs-s3-test.py`](rs-s3-test.py), run 2026-11-11 against an S3-compatible object store (E2E Networks, path-style addressing, HTTPS). **All 6 checks passed:**

| Check | Result |
|---|---|
| 3-member replica set, keyFile internal auth, encryption at rest on every member | ✅ |
| Anonymous write denied; wrong password denied; `readWrite` user can't write to another db or create users | ✅ |
| 10,000 `w:majority` writes visible on all 3 members; double values exact (big-endian check) | ✅ |
| Failover with `replSetStepDown`: new primary elected, writes continue | ✅ |
| Percona hot backup from a secondary straight to S3 (`createBackup` with `s3`): 58 files, 111.8 MB, 72 s | ✅ |
| Download from S3; collection files encrypted (no plaintext); `mongod --auth` starts on it with the same key; all 10,002 docs and the users intact; anonymous read denied | ✅ |

The S3 transfer hit 8 HTTP timeouts on a slow route (curl code 28). The AWS SDK retried them and the backup completed.

### Bug found: mongod crashes if an S3 backup is interrupted (Percona, not s390x-specific)

In an earlier run, the member taking the backup became primary again mid-upload (priority takeover after the failover test). Instead of failing the `createBackup` command, **mongod terminated**:

```
terminate() called. An exception is active
DBException::toString(): InterruptedDueToReplStateChange: operation was interrupted
  mongo::error_details::throwExceptionForStatus
  Aws::Http::CurlHttpClient::MakeRequest
  ...
  Aws::S3::S3Client::UploadPart
```

Cause: the S3 transfer progress callback in `src/mongo/db/storage/wiredtiger/wiredtiger_kv_engine.cpp` (around line 2672, `psmdb-8.3.13-4`) calls `opCtx->checkForInterrupt()`. That throws a C++ exception from inside the AWS SDK's curl transfer thread, where it can't be caught, so the process aborts. The same would happen on x86_64 and aarch64 on any interruption during an S3 backup: step-down, priority takeover, `killOp`, or shutdown. A fix would use `checkForInterruptNoAssert()` in the callback and cancel the transfer (`backupCancelled`) instead of throwing.

Until it's fixed: run S3 backups on a member that won't become primary during the backup (for example `priority: 0`, or equal priorities with no planned step-downs), and don't kill a running S3 backup.

## Problems found while setting up, and their fixes

A first run (`summary-run1-before-env-fixes.txt`) had 18 failures. All came from the VM's configuration, not from s390x or the build:

| Symptom | Cause | Fix |
|---|---|---|
| Replica-set and sharding tests time out waiting for members (`HostUnreachable ... No route to host`); 16 tests across `tde_*`, `audit`, `redaction`, `backup_tde_*` | the hostname resolves to the VM's public IP, which the cloud network doesn't route back to the VM itself | `127.0.0.1 <hostname>` in `/etc/hosts` |
| `mongod` aborts in the middle of `core` (`WT_PANIC ... Too many open files`), and the rest of the suite is skipped | default open-files limit of 1,024; MongoDB needs ~64,000 (Percona's systemd unit sets 64,000) | `ulimit -n 64000` (now in `run-tests.sh`) |
| `certs_are_generated.js` | test certificates not generated; Bazel's generator needs Rust on s390x | run `x509/mkcert.py` directly (now in `run-tests.sh`) |

## Files

- [`test-results/8.3.13-4/summary.txt`](test-results/8.3.13-4/summary.txt): resmoke's summary line per suite
- [`test-results/8.3.13-4/*.json`](test-results/8.3.13-4/): resmoke reports with every test's status and duration
- Full logs (~560 MB uncompressed): `test-logs-8.3.13-4.tar.xz` in the [release](https://github.com/maheswarareddyuma/psmdb-s390x/releases/tag/v8.3.13-4)

## Not covered

Suites that need external services or more machine: LDAP/Kerberos (`ldapauthz`, `external_auth*`), Vault/KMIP key management, OIDC, the dedicated `replica_sets*`, `sharding*`, `concurrency*`, `aggregation*`, and the C++ unit tests. Run them with `SUITES="..." ./run-tests.sh`.

Also verified separately: RPM install with `dnf`, `mongod` under systemd with SELinux enforcing (no denials), and [`smoke-test.sh`](smoke-test.sh) (encryption at rest, hot backup and restore, audit).
