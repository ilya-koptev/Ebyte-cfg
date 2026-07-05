#!/bin/bash
# Install the EBYTE serial-server configurator on a Wiren Board controller
# (manual / from-source install; for apt-based updates see docs/apt.md).
#
#   sudo bash install.sh [IFACE] [RS485_PORT]
#
# Defaults (Wiren Board 8): IFACE=eth1 (Ethernet 2), RS485_PORT=/dev/ttyRS485-2.
# Other controllers: check `ip link` and `ls -l /dev/ttyRS485*`, e.g.:
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
rm -rf "$DEST/__pycache__"
cp "$SRC/ebyte_config.js" /etc/wb-rules/

# interface / RS-485 port live in a conffile (read by ebyte_cli.py; survives upgrades)
if [ ! -f /etc/default/ebyte-cfg ]; then
    cat > /etc/default/ebyte-cfg <<EOF
# EBYTE configurator settings
IFACE="$IFACE"
PORT485="$PORT485"
EOF
else
    echo "Keeping existing /etc/default/ebyte-cfg"
fi

echo "Done."
echo "  engine + CLI    -> $DEST"
echo "  wb-rules device -> /etc/wb-rules/ebyte_config.js (auto-reloads)"
echo "  settings        -> /etc/default/ebyte-cfg"
echo "Open homeui -> Devices -> 'EBYTE configurator'."
