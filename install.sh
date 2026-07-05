#!/bin/bash
# Install the EBYTE serial-server configurator on a Wiren Board controller.
#
#   sudo bash install.sh [IFACE] [RS485_PORT]
#
# Defaults (Wiren Board 8): IFACE=eth1 (Ethernet 2), RS485_PORT=/dev/ttyRS485-2.
# On other controllers check `ip link` and `ls -l /dev/ttyRS485*` and pass args, e.g.:
#   sudo bash install.sh eth0 /dev/ttyRS485-1
set -e

IFACE="${1:-eth1}"
PORT485="${2:-/dev/ttyRS485-2}"
DEST=/mnt/data/root/ebyte
SRC="$(cd "$(dirname "$0")" && pwd)/src"

echo "Installing EBYTE configurator (iface=$IFACE, rs485=$PORT485)..."
mkdir -p "$DEST"
cp "$SRC/ebyte_core.py" "$DEST/"
cp "$SRC/ebyte_cli.py"  "$DEST/"
# patch the interface / RS-485 port constants
sed -i "s#^IFACE = .*#IFACE = \"$IFACE\"#"       "$DEST/ebyte_cli.py"
sed -i "s#^PORT485 = .*#PORT485 = \"$PORT485\"#"  "$DEST/ebyte_cli.py"
rm -rf "$DEST/__pycache__"
cp "$SRC/ebyte_config.js" /etc/wb-rules/

echo "Done."
echo "  engine + CLI -> $DEST"
echo "  wb-rules device -> /etc/wb-rules/ebyte_config.js (auto-reloads)"
echo "Open homeui -> Devices -> 'EBYTE configurator'."
