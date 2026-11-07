#!/bin/bash
# Smoke test for a PSMDB s390x build: encryption at rest, perconadecrypt,
# hot backup + restore, audit log. Exits non-zero on the first failure.
# Usage: ./smoke-test.sh [bin_dir] [perconadecrypt]   (needs: python3 -m pip install --user pymongo)
set -euo pipefail
BIN=${1:-$HOME/psmdb/bazel-bin/install/bin}
DECRYPT=${2:-$HOME/psmdb/bazel-bin/src/mongo/tools/perconadecrypt}
PY=${PY:-python3}
T=$(mktemp -d); PORT=27999
trap '"$BIN/mongod" --dbpath "$T/db" --shutdown >/dev/null 2>&1 || true; "$BIN/mongod" --dbpath "$T/bk" --shutdown >/dev/null 2>&1 || true; rm -rf "$T"' EXIT
ok(){ echo "PASS $*"; }

"$BIN/mongod" --version | head -1
openssl rand -base64 32 > "$T/key"; chmod 600 "$T/key"
mkdir -p "$T/db" "$T/bk"
start(){ "$BIN/mongod" --dbpath "$1" --port $PORT --bind_ip 127.0.0.1 --fork --logpath "$1.log" \
  --enableEncryption --encryptionKeyFile "$T/key" --wiredTigerCollectionBlockCompressor none \
  --auditDestination file --auditFormat JSON --auditPath "$1.audit.json" >/dev/null; }

start "$T/db"; ok "mongod starts with encryption + audit"

$PY - "$PORT" "$T/bk" <<'EOF'
import sys, pymongo
c = pymongo.MongoClient(port=int(sys.argv[1]))
c.t.c.insert_many([{"_id": i, "secret": "PLAINTEXT-MARKER-%d" % i, "n": i * 1.5} for i in range(1000)])
assert c.t.c.count_documents({}) == 1000
assert c.t.c.find_one({"_id": 7})["n"] == 10.5          # big-endian double round trip
c.t.c.create_index("n")
assert c.t.c.find_one({"n": {"$gt": 1497}})["_id"] == 999
c.admin.command("createBackup", backupDir=sys.argv[2])
print("PASS insert/query/index, createBackup")
EOF

f=$(ls "$T/db"/collection-*.wt | head -1)
! grep -q PLAINTEXT-MARKER "$f" && ok "collection file is encrypted on disk"
# perconadecrypt only handles whole-file master-key encryption (rollback files),
# not WiredTiger page-encrypted collection files; testing it needs a replica-set rollback.
"$DECRYPT" --version >/dev/null && ok "perconadecrypt runs (rollback-file decryption not tested here)"

"$BIN/mongod" --dbpath "$T/db" --shutdown >/dev/null
grep -q '"atype"' "$T/db.audit.json" && ok "audit log written ($(wc -l < "$T/db.audit.json") events)"

start "$T/bk"
$PY - "$PORT" <<'EOF'
import sys, pymongo
c = pymongo.MongoClient(port=int(sys.argv[1]))
assert c.t.c.count_documents({}) == 1000 and c.t.c.find_one({"_id": 999})["secret"] == "PLAINTEXT-MARKER-999"
print("PASS restore from hot backup")
EOF
echo "ALL PASSED"
