# Packages prebuilt Percona Server for MongoDB s390x binaries (see ../build-psmdb.sh).
# Layout, users, service and config follow Percona's own
# percona-packaging/redhat/percona-server-mongodb.spec.template; telemetry is left out.
# Build with ../build-rpm.sh. Pass --define 'with_shell 1' when mongo/mongobridge are built.

%global debug_package %{nil}
# Keep symbols for usable stack traces (binaries are already built without debug info).
%global __strip /bin/true
%define mongo_home /var/lib/mongo

Name:           psmdb-s390x
Version:        8.3.13
Release:        4.unofficial%{?dist}
Summary:        Percona Server for MongoDB for IBM Z / LinuxONE (unofficial community build)
License:        SSPL-1.0
URL:            https://github.com/maheswarareddyuma/psmdb-s390x
ExclusiveArch:  s390x
Source0:        mongod
Source1:        mongos
Source2:        perconadecrypt
Source3:        mongod.conf
Source4:        mongod.service
Source5:        mongod.default
Source6:        percona-server-mongodb-helper.sh
Source7:        percona-server-mongodb-enable-auth.sh
Source8:        mongod.pp
Source9:        LICENSE-Community.txt
Source10:       README.third_party.md
Source11:       mongo
Source12:       mongobridge
Requires:       %{name}-server = %{version}-%{release}
Requires:       %{name}-mongos = %{version}-%{release}

%description
Unofficial community build of Percona Server for MongoDB %{version}-4 for s390x.
Built from https://github.com/percona/percona-server-mongodb tag psmdb-%{version}-4
with the s390x patch from %{url}. Not affiliated with or endorsed by Percona or MongoDB, Inc.

%package server
Summary:        Percona Server for MongoDB database server (s390x, unofficial)
Requires:       openldap, cyrus-sasl-gssapi, cyrus-sasl-plain, curl
Requires(pre):  shadow-utils
Requires(post): policycoreutils
%{?systemd_requires}
Conflicts:      percona-server-mongodb-server, mongodb-org-server
%description server
mongod, perconadecrypt, systemd service and default configuration.

%package mongos
Summary:        Percona Server for MongoDB sharded cluster router (s390x, unofficial)
Conflicts:      percona-server-mongodb-mongos, mongodb-org-mongos
%description mongos
mongos query router for sharded clusters.

%if 0%{?with_shell}
%package shell
Summary:        Percona Server for MongoDB legacy shell (s390x, unofficial)
Requires:       cyrus-sasl-plain
Conflicts:      percona-server-mongodb-shell, mongodb-org-shell
%description shell
The legacy mongo shell, as used by the server test suites.
%endif

%prep
%build

%install
install -D -m 755 %{SOURCE0} %{buildroot}%{_bindir}/mongod
install -D -m 755 %{SOURCE1} %{buildroot}%{_bindir}/mongos
install -D -m 755 %{SOURCE2} %{buildroot}%{_bindir}/perconadecrypt
install -D -m 755 %{SOURCE6} %{buildroot}%{_bindir}/percona-server-mongodb-helper.sh
install -D -m 755 %{SOURCE7} %{buildroot}%{_bindir}/percona-server-mongodb-enable-auth.sh
install -D -m 644 %{SOURCE3} %{buildroot}%{_sysconfdir}/mongod.conf
install -D -m 644 %{SOURCE4} %{buildroot}%{_unitdir}/mongod.service
install -D -m 644 %{SOURCE5} %{buildroot}%{_sysconfdir}/sysconfig/mongod
install -D -m 644 %{SOURCE8} %{buildroot}%{_datadir}/selinux/packages/mongod.pp
%if 0%{?with_shell}
install -D -m 755 %{SOURCE11} %{buildroot}%{_bindir}/mongo
install -D -m 755 %{SOURCE12} %{buildroot}%{_bindir}/mongobridge
%endif
install -d -m 750 %{buildroot}%{mongo_home} %{buildroot}/var/log/mongo
cp %{SOURCE9} %{SOURCE10} .
# Same substitutions Percona's packaging makes for RHEL
sed -i 's|/var/lib/mongodb|/var/lib/mongo|; s|/var/log/mongodb/mongod.log|/var/log/mongo/mongod.log|' %{buildroot}%{_sysconfdir}/mongod.conf
sed -i 's|@@LOCATION@@|sysconfig|g; s|@@LOGDIR@@|mongo|g' \
  %{buildroot}%{_unitdir}/mongod.service %{buildroot}%{_sysconfdir}/sysconfig/mongod \
  %{buildroot}%{_bindir}/percona-server-mongodb-helper.sh

%pre server
getent group mongod >/dev/null || groupadd -r mongod
getent passwd mongod >/dev/null || useradd -M -r -g mongod -d %{mongo_home} -s /sbin/nologin -c mongod mongod
exit 0

%pre mongos
getent group mongod >/dev/null || groupadd -r mongod
getent passwd mongod >/dev/null || useradd -M -r -g mongod -d %{mongo_home} -s /sbin/nologin -c mongod mongod
exit 0

%post server
%systemd_post mongod.service
semodule -i %{_datadir}/selinux/packages/mongod.pp >/dev/null 2>&1 || :
echo " * Start with: systemctl start mongod   (access control is off by default;"
echo "   run /usr/bin/percona-server-mongodb-enable-auth.sh to enable it)"

%preun server
%systemd_preun mongod.service

%postun server
%systemd_postun_with_restart mongod.service

%files

%files server
%license LICENSE-Community.txt
%doc README.third_party.md
%{_bindir}/mongod
%{_bindir}/perconadecrypt
%{_bindir}/percona-server-mongodb-helper.sh
%{_bindir}/percona-server-mongodb-enable-auth.sh
%{_unitdir}/mongod.service
%{_datadir}/selinux/packages/mongod.pp
%config(noreplace) %{_sysconfdir}/mongod.conf
%config(noreplace) %{_sysconfdir}/sysconfig/mongod
%attr(0750,mongod,mongod) %dir %{mongo_home}
%attr(0750,mongod,mongod) %dir /var/log/mongo
%if 0%{?with_shell}
%{_bindir}/mongobridge
%endif

%files mongos
%license LICENSE-Community.txt
%{_bindir}/mongos

%if 0%{?with_shell}
%files shell
%license LICENSE-Community.txt
%{_bindir}/mongo
%endif

%changelog
* Sat Nov 07 2026 maheswarareddyuma - 8.3.13-4.unofficial
- First s390x build of Percona Server for MongoDB 8.3.13-4
