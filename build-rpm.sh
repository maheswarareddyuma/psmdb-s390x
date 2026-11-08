#!/bin/bash
# Package the binaries built by build-psmdb.sh into RPMs (needs: dnf install rpm-build).
# Output: ~/rpmbuild/RPMS/s390x/*.rpm
set -euo pipefail
SRC=${SRC:-$HOME/psmdb}
HERE=$(cd "$(dirname "$0")" && pwd)
S=$HOME/rpmbuild/SOURCES
mkdir -p "$S"
B=$SRC/bazel-bin
cp -fL "$B/install/bin/mongod" "$B/install/bin/mongos" "$B/src/mongo/tools/perconadecrypt" "$S/"
cp -f "$SRC"/percona-packaging/conf/{mongod.conf,mongod.service,mongod.default,percona-server-mongodb-helper.sh,percona-server-mongodb-enable-auth.sh} \
      "$SRC/percona-packaging/redhat/mongod.pp" "$SRC/LICENSE-Community.txt" "$SRC/README.third_party.md" "$S/"
shell=()
if [ -x "$B/install/bin/mongo" ]; then
  cp -fL "$B/install/bin/mongo" "$S/"
  cp -fL "$(find -L "$B/src/mongo/tools/mongobridge_tool" -maxdepth 1 -name mongobridge -type f | head -1)" "$S/"
  shell=(--define "with_shell 1")
else
  touch "$S/mongo" "$S/mongobridge"   # placeholders; not packaged without with_shell
fi
rpmbuild -bb "${shell[@]}" "$HERE/rpm/psmdb-s390x.spec"
ls -la "$HOME"/rpmbuild/RPMS/s390x/
