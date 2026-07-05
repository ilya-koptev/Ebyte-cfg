#!/usr/bin/env python3
"""
EBYTE serial-server protocol engine (discover + read + write).

Pure logic used by ebyte_cli.py (which the wb-rules homeui device drives).
No web server / no HTML — that standalone dashboard was removed.

Protocol (reverse-engineered from vendor captures, validated on NE2-D11):
  transport : UDP broadcast on IFACE. bind :1902, send to 255.255.255.255:1901.
  discover  : send  b"www.cdebyte.com"*2  -> :1901 ; device IP = reply src IP.
  frame     : [op:2][MAC:6][seq:2 BE][crc:2 = CRC16/MODBUS(data) little-endian][data]
  read      : config is 7 PAGES; seq is the PAGE INDEX 0..6. fe00+MAC+seq+00*8 ->
              fd00: seq0=96B identity, seq1..5=1036B config, seq6=128B. Network
              block (ip/gw/mask/dns1/dns2) is in page seq=1.
  write     : fe01+MAC+seq+crc+data for every page, sent TWICE (vendor does), each
              ACKed by fd01. Commits to FLASH immediately. Takes effect only after a
              full reboot (device loads flash into running config on boot). fe03 is
              meant to reboot but is unreliable on this unit -> reboot via power-cycle.
"""
import socket
import struct
import time
import re

IFACE = "eth1"      # importers set ebyte_core.IFACE if needed
REQ_PORT = 1901
RSP_PORT = 1902
MAGIC = b"www.cdebyte.com" * 2
SO_BINDTODEVICE = 25
PAGES = range(0, 7)

# field offsets WITHIN the page-1 payload (header included). IPv4 = 4 bytes BE.
NET = {"ip": 0xA8, "gateway": 0xAC, "netmask": 0xB0, "dns1": 0xB4, "dns2": 0xB8}
NAME_OFF = 0xC3
NAME_LEN = 9
# serial / mode decode (page-1 payload offsets), reverse-engineered by diffing
# vendor-app changes on a live NE2-D11 (2026-07-05):
BAUD_OFF = 0x14        # code: 01=1200 02=2400 03=4800 04=9600 05=19200 06=38400
STOP_OFF = 0x11        #       07=57600 08=115200 09=230400 0A=460800
PARITY_OFF = 0x12      # 00=None 02=Even 03=Odd
WMODE_OFF = 0x319      # 01=TCP Client 02=TCP Server (03/04 = UDP, unconfirmed)
BAUD_TBL = {1: 1200, 2: 2400, 3: 4800, 4: 9600, 5: 19200, 6: 38400,
            7: 57600, 8: 115200, 9: 230400, 10: 460800}
PARITY_TBL = {0x00: "N", 0x02: "E", 0x03: "O"}
WMODE_TBL = {0: "Disable", 1: "TCP Client", 2: "TCP Server", 3: "UDP Client",
             4: "UDP Server", 5: "MQTT Client", 6: "HTTP Client"}
BAUD_REV = {v: k for k, v in BAUD_TBL.items()}
PARITY_REV = {"N": 0x00, "NONE": 0x00, "E": 0x02, "EVEN": 0x02, "O": 0x03, "ODD": 0x03}
WMODE_REV = {"DISABLE": 0, "TCP CLIENT": 1, "TCP SERVER": 2, "UDP CLIENT": 3,
             "UDP SERVER": 4, "MQTT CLIENT": 5, "HTTP CLIENT": 6,
             "CLIENT": 1, "SERVER": 2, "OFF": 0}
