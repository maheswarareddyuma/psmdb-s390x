#!/usr/bin/env python3
"""Replica set + authentication + encryption at rest + hot backup to S3, on one machine.

Starts a 3-member replica set (keyFile internal auth, user auth, encryption at rest),
checks access control, replication, failover, takes a Percona hot backup from a
secondary straight to S3, downloads it, starts mongod on it and verifies the data.
Only touches objects under s3://$S3_BUCKET/psmdb-s390x-test/ and deletes them at the end
(set KEEP_S3=1 to keep them).

Usage:  set -a; . ~/.s3test.env; set +a          # S3_ENDPOINT S3_BUCKET S3_ACCESS_KEY S3_SECRET_KEY
        python rs-s3-test.py [bin_dir]           # needs pymongo, boto3
"""
import os, resource, secrets, shutil, subprocess, sys, tempfile, time
import boto3, pymongo
from botocore.config import Config
from pymongo.errors import OperationFailure

BIN = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/test-results/bin")
PORTS = [27101, 27102, 27103]
E = os.environ
BUCKET, PREFIX = E["S3_BUCKET"], "psmdb-s390x-test/%d" % time.time()
T = tempfile.mkdtemp(prefix="rs-s3-")
ROOT_PW, APP_PW = secrets.token_hex(12), secrets.token_hex(12)
resource.setrlimit(resource.RLIMIT_NOFILE, (64000, resource.getrlimit(resource.RLIMIT_NOFILE)[1]))
s3 = boto3.client("s3", endpoint_url="https://" + E["S3_ENDPOINT"], region_name="us-east-1",
                  aws_access_key_id=E["S3_ACCESS_KEY"], aws_secret_access_key=E["S3_SECRET_KEY"],
                  config=Config(s3={"addressing_style": "path"}))
results = []

def ok(msg):
    results.append(msg); print("PASS", msg, flush=True)

def mongod(port, dbpath, extra=()):
    os.makedirs(dbpath, exist_ok=True)
    subprocess.run([f"{BIN}/mongod", "--port", str(port), "--bind_ip", "127.0.0.1", "--dbpath", dbpath,
                    "--fork", "--logpath", dbpath + ".log", "--wiredTigerCacheSizeGB", "0.25",
                    "--enableEncryption", "--encryptionKeyFile", f"{T}/enc.key", *extra],
                   check=True, stdout=subprocess.DEVNULL)

def shutdown(dbpath):
    subprocess.run([f"{BIN}/mongod", "--dbpath", dbpath, "--shutdown"], stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)

def client(port=None, user=None, pw=None, **kw):
    hosts = f"127.0.0.1:{port}" if port else ",".join(f"127.0.0.1:{p}" for p in PORTS)
    opts = {"directConnection": True} if port else {"replicaSet": "rs0"}
    if user:
        opts.update(username=user, password=pw, authSource="admin")
    return pymongo.MongoClient(f"mongodb://{hosts}/", serverSelectionTimeoutMS=30000, **opts, **kw)

