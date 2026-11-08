#!/bin/bash
# Build Percona Server for MongoDB (Community) on Linux s390x.
#
# Usage:   ./build-psmdb.sh                # defaults below
#          JOBS=16 HEAP=8g ./build-psmdb.sh  # on a bigger machine
#
# Defaults are tuned for a small 2-vCPU / 4 GB VM (add ~16 GB swap there):
# capped Bazel heap, no debug info, low CPU/IO priority.
set -euo pipefail

TAG=${TAG:-psmdb-8.3.13-4}
VERSION=${TAG#psmdb-}                 # e.g. 8.3.13-4
SRC=${SRC:-$HOME/psmdb}
JOBS=${JOBS:-2}
HEAP=${HEAP:-2g}
TARGETS=${TARGETS:-install-mongod install-mongos //src/mongo/tools:perconadecrypt}
HERE=$(cd "$(dirname "$0")" && pwd)

if [ ! -d "$SRC" ]; then
  git -c advice.detachedHead=false clone --depth 1 --branch "$TAG" \
    https://github.com/percona/percona-server-mongodb.git "$SRC"
  git -C "$SRC" apply "$HERE/patches/$TAG-s390x.patch"
fi

cd "$SRC"
[ -x ~/.local/bin/bazel ] || python3 buildscripts/install_bazel.py
export PATH=~/.local/bin:$PATH

exec nice -n 19 ionice -c3 bazel --host_jvm_args=-Xmx$HEAP build --config=psmdb_opt_release \
  --define=MONGO_VERSION=$VERSION --define=GIT_COMMIT_HASH=$(git rev-parse HEAD) \
  --debug_symbols=False --//bazel/config:allocator=tcmalloc-gperf \
  --jobs=$JOBS --local_resources=cpu=$JOBS --local_resources=memory=HOST_RAM*.7 \
  $TARGETS