USER_OFF = 0xCF
PASS_OFF = 0xDA
STR_LEN = 10
SOCKA_REMOTE_OFF = 0x218
SOCKA_RPORT_OFF = 0x31C
SOCKA_LPORT_OFF = 0x320
# Link 1 (Socket A) = page1; Link 2 (Socket B) = page2
L1_MODE_OFF = 0x319       # page1: 00=off 01=TCP Client 02=TCP Server
L1_REMOTE_OFF = 0x218     # page1: ASCII
L1_RPORT_OFF = 0x31C      # page1: u16 LE
L1_LPORT_OFF = 0x320      # page1: u16 LE
L2_MODE_OFF = 0x139       # page2: 00=off 01=TCP Client 02=TCP Server
L2_REMOTE_OFF = 0x38      # page2: ASCII
L2_RPORT_OFF = 0x13C      # page2: u16 LE
L2_LPORT_OFF = 0x140      # page2: u16 LE
# RS-485 / Modbus gateway work mode (page1)
MB_MODE_OFF = 0xE8        # 00=transparent 02=multi-host 03=storage gateway
MB_TIMEOUT_OFF = 0xE4     # Modbus RTU response timeout, u16 LE (ms)
MB_POLL_OFF = 0xE6        # Modbus polling interval, u16 LE (ms)
MB_KEEP_OFF = 0xE9        # Modbus keep time, 1 byte
MB_T2R_OFF = 0xEA         # Modbus TCP<->RTU conversion: 0=off 1=on (independent!)
MBMODE_TBL = {0: "Disable", 1: "Simple conv", 2: "Multi-host", 3: "Storable",
              4: "Configurable", 5: "AutoUpdate"}
DHCP_OFF = 0xBC        # 0=static, 1=DHCP
DATABIT_OFF = 0x10     # databit code 0=5,1=6,2=7,3=8. OUT-OF-RANGE BRICKS THE DEVICE
HB_MODE_OFF = 0x20     # heartbeat pack mode: 0=Disable 1=SN 2=Send MAC 3=Custom
HB_CYCLE_OFF = 0x24    # heartbeat cycle, byte (seconds)
RECONN_OFF = 0xBE      # reconnection time, byte (seconds)
NETAT_EN_OFF = 0xC2    # Net AT enable: 0/1
NETAT_HDR_OFF = 0xC3   # Net AT header, ASCII (was mislabeled "name")
DATABIT_TBL = {0: 5, 1: 6, 2: 7, 3: 8}
HB_MODE_TBL = {0: "Disable", 1: "SN", 2: "Send MAC", 3: "Custom"}


def crc16_modbus(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if (crc & 1) else (crc >> 1)
    return crc & 0xFFFF


def _sock():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        s.setsockopt(socket.SOL_SOCKET, SO_BINDTODEVICE, IFACE.encode() + b"\x00")
    except OSError:
        pass
    s.bind(("", RSP_PORT))
    s.settimeout(0.4)
    return s


def _ip(buf, off):
    if len(buf) >= off + 4:
        return ".".join(str(x) for x in buf[off:off + 4])
    return None


def _ip_bytes(s):
    parts = [int(x) for x in s.split(".")]
    if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
        raise ValueError("bad IPv4: %r" % s)
    return bytes(parts)


def _cstr(buf, off, length):
    if len(buf) < off + length:
        return ""
    return buf[off:off + length].split(b"\x00")[0].decode("ascii", "ignore")


def _u16le(buf, off):
    if len(buf) < off + 2:
        return None
    return struct.unpack("<H", buf[off:off + 2])[0]


def _strings(buf):
    return [m.decode("ascii", "ignore") for m in re.findall(rb"[ -~]{3,}", buf)]


def _set_str(p1, off, s, fieldlen):
    b = str(s).encode("ascii", "ignore")[:fieldlen - 1]
    p1[off:off + fieldlen] = b + b"\x00" * (fieldlen - len(b))


# writable fields -> how to patch them into the page-1 payload bytearray.
# NOTE: never touch payload 0x10 (data[4]=0x03 structural constant) -> bricks device.
def _has(edits, *keys):
    """Return the first present non-empty value among keys, else None."""
    for k in keys:
        v = edits.get(k)
        if v not in (None, ""):
            return v
    return None


def _mode_byte(v):
    if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).strip().isdigit()):
        b = int(v)
        if b not in (0, 1, 2, 3, 4):
            raise ValueError("bad mode code %r" % v)
        return b
    b = WMODE_REV.get(str(v).strip().upper())
    if b is None:
        raise ValueError("bad mode %r" % v)
    return b