def wait(cond, what, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            if cond():
                return
        except Exception:
            pass
        time.sleep(1)
    raise AssertionError("timed out waiting for " + what)

def denied(fn):
    try:
        fn()
    except OperationFailure as e:
        return e.code in (13, 18)  # Unauthorized, AuthenticationFailed
    return False

try:
    with open(f"{T}/rs.key", "w") as f: f.write(subprocess.check_output(["openssl", "rand", "-base64", "756"], text=True))
    with open(f"{T}/enc.key", "w") as f: f.write(subprocess.check_output(["openssl", "rand", "-base64", "32"], text=True))
    os.chmod(f"{T}/rs.key", 0o600); os.chmod(f"{T}/enc.key", 0o600)

    # 1. replica set with internal (keyFile) auth, which also turns on client auth
    for p in PORTS:
        mongod(p, f"{T}/n{p}", ["--replSet", "rs0", "--keyFile", f"{T}/rs.key"])
    c = client(PORTS[0])
    c.admin.command("replSetInitiate", {"_id": "rs0", "members": [
        # Equal priorities: a higher-priority member would take the primary role back after the
        # failover test, interrupting the S3 backup running on it, which crashes mongod
        # (Percona bug: checkForInterrupt() throws inside the AWS SDK progress callback).
        {"_id": i, "host": f"127.0.0.1:{p}"} for i, p in enumerate(PORTS)]})
    wait(lambda: c.admin.command("hello")["isWritablePrimary"], "primary")
    c.admin.command("createUser", "root", pwd=ROOT_PW, roles=["root"])   # localhost exception
    ok("3-member replica set up with keyFile auth + encryption at rest")

    # 2. authentication and authorization
    root = client(user="root", pw=ROOT_PW, w="majority")
    root.admin.command("createUser", "app", pwd=APP_PW, roles=[{"role": "readWrite", "db": "app"}])
    assert denied(lambda: client().app.c.insert_one({"x": 1})), "unauthenticated write was allowed"
    assert denied(lambda: client(user="root", pw="wrong").admin.command("ping")), "wrong password accepted"
    app = client(user="app", pw=APP_PW, w="majority")
    app.app.c.insert_one({"x": 1})
    assert denied(lambda: app.other.c.insert_one({"x": 1})), "app user wrote outside its database"
    assert denied(lambda: app.admin.command("createUser", "evil", pwd="x", roles=["root"])), "app user created a user"
    ok("auth: anonymous write denied, wrong password denied, readWrite user limited to its db")

    # 3. replication: majority writes, reads from every secondary
    app.app.c.insert_many([{"_id": i, "s": "MARKER-%d" % i, "v": i * 0.5} for i in range(10000)])
    for p in PORTS:
        n = client(p, "root", ROOT_PW)
        wait(lambda: n.app.c.count_documents({}) == 10001, f"replication to {p}")
        assert n.app.c.find_one({"_id": 4321})["v"] == 2160.5
    ok("replication: 10,000 majority writes visible on all 3 members, doubles exact")

    # 4. failover
    old = root.admin.command("hello")["primary"]
    try:
        client(PORTS[0], "root", ROOT_PW).admin.command("replSetStepDown", 60, force=True)
    except Exception:
        pass  # connection is dropped on stepdown
    wait(lambda: root.admin.command("hello").get("primary") not in (None, old), "new primary")
    new = root.admin.command("hello")["primary"]
    app.app.c.insert_one({"_id": "after-failover"})
    assert app.app.c.count_documents({}) == 10002
    ok(f"failover: primary {old} -> {new}, writes continue")

    # 5. hot backup from a secondary straight to S3
    sec = next(p for p in PORTS if f"127.0.0.1:{p}" != new)
    wait(lambda: client(sec, "root", ROOT_PW).app.c.count_documents({}) == 10002, "secondary catch-up")
    t0 = time.time()
    client(sec, "root", ROOT_PW).admin.command("createBackup", s3={
        "bucket": BUCKET, "path": PREFIX, "endpoint": E["S3_ENDPOINT"], "scheme": "HTTPS",
        "useVirtualAddressing": False, "region": "us-east-1",
        "accessKeyId": E["S3_ACCESS_KEY"], "secretAccessKey": E["S3_SECRET_KEY"]})
    objs = [o for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX + "/")
            for o in page.get("Contents", [])]
    size = sum(o["Size"] for o in objs)
    assert objs and any(o["Key"].endswith("WiredTiger") for o in objs), "backup incomplete in S3"
    ok(f"hot backup from secondary 127.0.0.1:{sec} to s3://{BUCKET}/{PREFIX}: "
       f"{len(objs)} files, {size / 1e6:.1f} MB, {time.time() - t0:.0f} s")

    # 6. restore: download, check encryption on disk, start mongod on it, verify data
    R = f"{T}/restore"
    for o in objs:
        dest = os.path.join(R, o["Key"][len(PREFIX) + 1:])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        s3.download_file(BUCKET, o["Key"], dest)
    plain = [f for f in os.listdir(R) if f.startswith("collection-") and b"MARKER-" in open(os.path.join(R, f), "rb").read()]
    assert not plain, f"plaintext found in backup files {plain}"
    mongod(27199, R, ["--auth"])
    r = client(27199, "root", ROOT_PW)
    assert r.app.c.count_documents({}) == 10002
    assert r.app.c.find_one({"_id": 9999})["s"] == "MARKER-9999" and r.app.c.find_one({"_id": "after-failover"})
    assert denied(lambda: client(27199).app.c.find_one()), "restored node allowed anonymous read"
    ok("restore from S3: data files encrypted, mongod starts with the same key, all 10,002 docs and users intact")
    shutdown(R)
finally:
    for p in PORTS:
        shutdown(f"{T}/n{p}")
    if not E.get("KEEP_S3"):
        for page in s3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=PREFIX + "/"):
            for o in page.get("Contents", []):
                s3.delete_object(Bucket=BUCKET, Key=o["Key"])
    LOGS = os.path.expanduser("~/rs-s3-test-logs")   # keep mongod logs for inspection
    shutil.rmtree(LOGS, ignore_errors=True); os.makedirs(LOGS)
    for f in os.listdir(T):
        if f.endswith(".log"):
            shutil.copy(os.path.join(T, f), LOGS)
    shutil.rmtree(T, ignore_errors=True)

print(f"ALL {len(results)} CHECKS PASSED")
