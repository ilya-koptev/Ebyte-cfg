# EBYTE LAN configuration protocol (write path)

Reverse-engineered from vendor-tool captures and validated on **NE2-D11 /
FW-9167-0-11**. Everything is **UDP broadcast**; no device-side feature has to be
enabled.

## Transport

- Controller socket: `bind(("", 1902))`, `SO_REUSEADDR`, `SO_BROADCAST`,
  `SO_BINDTODEVICE = <iface>` (e.g. `eth1`). Send to `255.255.255.255:1901`.
- Because it is link-level broadcast bound to the interface, discovery/read/write
  work **regardless of the device's IP subnet**.

## Frame format

```
[opcode:2][MAC:6][seq:2 big-endian][crc:2][data ...]
```

- `crc` = **CRC16/MODBUS over `data`** (i.e. `payload[12:]`), stored **little-endian**
  in `payload[10:12]`.
- Opcodes: `fe 00` read, `fe 01` write, `fe 03` apply/reboot.
  Replies: `fd 00` config page, `fd 01` write-ACK, `fd 03` apply-ACK, `fd 06` announce.

```python
def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF
```

## Discovery

Send the 30-byte magic `b"www.cdebyte.com" * 2` to `:1901`. Every EBYTE replies
(`fd 06` announce) to `:1902`; the **device IP is the source IP** of its reply.

## The config is 7 pages — `seq` is the PAGE INDEX (0..6), not a counter

Poll `fe 00 + MAC + seq + 00*8` for `seq = 0..6`; the device answers `fd 00` frames:

| seq | size  | contents                                            |
|-----|-------|-----------------------------------------------------|
| 0   | 96 B  | identity: model / firmware / serial                 |
| 1   | 1036 B| **main config**: network, serial, Modbus, Link 1    |
| 2   | 1036 B| **Link 2** + HTTP/MQTT socket B                     |
| 3–5 | 1036 B| HTTP / MQTT parameters                              |
| 6   | 128 B | reserve                                             |

Offsets in [registers.md](registers.md) are into the **frame payload** of the
relevant page (12-byte header included).

## Writing

1. Read the current config (all pages).
2. Patch the target bytes in the relevant page; **do not touch page-1 payload
   `0x10` (data-bits)** with an out-of-range value — that **hard-bricks the
   device** (firmware hangs on boot, Ethernet/serial dead, reset button ignored).
3. Send `fe 01 + MAC + seq + crc + data` for **every page**, **twice** (the vendor
   tool sends two identical rounds — the device latches config on the confirming
   round). Each page is ACKed with `fd 01`.
4. Send `fe 03 + MAC + 0x1101 + 00*8` (apply/reboot).

Writes commit to **flash immediately** (proven: value survives a power cycle).

### Two important quirks

- **The change only takes effect after a full reboot.** The device loads flash into
  its running config on boot; a read right after a write still shows the *old*
  running value. `fe 03` is meant to reboot but is **unreliable** on this unit — so
  this project applies changes by **power-cycling V_OUT**
  (`/devices/wb-gpio/controls/V_OUT`) and then re-reading.
- **The `payload[0x0C:0x0E]` word is NOT a validated checksum.** The vendor app
  writes a value there, but the device **zeroes it on boot and runs fine** — so it
  can be left alone when writing. (The device does validate the per-frame
  CRC16 at `[10:12]`, which this tool always recomputes.)

## Control-frame examples

```
read  page 1 : fe 00 <MAC> 00 01 00 00 00 00 00 00
write ACK    : fd 01 <MAC> <seq> 00 01 00 00 00 00 00 00
apply        : fe 03 <MAC> 11 01 00 00 00 00 00 00
announce     : fd 06 <MAC> 11 00 00 00 00 00 00 00
```