def _parity_byte(v):
    if isinstance(v, (int, float)) or (isinstance(v, str) and str(v).strip().isdigit()):
        b = int(v)
        if b not in (0, 2, 3):
            raise ValueError("bad parity code %r" % v)
        return b
    b = PARITY_REV.get(str(v).strip().upper())
    if b is None:
        raise ValueError("bad parity %r" % v)
    return b


def _patch_page1(p1, edits):
    applied = {}
    for f in ("ip", "gateway", "netmask", "dns1", "dns2"):
        v = edits.get(f)
        if v:
            p1[NET[f]:NET[f] + 4] = _ip_bytes(v)
            applied[f] = v
    if _has(edits, "baud") is not None:
        code = BAUD_REV.get(int(_has(edits, "baud")))
        if code is None:
            raise ValueError("unsupported baud %r" % edits["baud"])
        p1[BAUD_OFF] = code
        applied["baud"] = int(edits["baud"])
    if _has(edits, "parity") is not None:
        p1[PARITY_OFF] = _parity_byte(edits["parity"])
        applied["parity"] = p1[PARITY_OFF]
    if _has(edits, "stopbits") is not None:
        s = int(edits["stopbits"])
        p1[STOP_OFF] = (p1[STOP_OFF] | 0x02) if s == 2 else (p1[STOP_OFF] & ~0x02)
        applied["stopbits"] = s
    if _has(edits, "dhcp") is not None:
        p1[DHCP_OFF] = 1 if int(edits["dhcp"]) else 0
        applied["dhcp"] = p1[DHCP_OFF]
    if _has(edits, "databit") is not None:
        db = int(edits["databit"])
        if db not in (0, 1, 2, 3):          # 0..3 = 5..8 bits; out-of-range bricks!
            raise ValueError("bad databit code %r (allowed 0..3 = 5..8 bits)" % db)
        p1[DATABIT_OFF] = db
        applied["databit"] = db
    if _has(edits, "hb_mode") is not None:
        hm = int(edits["hb_mode"])
        if hm not in (0, 1, 2, 3):
            raise ValueError("bad hb_mode %r" % hm)
        p1[HB_MODE_OFF] = hm
        applied["hb_mode"] = hm
    if _has(edits, "hb_cycle") is not None:
        p1[HB_CYCLE_OFF] = int(edits["hb_cycle"]) & 0xFF
        applied["hb_cycle"] = int(edits["hb_cycle"])
    if _has(edits, "reconn") is not None:
        p1[RECONN_OFF] = int(edits["reconn"]) & 0xFF
        applied["reconn"] = int(edits["reconn"])
    if _has(edits, "netat_en") is not None:
        p1[NETAT_EN_OFF] = 1 if int(edits["netat_en"]) else 0
        applied["netat_en"] = p1[NETAT_EN_OFF]
    if _has(edits, "netat_hdr") is not None:
        _set_str(p1, NETAT_HDR_OFF, edits["netat_hdr"], NAME_LEN)
        applied["netat_hdr"] = edits["netat_hdr"]
    if _has(edits, "mb_mode") is not None:
        p1[MB_MODE_OFF] = int(edits["mb_mode"])   # 0xE8 only; TCP<->RTU is separate
        applied["mb_mode"] = p1[MB_MODE_OFF]
    if _has(edits, "mb_tcp2rtu") is not None:
        p1[MB_T2R_OFF] = 1 if int(edits["mb_tcp2rtu"]) else 0
        applied["mb_tcp2rtu"] = p1[MB_T2R_OFF]
    if _has(edits, "mb_timeout") is not None:
        struct.pack_into("<H", p1, MB_TIMEOUT_OFF, int(edits["mb_timeout"]) & 0xFFFF)
        applied["mb_timeout"] = int(edits["mb_timeout"])
    if _has(edits, "mb_poll") is not None:
        struct.pack_into("<H", p1, MB_POLL_OFF, int(edits["mb_poll"]) & 0xFFFF)
        applied["mb_poll"] = int(edits["mb_poll"])
    if _has(edits, "mb_keep") is not None:
        p1[MB_KEEP_OFF] = int(edits["mb_keep"]) & 0xFF
        applied["mb_keep"] = int(edits["mb_keep"])
    # Link 1 (Socket A, page1). Accept l1_* or legacy work_mode/remote/*_port.
    m = _has(edits, "l1_mode", "work_mode")
    if m is not None:
        p1[L1_MODE_OFF] = _mode_byte(m)
        applied["l1_mode"] = p1[L1_MODE_OFF]
    r = _has(edits, "l1_remote", "remote")
    if r is not None:
        _set_str(p1, L1_REMOTE_OFF, r, 40)
        applied["l1_remote"] = r
    rp = _has(edits, "l1_rport", "remote_port")
    if rp is not None:
        struct.pack_into("<H", p1, L1_RPORT_OFF, int(rp) & 0xFFFF)
        applied["l1_rport"] = int(rp)
    lp = _has(edits, "l1_lport", "local_port")
    if lp is not None:
        struct.pack_into("<H", p1, L1_LPORT_OFF, int(lp) & 0xFFFF)
        applied["l1_lport"] = int(lp)
    return applied


