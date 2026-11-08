#!/bin/bash
# Run Percona's and MongoDB's resmoke test suites against the s390x build.
# Needs: the build from build-psmdb.sh plus the test shell:
#   TARGETS="install-mongo //src/mongo/tools/mongobridge_tool:mongobridge" ./build-psmdb.sh
# and a Python venv with resmoke's dependencies (see README).
# Results: $OUT/<suite>.log, $OUT/<suite>.json, and one line per suite in $OUT/summary.txt
set -uo pipefail
SRC=${SRC:-$HOME/psmdb}
OUT=${OUT:-$HOME/test-results}
VENV=${VENV:-$HOME/rvenv}
JOBS=${JOBS:-1}
SUITES=${SUITES:-"percona_no_passthrough_with_mongod tde_cbc tde_gcm audit redaction backup backup_tde_cbc backup_tde_gcm core_tde_cbc core"}

# mongod needs many open files (Percona's systemd unit uses 64000); the default 1024
# makes WiredTiger panic with "Too many open files" partway through the core suite.
ulimit -n 64000 || { echo "raise the open-files hard limit to >= 64000 first"; exit 1; }
# Replica-set tests connect via the machine's hostname; it must resolve to an address
# the machine can reach itself (cloud VMs often can't reach their own public IP).
getent ahostsv4 "$(hostname)" | head -1 | grep -q '^127\.' || \
  echo "WARNING: $(hostname) does not resolve to loopback; replica-set tests may fail (add '127.0.0.1 $(hostname)' to /etc/hosts)"

B=$SRC/bazel-bin; BIN=$OUT/bin
mkdir -p "$BIN" "$OUT/data"
cp -fL "$B"/install/bin/{mongod,mongos,mongo} "$B/src/mongo/tools/perconadecrypt" \
       "$B/src/mongo/tools/mongobridge_tool/mongobridge" "$BIN/"
. "$VENV/bin/activate"
cd "$SRC"
# Test TLS certificates, expected in <installDir>/x509. Bazel's //x509:generate_main_certificates
# needs Rust on s390x (no pinned cryptography wheel), so run its generator script directly.
if [ ! -f "$BIN/x509/ca.pem" ]; then
  python -c 'import json, types; ns = {"json": types.SimpleNamespace(encode=json.dumps)}; exec(open("x509/main_certs_def.bzl").read(), ns); print(ns["certs_def"])' > "$OUT/certs.json"
  mkdir -p "$BIN/x509"
  python x509/mkcert.py "$OUT/certs.json" --mkcrl --quiet --output "$BIN/x509" > /dev/null
fi
for s in $SUITES; do
  start=$(date +%s)
  python buildscripts/resmoke.py run --suites="$s" --installDir="$BIN" --dbpathPrefix="$OUT/data" \
    --jobs="$JOBS" --continueOnFailure --reportFile="$OUT/$s.json" > "$OUT/$s.log" 2>&1
  rc=$?
  rm -rf "$OUT/data"/*
  r=$(grep -oP "Summary of $s suite: \K.*" "$OUT/$s.log" | tail -1)
  echo "$(date '+%F %T')  $s  exit=$rc  $(( ($(date +%s)-start)/60 ))min  $r" | tee -a "$OUT/summary.txt"
done
