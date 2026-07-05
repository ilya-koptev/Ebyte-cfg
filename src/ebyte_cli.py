#!/usr/bin/env python3
"""CLI wrapper around the EBYTE UDP logic, driven by the wb-rules homeui device.

Model: exactly ONE EBYTE on Ethernet 2 (eth1), its serial side wired to RS485-2.

  ebyte_cli.py read                 -> {found,count,iface,dev{...}}
  ebyte_cli.py write <mac> <json>   -> {ok,applied,...}   (writes flash only)
  ebyte_cli.py rs485test <mac>      -> {ok,skip?,detail}  (serial<->TCP bridge check)
  ebyte_cli.py reboot               -> power-cycle via V_OUT, re-read

The wb-rules device orchestrates write -> V_OUT reboot (via its own timers) ->
read/verify -> rs485test, so the reboot is never a long shell subprocess.
"""
import sys
import os
import json
import time
import struct
import termios
import fcntl
import socket
import subprocess
import ebyte_core as E

IFACE = "eth1"                       # Ethernet 2 = eth1
E.IFACE = IFACE
PORT485 = "/dev/ttyRS485-2"
FIELDS = ("ip", "gateway", "netmask", "dns1", "dns2")
BAUD_CONST = {1200: termios.B1200, 2400: termios.B2400, 4800: termios.B4800,
              9600: termios.B9600, 19200: termios.B19200, 38400: termios.B38400,
              57600: termios.B57600, 115200: termios.B115200}


def _n(v):
    return v if v is not None else ""


def dev_summary(d):
    dev = {"model": d.get("model", ""), "mac": d.get("mac", ""),
           "ip_seen": d.get("ip_seen", "")}
    for k in FIELDS:
        dev[k] = d.get(k) or ""
    # serial (enum cells store codes: baud=number, parity=byte, stopbits=1/2)
    dev["baud"] = _n(d.get("baud"))
    dev["parity"] = _n(d.get("parity_code"))
    dev["stopbits"] = _n(d.get("stopbits"))
    dev["mb_mode"] = _n(d.get("mb_mode"))
    dev["mb_timeout"] = _n(d.get("mb_timeout"))
    dev["mb_poll"] = _n(d.get("mb_poll"))
    dev["mb_keep"] = _n(d.get("mb_keep"))
    dev["mb_tcp2rtu"] = _n(d.get("mb_tcp2rtu"))
    dev["dhcp"] = _n(d.get("dhcp"))
    dev["databit"] = _n(d.get("databit"))
    dev["hb_mode"] = _n(d.get("hb_mode"))
    dev["hb_cycle"] = _n(d.get("hb_cycle"))
    dev["reconn"] = _n(d.get("reconn"))
    dev["netat_en"] = _n(d.get("netat_en"))
    dev["netat_hdr"] = d.get("netat_hdr") or ""
    dev["name"] = d.get("name") or ""
    # Link 1 (Socket A) / Link 2 (Socket B); mode = code 0/1/2
    dev["l1_mode"] = _n(d.get("l1_mode"))
    dev["l1_remote"] = d.get("l1_remote") or ""
    dev["l1_rport"] = _n(d.get("l1_rport"))
    dev["l1_lport"] = _n(d.get("l1_lport"))
    dev["l2_mode"] = _n(d.get("l2_mode"))
    dev["l2_remote"] = d.get("l2_remote") or ""
    dev["l2_rport"] = _n(d.get("l2_rport"))
    dev["l2_lport"] = _n(d.get("l2_lport"))
    return dev


def find(mac):
    for d in E.discover(3.0):
        if d["mac"].lower() == mac.lower():
            return d
    return None