def _patch_page2(p2, edits):
    applied = {}
    if _has(edits, "l2_mode") is not None:
        p2[L2_MODE_OFF] = _mode_byte(edits["l2_mode"])
        applied["l2_mode"] = p2[L2_MODE_OFF]
    if _has(edits, "l2_remote") is not None:
        _set_str(p2, L2_REMOTE_OFF, edits["l2_remote"], 40)
        applied["l2_remote"] = edits["l2_remote"]
    if _has(edits, "l2_rport") is not None:
        struct.pack_into("<H", p2, L2_RPORT_OFF, int(edits["l2_rport"]) & 0xFFFF)
        applied["l2_rport"] = int(edits["l2_rport"])
    if _has(edits, "l2_lport") is not None:
        struct.pack_into("<H", p2, L2_LPORT_OFF, int(edits["l2_lport"]) & 0xFFFF)
        applied["l2_lport"] = int(edits["l2_lport"])
    return applied


def _read_frame(mac, seq):
    return b"\xfe\x00" + mac + struct.pack(">H", seq) + b"\x00" * 8


def _write_frame(mac, seq, data):
    crc = struct.pack("<H", crc16_modbus(data))
    return b"\xfe\x01" + mac + struct.pack(">H", seq) + crc + data


def _apply_frame(mac):
    return b"\xfe\x03" + mac + struct.pack(">H", 0x1101) + b"\x00" * 8


def read_all_pages(sock, mac, tries=4, per_wait=0.5):
    pages = {}
    for seq in PAGES:
        req = _read_frame(mac, seq)
        got = None
        for _ in range(tries):
            if seq in pages:
                break
            sock.sendto(req, ("255.255.255.255", REQ_PORT))
            end = time.time() + per_wait
            while time.time() < end:
                try:
                    data, _ = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                if len(data) < 10 or data[0] != 0xFD or data[1] != 0x00:
                    continue
                if data[2:8] != mac:
                    continue
                if struct.unpack(">H", data[8:10])[0] != seq:
                    continue
                got = data
                break
            if got is not None:
                pages[seq] = got
                break
    return pages


