#!/bin/bash
# Build percona-mongodb-mongosh for RHEL 9 s390x, following Percona's own recipe
# (github.com/percona/mongosh-packaging, percona-mongodb-mongosh-builder.sh):
# MongoDB's Apache-2.0 mongosh source + Percona's patch, which drops the proprietary
# mongosh_crypt_v1.so; client-side encryption support is built from open source.
#
# Needs: sudo dnf install -y git gcc-toolset-13 openssl-devel krb5-devel cmake python3 npm rpm-build
# Compiles Node.js from source: hours on a small machine. Re-run to resume.
# Output: ~/mongosh-build/mongosh/dist/*.rpm and *.tar.gz
set -euo pipefail
VERSION=${VERSION:-2.14.1}
PACKAGING_REF=${PACKAGING_REF:-d7683a15bfd4}     # percona/mongosh-packaging commit
JOBS=${JOBS:-2}
W=${W:-$HOME/mongosh-build}

set +u; source /opt/rh/gcc-toolset-13/enable; set -u
export N_PREFIX=$HOME/.n NPM_CONFIG_PREFIX=$HOME/.npm-global
export PATH=$N_PREFIX/bin:$NPM_CONFIG_PREFIX/bin:$PATH
mkdir -p "$W" && cd "$W"

if [ ! -d mongosh ]; then
  git -c advice.detachedHead=false clone --filter=blob:none --branch "v$VERSION" https://github.com/mongodb-js/mongosh.git
  # As Percona does: the release's version bump lives in a separate commit tagged mongosh@VERSION
  git -C mongosh -c user.name=build -c user.email=build@localhost cherry-pick "$(git -C mongosh rev-list -n 1 "mongosh@$VERSION")"
  curl -sfL "https://raw.githubusercontent.com/percona/mongosh-packaging/$PACKAGING_REF/mongosh.patch" \
    | sed "s:__VERSION__:$VERSION:g" > mongosh.patch
  git -C mongosh apply ../mongosh.patch
fi
cd mongosh
NODE_JS_VERSION=$(grep -oP '(?<="version": ")[^"]*' .evergreen/node-24-latest.json)
echo "mongosh $VERSION, Node.js $NODE_JS_VERSION"

# Same build tooling as Percona's install_npm_modules()
command -v n >/dev/null || npm install -g n
[ "$(node --version 2>/dev/null)" = "v$NODE_JS_VERSION" ] || n "$NODE_JS_VERSION"
npm install -g npm@10 lerna typescript cross-env

[ -d node_modules ] || {
  npm run bootstrap
  npm run mark-ci-required-optional-dependencies
  npm ci --ignore-scripts
}

export NODE_JS_VERSION SEGMENT_API_KEY=dummy BUILD_FLE_FROM_SOURCE=true \
       BOXEDNODE_CONFIGURE_ARGS=--shared-openssl BOXEDNODE_MAKE_ARGS="-j$JOBS" \
       REVISION=$(git rev-parse HEAD)
nice -n 19 npm run compile-exec
for v in rpm-s390x-openssl3 linux-s390x-openssl3; do
  npm run evergreen-release package -- --build-variant=$v
done
ls -la dist/
