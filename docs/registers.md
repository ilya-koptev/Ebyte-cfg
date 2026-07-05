# Register / config-byte map (NE2-D11)

Offsets are into the **UDP frame payload** of a config page (the 12-byte frame
header is included, so `payload[0x10]` = `data[0x04]`). Reverse-engineered by
diffing single-setting changes made in the vendor app.

> ⚠️ **`page1 payload 0x10` (data bits) is dangerous.** Valid codes are `0..3`
> (= 5..8 bits). Writing an out-of-range value (e.g. `0x05`) **hard-bricks the
> device**: firmware hangs on boot, Ethernet/serial go dead, the reset button is
> ignored. The tool validates this on write.

## Page 1 — main config

### Network
| Field    | Payload | Type              | Notes                     |
|----------|---------|-------------------|---------------------------|
| IP       | `0xA8`  | IPv4, 4 B big-end | Local IP                  |
| Gateway  | `0xAC`  | IPv4              |                           |
| Netmask  | `0xB0`  | IPv4              |                           |
| DNS1     | `0xB4`  | IPv4              |                           |
| DNS2     | `0xB8`  | IPv4              |                           |
| DHCP     | `0xBC`  | byte              | `0` static, `1` DHCP      |
| Reconnect| `0xBE`  | byte              | reconnection time, sec    |

### Serial
| Field     | Payload | Type | Codes |
|-----------|---------|------|-------|
| Data bits | `0x10`  | byte | `0`=5 `1`=6 `2`=7 `3`=8  ⚠️ |
| Stop bits | `0x11`  | byte | bit1: `0x01`=1, `0x03`=2 (with 8 data bits) |
| Parity    | `0x12`  | byte | `0`=None `2`=Even `3`=Odd |
| Baud      | `0x14`  | byte | `1`=1200 `2`=2400 `3`=4800 `4`=9600 `5`=19200 `6`=38400 `7`=57600 `8`=115200 `9`=230400 `0A`=460800 |

### Serial keepalive / heartbeat
| Field           | Payload | Type | Codes |
|-----------------|---------|------|-------|
| Heartbeat mode  | `0x20`  | byte | `0`=Disable `1`=SN `2`=Send MAC `3`=send Customize |
| Heartbeat cycle | `0x24`  | byte | seconds |

### Modbus gateway
| Field            | Payload | Type      | Codes |
|------------------|---------|-----------|-------|
| Gateway mode     | `0xE8`  | byte      | `0`=disable(transparent) `1`=Simple converion `2`=Multihost `3`=Storable `4`=Configurable `5`=AutoUpdate |
| TCP↔RTU          | `0xEA`  | byte      | `0`/`1` — **independent** of `0xE8` |
| RTU timeout      | `0xE4`  | u16 LE    | ms |
| Polling interval | `0xE6`  | u16 LE    | ms |
| Keep time        | `0xE9`  | byte      | seconds |

### Net AT / login
| Field         | Payload | Type        | Notes |
|---------------|---------|-------------|-------|
| Net AT enable | `0xC2`  | byte        | `0`/`1` |
| Net AT header | `0xC3`  | ASCII (~9)  | default `NETAT` |
| Login user    | `0xCF`  | ASCII (~10) | default `admin` |
| Login pass    | `0xDA`  | ASCII (~10) | default `admin` |

### Link 1 (Socket A)
| Field       | Payload | Type   | Codes |
|-------------|---------|--------|-------|
| Work mode   | `0x319` | byte   | `0`=Disable `1`=TCP client `2`=TCP server `3`=UDP client `4`=UDP server `5`=Mqtt client `6`=HTTP client |
| Remote addr | `0x218` | ASCII  | IP or domain |
| Remote port | `0x31C` | u16 LE |       |
| Local port  | `0x320` | u16 LE |       |

## Page 2 — Link 2 (Socket B)
Same fields as Link 1, on page 2, at different offsets:

| Field       | Payload | Type   |
|-------------|---------|--------|
| Work mode   | `0x139` | byte (same enum as Link 1) |
| Remote addr | `0x38`  | ASCII  |
| Remote port | `0x13C` | u16 LE |
| Local port  | `0x140` | u16 LE |

## Other
- `page1 payload 0x0C:0x0E` — app-written word, **not validated** by the device
  (zeroed on boot). Leave alone; only the per-frame CRC16 at `[10:12]` matters.
- Pages 3–5 hold HTTP (`/1.php?`, `User-Agent`) and MQTT (client id, topics,
  password) parameters — present in the config but not yet exposed in the dashboard.
