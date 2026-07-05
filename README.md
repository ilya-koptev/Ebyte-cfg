# EBYTE serial-server configurator for Wiren Board

Find, read and configure **EBYTE NE2-D11** (RS-485 ↔ Ethernet serial server)
devices from a Wiren Board controller — as a native **homeui device** (no extra
web page). Discovers a device on Ethernet 2, shows every setting, lets you edit
and write them back, then verifies the config and the RS-485 link.

It talks the vendor's own UDP LAN protocol (reverse-engineered), so **nothing has
to be enabled on the device** and no vendor Windows tool is needed.

![tabs: network, serial, modbus, link1/2, net at](docs/dashboard.md)

## Features

- **Search** an EBYTE on Ethernet 2 (broadcast discovery — finds it even with an
  unknown/wrong IP).
- Read & edit **all** settings: network (+DHCP), serial (baud/databit/parity/stop
  + heartbeat), Modbus gateway (mode / TCP↔RTU / timeouts), two socket **Links**,
  reconnection, Net AT — all with dropdowns matching the vendor app.
- **Default** button loads a known-good template; **Write** flashes the device,
  reboots it (via V_OUT), reads it back to **verify**, and runs an **RS-485 bridge
  test**.
- Safe: writes are byte-validated (e.g. an out-of-range data-bits value can brick
  the device — the tool refuses it).

## Install (on the controller)

```sh
git clone https://github.com/ilya-koptev/Ebyte-cfg.git
cd Ebyte-cfg
sudo bash install.sh                 # WB8 defaults: eth1 + /dev/ttyRS485-2
# other hardware: sudo bash install.sh <iface> <rs485-port>
```

That copies the engine + CLI to `/mnt/data/root/ebyte/` and the virtual device to
`/etc/wb-rules/`. wb-rules auto-reloads — open **homeui → Devices → “EBYTE
configurator”**.

## Requirements

- Wiren Board controller (tested on **WB8**, `wb-rules` 2.40) with `mosquitto`,
  `python3`, homeui.
- The EBYTE plugged into **Ethernet 2** (config port) and its RS-485 into
  **RS485-2**, powered from **V_OUT** (needed for the reboot/verify step).

## Documentation

- [Dashboard usage](docs/dashboard.md) — connect, search, default, change IP, write, verify.
- [Write protocol](docs/protocol.md) — UDP framing, pages, read/write/apply, flash model.
- [Register map](docs/registers.md) — every decoded config byte with codes.

## Layout

```
src/ebyte_core.py    UDP protocol engine (discover / read / write) + byte decode
src/ebyte_cli.py     CLI used by the wb-rules device (read / write / rs485test)
src/ebyte_config.js  wb-rules virtual device (the homeui UI)
install.sh           installer
docs/                protocol, registers, dashboard docs
```

## Notes & limitations

- Config byte offsets were reverse-engineered on **NE2-D11 / FW-9167-0-11**. Other
  EBYTE models may differ.
- Serial params apply only after a **full device reboot** (the tool power-cycles
  V_OUT). The RS-485 verify test only passes in **transparent** Modbus mode.
- Not affiliated with EBYTE / Chengdu Ebyte.