def parse_settings(pages):
    out = {
        "model": "", "firmware": "", "serial": "",
        "name": "", "username": "", "password": "",
        "sockA_remote": "", "sockA_remote_port": None, "sockA_local_port": None,
        "serial_raw": "", "baud": None, "parity": "", "stopbits": None,
        "work_mode": "",
    }
    p0 = pages.get(0, b"")
    for s in _strings(p0):
        if s.startswith(("NE", "NA", "NB")) and not out["model"]:
            out["model"] = s
        elif s.startswith("FW") and not out["firmware"]:
            out["firmware"] = s
        elif s.startswith("S") and sum(c.isdigit() for c in s) >= 5 and not out["serial"]:
            out["serial"] = s
    p1 = pages.get(1, b"")
    for k, off in NET.items():
        out[k] = _ip(p1, off)
    out["name"] = _cstr(p1, NAME_OFF, NAME_LEN)
    out["username"] = _cstr(p1, USER_OFF, STR_LEN)
    out["password"] = _cstr(p1, PASS_OFF, STR_LEN)
    out["sockA_remote"] = _cstr(p1, SOCKA_REMOTE_OFF, 16)
    out["sockA_remote_port"] = _u16le(p1, SOCKA_RPORT_OFF)
    out["sockA_local_port"] = _u16le(p1, SOCKA_LPORT_OFF)
    if len(p1) >= 12 + 16:
        out["serial_raw"] = p1[12:12 + 16].hex()
    # decoded serial / mode
    if len(p1) > BAUD_OFF:
        out["baud"] = BAUD_TBL.get(p1[BAUD_OFF])
        out["parity"] = PARITY_TBL.get(p1[PARITY_OFF], "?")
        out["parity_code"] = p1[PARITY_OFF]
        out["stopbits"] = 2 if (p1[STOP_OFF] & 0x02) else 1
    if len(p1) > WMODE_OFF:
        out["work_mode"] = WMODE_TBL.get(p1[WMODE_OFF], "code %d" % p1[WMODE_OFF])
        out["work_mode_code"] = p1[WMODE_OFF]
    if len(p1) > MB_T2R_OFF:
        out["mb_mode"] = p1[MB_MODE_OFF]
        out["mb_timeout"] = _u16le(p1, MB_TIMEOUT_OFF)
        out["mb_poll"] = _u16le(p1, MB_POLL_OFF)
        out["mb_keep"] = p1[MB_KEEP_OFF]
        out["mb_tcp2rtu"] = p1[MB_T2R_OFF]
    if len(p1) > NETAT_HDR_OFF:
        out["dhcp"] = p1[DHCP_OFF]
        out["databit"] = p1[DATABIT_OFF]
        out["hb_mode"] = p1[HB_MODE_OFF]
        out["hb_cycle"] = p1[HB_CYCLE_OFF]
        out["reconn"] = p1[RECONN_OFF]
        out["netat_en"] = p1[NETAT_EN_OFF]
        out["netat_hdr"] = _cstr(p1, NETAT_HDR_OFF, 9)
    # explicit Link 1 (Socket A, page1) and Link 2 (Socket B, page2)
    p2 = pages.get(2, b"")
    if len(p1) > L1_LPORT_OFF:
        out["l1_mode"] = p1[L1_MODE_OFF]
        out["l1_remote"] = _cstr(p1, L1_REMOTE_OFF, 40)
        out["l1_rport"] = _u16le(p1, L1_RPORT_OFF)
        out["l1_lport"] = _u16le(p1, L1_LPORT_OFF)
    if len(p2) > L2_LPORT_OFF:
        out["l2_mode"] = p2[L2_MODE_OFF]
        out["l2_remote"] = _cstr(p2, L2_REMOTE_OFF, 40)
        out["l2_rport"] = _u16le(p2, L2_RPORT_OFF)
        out["l2_lport"] = _u16le(p2, L2_LPORT_OFF)
    return out


