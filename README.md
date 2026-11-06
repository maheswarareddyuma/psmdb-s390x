# psmdb-s390x

Unofficial, community builds of **Percona Server for MongoDB** (Community edition) for **Linux on IBM Z / LinuxONE (s390x)**.

Percona publishes packages for x86_64 and aarch64 only. This project adds the small changes needed to build on s390x (big-endian) and aims to publish RPMs for RHEL 9 s390x.

> Not affiliated with or endorsed by Percona or MongoDB, Inc. "Percona" and "MongoDB" are trademarks of their respective owners.

## Status

| Version | Build | Tests | Packages |
|---|---|---|---|
| 8.3.13-4 | in progress (RHEL 9.8, s390x) | not yet | not yet |

## What the patch changes

Upstream Percona marks two bundled libraries as x86_64/aarch64-only, which makes Bazel silently skip `mongod` and `mongos` on s390x. [`patches/psmdb-8.3.13-4-s390x.patch`](patches/psmdb-8.3.13-4-s390x.patch):

- **libbson** — adds `build_linux_s390x/` config with big-endian byte order (`BSON_BYTE_ORDER 4321`, `BSON_EXTRA_ALIGN 1`), matching upstream MongoDB's own s390x config.
- **aws-sdk-cpp** (used by hot backup to S3) — adds a `platform/linux_s390x/` config with CPU-specific acceleration off, so the portable C code paths are used.

The build also switches the allocator to `tcmalloc-gperf`, because Percona's default `tcmalloc-google` does not support s390x.

## Build

On RHEL 9 s390x:

```bash
sudo dnf install -y git gcc gcc-c++ make python3.12 libcurl-devel openssl-devel \
  cyrus-sasl-devel openldap-devel krb5-devel xz-devel zlib-devel
git clone https://github.com/maheswarareddyuma/psmdb-s390x.git
cd psmdb-s390x
./build-psmdb.sh                    # small VM defaults (2 jobs, 2 GB Bazel heap)
JOBS=16 HEAP=8g ./build-psmdb.sh    # bigger machine
```

On a 2-vCPU / 4 GB VM, add swap first (about 16 GB) and expect 8–11 hours. Binaries end up in `~/psmdb/bazel-bin/install/bin/` and `~/psmdb/bazel-bin/src/mongo/tools/perconadecrypt`.

## Planned

- Test suite runs on s390x, focusing on Percona features that are new to big-endian: encryption at rest (key file, Vault, KMIP) with `perconadecrypt`, hot backup (local and S3), audit log, LDAP.
- RPM packages for RHEL 9 s390x, signed, in GitHub Releases and a dnf repository.
- CI on IBM Z.

## License

Build scripts in this repository: MIT (see [LICENSE](LICENSE)). Code inside the patches stays under the license of the upstream file it modifies.
Percona Server for MongoDB itself is licensed under the [SSPL](https://github.com/percona/percona-server-mongodb/blob/master/LICENSE-Community.txt); source: https://github.com/percona/percona-server-mongodb
