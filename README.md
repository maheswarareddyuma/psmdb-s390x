# psmdb-s390x

Unofficial community builds of **Percona Server for MongoDB** (Community edition) for **Linux on IBM Z / LinuxONE (s390x)**: RPMs, plain binaries, the patch and scripts to build them yourself, and test results from Percona's and MongoDB's own test suites.

Percona publishes packages for x86_64 and aarch64 only. This project adds the small source changes needed for s390x (big-endian).

> **Unofficial.** Not affiliated with or endorsed by Percona or MongoDB, Inc. "Percona" and "MongoDB" are trademarks of their respective owners. Test it yourself before trusting production data to it.

## Status

| Version | Platform | Build | Tests | Packages |
|---|---|---|---|---|
| 8.3.13-4 | RHEL 9.8, s390x | ✅ | ✅ 2,954 / 2,954 test files passed ([TEST-RESULTS.md](TEST-RESULTS.md)) | [Release](https://github.com/maheswarareddyuma/psmdb-s390x/releases/tag/v8.3.13-4) |

`mongod --version` reports `8.3.13-4`, `distarch: s390x`, allocator `tcmalloc-gperf`, and every Percona feature: TDE (encryption at rest), HotBackup, Auditing, LDAP, Kerberos, OIDC, AWS IAM, MemoryEngine, FIPSMode, LogRedaction, ngram.

## Install (RHEL 9 s390x)

Requirements: RHEL 9 (or a rebuild) on s390x with **OpenSSL 3.4 or newer**. Tested on RHEL 9.8, which ships OpenSSL 3.5.

```bash
V=8.3.13-4; R=https://github.com/maheswarareddyuma/psmdb-s390x/releases/download/v$V
sudo dnf install -y \
  $R/psmdb-s390x-$V.unofficial.el9.s390x.rpm \
  $R/psmdb-s390x-server-$V.unofficial.el9.s390x.rpm \
  $R/psmdb-s390x-mongos-$V.unofficial.el9.s390x.rpm
sudo systemctl enable --now mongod
```

| Package | Contents |
|---|---|
| `psmdb-s390x-server` | `mongod`, `perconadecrypt`, `mongobridge`, systemd unit, `/etc/mongod.conf`, SELinux module, Percona helper scripts |
| `psmdb-s390x-mongos` | `mongos` |
| `psmdb-s390x-shell` | legacy `mongo` shell (used by the test suites; use `mongosh` for day-to-day work) |
| `psmdb-s390x` | metapackage: server + mongos |

Data goes in `/var/lib/mongo` and logs in `/var/log/mongo`, as with Percona's own RHEL packages. Access control is **off** by default; run `sudo percona-server-mongodb-enable-auth.sh` to turn it on. The packages conflict with Percona's and MongoDB's official packages because they install the same files.

**Plain binaries**: `psmdb-8.3.13-4-s390x-el9.tar.xz` in the release has `bin/{mongod,mongos,mongo,mongobridge,perconadecrypt}`. Verify downloads with `SHA256SUMS`.

## Build it yourself

Tested on RHEL 9.8 s390x with 2 vCPU, 4 GB RAM and 50 GB disk. On that machine a full build takes about **18 hours**; with 8+ vCPU and 16+ GB RAM, expect 2–3 hours.

### 1. Prerequisites

```bash
sudo dnf install -y git gcc gcc-c++ make python3.12 python3.12-devel libcurl-devel openssl-devel \
  cyrus-sasl-devel openldap-devel krb5-devel xz-devel zlib-devel rpm-build
```

Bazel downloads its own GCC 14 toolchain, so the system compiler version doesn't matter.

On a small machine (≤ 8 GB RAM), add swap first, or compiler processes get killed for running out of memory:

```bash
sudo fallocate -l 16G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap defaults 0 0' | sudo tee -a /etc/fstab
```

### 2. Build mongod, mongos and perconadecrypt

```bash
git clone https://github.com/maheswarareddyuma/psmdb-s390x.git
cd psmdb-s390x
./build-psmdb.sh                     # small-machine defaults: 2 jobs, 2 GB Bazel heap
JOBS=8 HEAP=6g ./build-psmdb.sh      # bigger machine
```

`build-psmdb.sh` clones tag `psmdb-8.3.13-4` into `~/psmdb`, applies [the s390x patch](patches/psmdb-8.3.13-4-s390x.patch), installs Bazel, and builds with Percona's release profile (`--config=psmdb_opt_release`: optimized, statically linked, Community only). Outputs:

- `~/psmdb/bazel-bin/install/bin/{mongod,mongos}`
- `~/psmdb/bazel-bin/src/mongo/tools/perconadecrypt`

Run it inside `tmux`/`screen` or with `nohup`, because it takes hours. If it stops, run it again: Bazel reuses everything already compiled.

| Problem | Fix |
|---|---|
| `Killed signal terminated program cc1plus` | `JOBS=1 ./build-psmdb.sh` (and check swap) |
| `bazel ran out of memory` / `Java heap space` | `HEAP=3g ./build-psmdb.sh` |
| `Target //:install-mongod was skipped` | the patch wasn't applied; `cd ~/psmdb && git apply ~/psmdb-s390x/patches/psmdb-8.3.13-4-s390x.patch` |

### 3. Build the test shell (needed for the tests and the shell RPM)

```bash
TARGETS="install-mongo //src/mongo/tools/mongobridge_tool:mongobridge" ./build-psmdb.sh
```

### 4. Build the RPMs

```bash
./build-rpm.sh        # writes ~/rpmbuild/RPMS/s390x/*.rpm
```

[`rpm/psmdb-s390x.spec`](rpm/psmdb-s390x.spec) packages the binaries with Percona's own config, systemd unit, helper scripts and SELinux module, following Percona's `percona-server-mongodb.spec.template`. Percona's telemetry agent is left out.

## Run the tests

Quick smoke test (about 1 minute): encryption at rest, hot backup and restore, audit log.

```bash
python3.12 -m pip install --user pymongo
PY=python3.12 ./smoke-test.sh
```

Percona's and MongoDB's official test suites, using MongoDB's test runner (resmoke):

```bash
python3.12 -m venv ~/rvenv
~/rvenv/bin/pip install -r requirements-resmoke.txt
./run-tests.sh                                   # all suites below, one after another
SUITES="tde_cbc audit" ./run-tests.sh            # pick suites
```

Replica set with authentication, encryption at rest, failover, and hot backup to S3 plus restore (about 5 minutes; touches only `psmdb-s390x-test/` in the bucket and cleans up):

```bash
cat > ~/.s3test.env <<'EOF'      # chmod 600; never commit this file
S3_ENDPOINT=objectstore.example.com
S3_BUCKET=my-bucket
S3_ACCESS_KEY=...
S3_SECRET_KEY=...
EOF
chmod 600 ~/.s3test.env
set -a; . ~/.s3test.env; set +a; ~/rvenv/bin/python rs-s3-test.py
```

Results go to `~/test-results/`: one `.log` and one `.json` report per suite, plus `summary.txt`. The default suites:

| Suite | Source | What it covers |
|---|---|---|
| `percona_no_passthrough_with_mongod` | Percona | Percona-specific server tests |
| `tde_cbc`, `tde_gcm` | Percona | encryption at rest: wrong keys, key files, replica sets |
| `audit` | Percona | audit log |
| `redaction` | Percona | log redaction |
| `backup`, `backup_tde_cbc`, `backup_tde_gcm` | Percona | hot backup, plain and encrypted |
| `core_tde_cbc` | MongoDB core tests, Percona encryption config | ~1,450 core tests with encryption at rest on |
| `core` | MongoDB | ~1,450 core tests |

All of them together take about 1 hour on a 2-vCPU machine. Use `JOBS=N` on bigger machines.

Before running, on the test machine:

- **Open files:** `run-tests.sh` raises its limit to 64,000 (MongoDB needs that many). If the hard limit is lower, raise it in `/etc/security/limits.conf` first.
- **Hostname:** replica-set tests connect through the machine's hostname. If it resolves to an address the machine can't reach itself (common on cloud VMs: `No route to host`), add `127.0.0.1 <hostname>` to `/etc/hosts`. The script warns when this looks wrong.
- **TLS test certificates** are generated automatically into `~/test-results/bin/x509`.

## What the patch changes

Percona's bundled libraries only carry x86_64/aarch64 configuration. Two are marked x86/ARM-only, which makes Bazel **silently skip** `mongod` and `mongos` on s390x while still reporting success; a third has no s390x `config.h`. [`patches/psmdb-8.3.13-4-s390x.patch`](patches/psmdb-8.3.13-4-s390x.patch):

- **libbson**: adds a `build_linux_s390x/` config with big-endian byte order (`BSON_BYTE_ORDER 4321`, `BSON_EXTRA_ALIGN 1`), matching upstream MongoDB's own s390x config.
- **aws-sdk-cpp** (hot backup to S3): adds a `platform/linux_s390x/` config with CPU-specific acceleration off, so the portable C code is used.
- **libarchive** (hot backup): adds `platform/build_linux_s390x/config.h`. The x86_64 and aarch64 configs are identical and libarchive handles byte order in portable code.

The build also uses the `tcmalloc-gperf` allocator, because Percona's default `tcmalloc-google` doesn't support s390x.

## Known issue

**An interrupted S3 hot backup crashes mongod** (Percona bug, every platform): a step-down, priority takeover, `killOp` or shutdown during `createBackup` to S3 terminates the server instead of failing the command. Run S3 backups on a member that won't become primary meanwhile. Details in [TEST-RESULTS.md](TEST-RESULTS.md#bug-found-mongod-crashes-if-an-s3-backup-is-interrupted-percona-not-s390x-specific).

## Not tested yet

`perconadecrypt` on a real rollback file, Vault/KMIP key servers, LDAP/Kerberos, OIDC, the dedicated `replica_sets*`/`sharding*`/`concurrency*` suites, C++ unit tests, and long-running stress tests.

## License

Build scripts and spec in this repository: MIT (see [LICENSE](LICENSE)). Code inside the patch stays under the license of the upstream file it modifies. Percona Server for MongoDB itself is licensed under the [SSPL](https://github.com/percona/percona-server-mongodb/blob/master/LICENSE-Community.txt); source: https://github.com/percona/percona-server-mongodb (tag `psmdb-8.3.13-4`).
