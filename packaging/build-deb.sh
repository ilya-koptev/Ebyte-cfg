#!/bin/bash
# Build ebyte-cfg_<version>_all.deb from src/. Run on any Debian host (needs dpkg-deb).
#   bash packaging/build-deb.sh [version]
set -e

VERSION="${1:-1.0.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$(mktemp -d)"
PKG="$BUILD/ebyte-cfg"

mkdir -p "$PKG/DEBIAN" \
         "$PKG/mnt/data/root/ebyte" \
         "$PKG/etc/wb-rules" \
         "$PKG/etc/default"

# payload
cp "$ROOT/src/ebyte_core.py" "$ROOT/src/ebyte_cli.py" "$PKG/mnt/data/root/ebyte/"
cp "$ROOT/src/ebyte_config.js" "$PKG/etc/wb-rules/"
cat > "$PKG/etc/default/ebyte-cfg" <<EOF
# EBYTE configurator settings (edit for your hardware; preserved across upgrades)
IFACE="eth1"
PORT485="/dev/ttyRS485-2"
EOF

# control
cat > "$PKG/DEBIAN/control" <<EOF
Package: ebyte-cfg
Version: $VERSION
Section: utils
Priority: optional
Architecture: all
Depends: python3, wb-rules, mosquitto-clients
Maintainer: Ilya Koptev <ilya.koptev@struhe.com>
Description: EBYTE serial-server configurator for Wiren Board (homeui device)
 Discover and configure EBYTE NE2-D11 RS-485 <-> Ethernet serial servers from a
 Wiren Board controller via a native homeui device.
EOF

# keep user's /etc/default/ebyte-cfg on upgrade
echo "/etc/default/ebyte-cfg" > "$PKG/DEBIAN/conffiles"

cat > "$PKG/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
rm -rf /mnt/data/root/ebyte/__pycache__ 2>/dev/null || true
echo "ebyte-cfg installed. homeui -> Devices -> 'EBYTE configurator'."
exit 0
EOF
chmod 755 "$PKG/DEBIAN/postinst"

OUT="$ROOT/ebyte-cfg_${VERSION}_all.deb"
# gzip compression: newer dpkg-deb defaults to zstd, which the older dpkg on
# Wiren Board can't unpack ("unknown compression for member control.tar.zst").
dpkg-deb -Zgzip --build --root-owner-group "$PKG" "$OUT"
echo "Built $OUT"