def open485(baud, parity, stop2):
    fd = os.open(PORT485, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        fcntl.ioctl(fd, 0x542F, struct.pack("IIIIIIII", 0x03, 0, 0, 0, 0, 0, 0, 0))
    except OSError:
        pass
    a = termios.tcgetattr(fd)
    cflag = termios.CS8 | termios.CLOCAL | termios.CREAD
    if stop2:
        cflag |= termios.CSTOPB
    if parity in ("E", "O"):
        cflag |= termios.PARENB
        if parity == "O":
            cflag |= termios.PARODD
    a[2] = cflag
    a[0] = a[1] = a[3] = 0
    a[4] = a[5] = BAUD_CONST.get(baud, termios.B9600)
    a[6][termios.VMIN] = 0; a[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, a)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def rs485_bridge_check(dev):
    """serial<->TCP loopback via the device (TCP Server mode). Returns dict."""
    if dev.get("work_mode") != "TCP Server":
        return {"ok": False, "skip": True,
                "detail": "RS-485 тест только в режиме TCP Server (сейчас %s)" % dev.get("work_mode")}
    ip = dev.get("ip"); port = dev.get("sockA_local_port")
    baud = dev.get("baud"); parity = dev.get("parity")
    stop2 = (dev.get("stopbits") == 2)
    if not ip or not port:
        return {"ok": False, "detail": "нет ip/локального порта для теста"}
    # give eth1 an address on the device subnet (assume /24)
    subnet = ip.rsplit(".", 1)[0]
    subprocess.run(["ip", "addr", "add", subnet + ".253/24", "dev", "eth1"],
                   stderr=subprocess.DEVNULL)
    subprocess.run(["ip", "route", "flush", "cache"], stderr=subprocess.DEVNULL)
    subprocess.run(["systemctl", "stop", "wb-mqtt-serial"], timeout=10)
    time.sleep(1)
    out = {"ok": False}
    fd = None; tcp = None
    try:
        fd = open485(baud, parity, stop2)
        tcp = socket.create_connection((ip, port), timeout=5)
        tcp.settimeout(2.0)
        time.sleep(0.3)
        # TCP -> serial
        tcp.sendall(b"RS485CHK_T\n"); time.sleep(0.4)
        s_got = b""
        end = time.time() + 2
        while time.time() < end:
            try:
                c = os.read(fd, 128)
                if c:
                    s_got += c
            except (BlockingIOError, OSError):
                time.sleep(0.02)
        # serial -> TCP
        os.write(fd, b"RS485CHK_S\n"); time.sleep(0.4)
        try:
            t_got = tcp.recv(128)
        except socket.timeout:
            t_got = b""
        tcp_to_ser = b"RS485CHK_T" in s_got
        ser_to_tcp = b"RS485CHK_S" in t_got
        out = {"ok": tcp_to_ser and ser_to_tcp,
               "tcp_to_serial": tcp_to_ser, "serial_to_tcp": ser_to_tcp,
               "detail": "TCP->485:%s  485->TCP:%s @%s 8%s%s" %
                         (tcp_to_ser, ser_to_tcp, baud, parity, 2 if stop2 else 1)}
    except Exception as e:
        out = {"ok": False, "detail": "ошибка теста: %s" % e}
    finally:
        try:
            if tcp:
                tcp.close()
        except Exception:
            pass
        if fd is not None:
            os.close(fd)
        subprocess.run(["systemctl", "start", "wb-mqtt-serial"], timeout=10)
    return out


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "read"
    E.IFACE = IFACE
    if cmd == "read":
        try:
            ds = E.discover(3.0)
        except Exception as e:
            print(json.dumps({"found": False, "error": str(e)})); return
        dev = dev_summary(ds[0]) if ds else {}
        print(json.dumps({"found": bool(ds), "count": len(ds), "iface": IFACE, "dev": dev}))
    elif cmd == "write":
        try:
            mac = sys.argv[2]
            edits = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}
            print(json.dumps(E.save_config(mac, edits)))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
    elif cmd == "rs485test":
        try:
            dev = find(sys.argv[2])
            if not dev:
                print(json.dumps({"ok": False, "detail": "устройство не найдено"})); return
            print(json.dumps(rs485_bridge_check(dev)))
        except Exception as e:
            print(json.dumps({"ok": False, "detail": "ошибка: %s" % e}))
    elif cmd == "reboot":
        try:
            subprocess.run(["mosquitto_pub", "-t", "/devices/wb-gpio/controls/V_OUT/on", "-m", "0"], timeout=5)
            time.sleep(6)
            subprocess.run(["mosquitto_pub", "-t", "/devices/wb-gpio/controls/V_OUT/on", "-m", "1"], timeout=5)
            dev = {}
            for _ in range(30):
                time.sleep(1)
                ds = E.discover(2.0)
                if ds:
                    dev = dev_summary(ds[0]); break
            print(json.dumps({"ok": bool(dev), "dev": dev}))
        except Exception as e:
            print(json.dumps({"ok": False, "error": str(e)}))
    else:
        print(json.dumps({"error": "unknown command %r" % cmd}))


if __name__ == "__main__":
    main()
