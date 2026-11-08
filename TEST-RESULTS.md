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

Suites that need external services or more machine: LDAP/Kerberos (`ldapauthz`, `external_auth*`), Vault/KMIP key management, OIDC, AWS S3 hot backup, `replica_sets*`, `sharding*`, `concurrency*`, `aggregation*`, and the C++ unit tests. Run them with `SUITES="..." ./run-tests.sh`.

Also verified separately: RPM install with `dnf`, `mongod` under systemd with SELinux enforcing (no denials), and [`smoke-test.sh`](smoke-test.sh) (encryption at rest, hot backup and restore, audit).