def dev_dict(mac, ip, pages):
    macstr = ":".join("%02x" % b for b in mac)
    d = {"mac": macstr, "ip_seen": ip,
         "pages": {s: len(p) for s, p in pages.items()},
         "raw_hex": pages[1][12:].hex() if 1 in pages else ""}
    d.update({k: _ip(pages.get(1, b""), off) for k, off in NET.items()})
    d.update(parse_settings(pages))
    return d


def discover(wait=3.0):
    sock = _sock()
    try:
        for _ in range(4):
            sock.sendto(MAGIC, ("255.255.255.255", REQ_PORT))
            time.sleep(0.15)
        found = {}
        end = time.time() + wait
        while time.time() < end:
            try:
                data, addr = sock.recvfrom(4096)
            except socket.timeout:
                continue
            if len(data) < 8 or data[0] != 0xFD:
                continue
            mac = data[2:8]
            if mac not in found:
                found[mac] = addr[0]
        devices = []
        for mac, ip in found.items():
            pages = read_all_pages(sock, mac)
            devices.append(dev_dict(mac, ip, pages))
        devices.sort(key=lambda d: d["ip_seen"])
        return devices
    finally:
        sock.close()


def save_config(mac_str, edits):
    """Read current config for one MAC, apply edits to page 1, write all pages
    (twice, like the vendor), then fe03. Commits to flash; apply via reboot."""
    mac = bytes(int(x, 16) for x in mac_str.split(":"))
    sock = _sock()
    try:
        pages = read_all_pages(sock, mac)
        if 1 not in pages:
            return {"ok": False, "error": "could not read config page 1 from device"}
        p1 = bytearray(pages[1])
        p2 = bytearray(pages.get(2, b""))
        try:
            applied = _patch_page1(p1, edits)
            if len(p2) > L2_LPORT_OFF:
                applied.update(_patch_page2(p2, edits))
        except ValueError as e:
            return {"ok": False, "error": str(e)}
        struct.pack_into("<H", p1, 10, crc16_modbus(bytes(p1[12:])))
        pages[1] = bytes(p1)
        if len(p2) > L2_LPORT_OFF:
            struct.pack_into("<H", p2, 10, crc16_modbus(bytes(p2[12:])))
            pages[2] = bytes(p2)

        acks = []
        for rnd in range(2):
            if rnd > 0:
                time.sleep(2.5)   # vendor left ~2.6 s between the two write rounds
            round_acks = []
            for seq in sorted(pages):
                frame = _write_frame(mac, seq, pages[seq][12:])
                ack = None
                for _ in range(3):
                    sock.sendto(frame, ("255.255.255.255", REQ_PORT))
                    end = time.time() + 0.5
                    while time.time() < end:
                        try:
                            data, _ = sock.recvfrom(4096)
                        except socket.timeout:
                            continue
                        if (len(data) >= 10 and data[0] == 0xFD and data[1] == 0x01
                                and data[2:8] == mac
                                and struct.unpack(">H", data[8:10])[0] == seq):
                            ack = True
                            break
                    if ack:
                        break
                round_acks.append({"seq": seq, "ack": bool(ack)})
            acks.append(round_acks)
        time.sleep(1.8)
        applied_ok = None
        for _ in range(3):
            sock.sendto(_apply_frame(mac), ("255.255.255.255", REQ_PORT))
            end = time.time() + 1.5
            while time.time() < end:
                try:
                    data, _ = sock.recvfrom(4096)
                except socket.timeout:
                    continue
                if len(data) >= 8 and data[0] == 0xFD and data[1] == 0x03 and data[2:8] == mac:
                    applied_ok = True
                    break
            if applied_ok:
                break
        all_acked = all(a["ack"] for rnd in acks for a in rnd)
        return {"ok": all_acked, "applied": applied,
                "acks": acks, "reboot_ack": bool(applied_ok)}
    finally:
        sock.close()
