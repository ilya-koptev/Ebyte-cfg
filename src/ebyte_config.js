/**
 * ebyte_config.js — homeui device to configure an EBYTE serial server.
 * One device on Ethernet 2 (eth1), serial on RS485-2, powered from V_OUT.
 * Search (eth1) / Default (template) / Write (flash + reboot + verify + RS-485).
 * Byte offsets reverse-engineered (see project memory). Labels match the vendor app.
 */
var CLI = "cd /mnt/data/root/ebyte && python3 ebyte_cli.py";
var DEV = "ebyte_config";

var TEXT_FIELDS = ["ip", "gateway", "netmask", "dns1", "dns2",
                   "hb_cycle", "reconn", "netat_hdr",
                   "mb_timeout", "mb_poll", "mb_keep",
                   "l1_remote", "l1_rport", "l1_lport",
                   "l2_remote", "l2_rport", "l2_lport"];
var ENUM_FIELDS = ["baud", "databit", "parity", "stopbits", "hb_mode", "dhcp", "netat_en",
                   "mb_mode", "mb_tcp2rtu", "l1_mode", "l2_mode"];

var BAUD_ENUM = {1200: {en: "1200"}, 2400: {en: "2400"}, 4800: {en: "4800"},
    9600: {en: "9600"}, 19200: {en: "19200"}, 38400: {en: "38400"},
    57600: {en: "57600"}, 115200: {en: "115200"}, 230400: {en: "230400"}, 460800: {en: "460800"}};
var DATABIT_ENUM = {0: {en: "5"}, 1: {en: "6"}, 2: {en: "7"}, 3: {en: "8"}};
var PARITY_ENUM = {0: {en: "NONE"}, 2: {en: "EVEN"}, 3: {en: "ODD"}};
var STOP_ENUM = {1: {en: "1"}, 2: {en: "2"}};
var HB_ENUM = {0: {en: "Disable"}, 1: {en: "SN"}, 2: {en: "Send MAC"}, 3: {en: "send Customize"}};
var DHCP_ENUM = {0: {en: "Disable"}, 1: {en: "Enable"}};
var ONOFF_ENUM = {0: {en: "Disable"}, 1: {en: "Enable"}};
var MODE_ENUM = {0: {en: "Disable"}, 1: {en: "TCP client"}, 2: {en: "TCP server"},
    3: {en: "UDP client"}, 4: {en: "UDP server"}, 5: {en: "Mqtt client"}, 6: {en: "HTTP client"}};
var MBMODE_ENUM = {0: {en: "disable"}, 1: {en: "Simple converion"}, 2: {en: "Multihost mode"},
    3: {en: "Storable getway"}, 4: {en: "Configurable getway"}, 5: {en: "AutoUpdate"}};

// Template = original device state ("as it came from the factory")
var TEMPLATE = {
    ip: "192.168.69.10", gateway: "192.168.69.1", netmask: "255.255.255.0",
    dns1: "192.168.69.1", dns2: "192.168.69.1", dhcp: 0,
    baud: 9600, databit: 3, parity: 0, stopbits: 2,
    hb_mode: 0, hb_cycle: 3, reconn: 10, netat_en: 0, netat_hdr: "NETAT",
    mb_mode: 0, mb_tcp2rtu: 0, mb_timeout: 1000, mb_poll: 500, mb_keep: 10,
    l1_mode: 2, l1_remote: "192.168.3.3", l1_rport: 8888, l1_lport: 8886,
    l2_mode: 0, l2_remote: "192.168.3.3", l2_rport: 8886, l2_lport: 8887
};

var LAST_EDITS = {};
var FILLING = false;
function beginFill() { FILLING = true; }
function endFill() { setTimeout(function () { FILLING = false; }, 400); }
function T(s) { return { en: s, ru: s }; }

defineVirtualDevice(DEV, {
    title: "EBYTE configurator",
    cells: {
        search:     { type: "pushbutton", title: T("Search"), order: 1 },
        status:     { type: "text", value: "press Search", readonly: true, title: T("Status"), order: 2 },
        "default":  { type: "pushbutton", title: T("Default"), order: 3 },
        model:      { type: "text", value: "", readonly: true, title: T("Device module"), order: 5 },
        mac:        { type: "text", value: "", readonly: true, title: T("MAC"), order: 6 },
        ip:         { type: "text", value: "", readonly: false, title: T("Local IP"), order: 10 },
        gateway:    { type: "text", value: "", readonly: false, title: T("Getway"), order: 11 },
        netmask:    { type: "text", value: "", readonly: false, title: T("Mask"), order: 12 },
        dns1:       { type: "text", value: "", readonly: false, title: T("DNS"), order: 13 },
        dns2:       { type: "text", value: "", readonly: false, title: T("DNS2"), order: 14 },
        dhcp:       { type: "value", value: 0, enum: DHCP_ENUM, readonly: false, title: T("DHCP"), order: 15 },
        databit:    { type: "value", value: 3, enum: DATABIT_ENUM, readonly: false, title: T("databit"), order: 19 },
        baud:       { type: "value", value: 9600, enum: BAUD_ENUM, readonly: false, title: T("Boud rate"), order: 20 },
        parity:     { type: "value", value: 0, enum: PARITY_ENUM, readonly: false, title: T("Parity"), order: 21 },
        stopbits:   { type: "value", value: 1, enum: STOP_ENUM, readonly: false, title: T("Stop bit"), order: 22 },
        hb_mode:    { type: "value", value: 0, enum: HB_ENUM, readonly: false, title: T("Heartbeat pack mode"), order: 28 },
        hb_cycle:   { type: "text", value: "", readonly: false, title: T("Heartbeat cycle"), order: 29 },
        mb_mode:    { type: "value", value: 0, enum: MBMODE_ENUM, readonly: false, title: T("MODBUS Getway"), order: 23 },
        mb_tcp2rtu: { type: "value", value: 0, enum: ONOFF_ENUM, readonly: false, title: T("Modbus TCP to RTU"), order: 24 },
        mb_timeout: { type: "text", value: "", readonly: false, title: T("Modbus RTU timeout"), order: 25 },
        mb_poll:    { type: "text", value: "", readonly: false, title: T("Modbus polling interval"), order: 26 },
        mb_keep:    { type: "text", value: "", readonly: false, title: T("Modbus keep time"), order: 27 },
        l1_mode:    { type: "value", value: 2, enum: MODE_ENUM, readonly: false, title: T("Link1 Work Mode"), order: 30 },
        l1_remote:  { type: "text", value: "", readonly: false, title: T("Link1 Remote IP"), order: 31 },
        l1_rport:   { type: "text", value: "", readonly: false, title: T("Link1 Remote port"), order: 32 },
        l1_lport:   { type: "text", value: "", readonly: false, title: T("Link1 Local port"), order: 33 },
        l2_mode:    { type: "value", value: 0, enum: MODE_ENUM, readonly: false, title: T("Link2 Work Mode"), order: 40 },
        l2_remote:  { type: "text", value: "", readonly: false, title: T("Link2 Remote IP"), order: 41 },
        l2_rport:   { type: "text", value: "", readonly: false, title: T("Link2 Remote port"), order: 42 },
        l2_lport:   { type: "text", value: "", readonly: false, title: T("Link2 Local port"), order: 43 },
        reconn:     { type: "text", value: "", readonly: false, title: T("Reconnection time"), order: 50 },
        netat_en:   { type: "value", value: 0, enum: ONOFF_ENUM, readonly: false, title: T("Net AT enable"), order: 51 },
        netat_hdr:  { type: "text", value: "", readonly: false, title: T("Net AT header"), order: 52 },
        write:      { type: "pushbutton", title: T("Write"), order: 100 }
    }
});

function st(msg) { dev[DEV]["status"] = msg; }
function parseJ(out) { try { return JSON.parse(out); } catch (e) { log("ebyte bad JSON: " + out); return null; } }

function clearFields() {
    for (var i = 0; i < TEXT_FIELDS.length; i++) dev[DEV][TEXT_FIELDS[i]] = "";
    dev[DEV]["model"] = ""; dev[DEV]["mac"] = "";
}

var DASH = "—";
function dash(k) { dev[DEV][k] = DASH; }
function undash(k) { if (dev[DEV][k] === DASH) dev[DEV][k] = ""; }
function applyLink(mode, rem, rport, lport) {
    var m = Number(mode);
    if (m === 0) { dash(rem); dash(rport); dash(lport); }        // Disable: all dashed
    else if (m === 2) { dash(rem); dash(rport); undash(lport); } // TCP server: remote dashed
    else { undash(rem); undash(rport); undash(lport); }          // client/udp/mqtt/http: active
}
function applyVisibility() {
    applyLink(dev[DEV]["l1_mode"], "l1_remote", "l1_rport", "l1_lport");
    applyLink(dev[DEV]["l2_mode"], "l2_remote", "l2_rport", "l2_lport");
}

function fillFromJson(out) {
    var j = parseJ(out);
    if (!j) { st("bad response"); return null; }
    if (j.error) { st("error: " + j.error); return null; }
    if (!j.found) { clearFields(); st("device not found"); return j; }
    var d = j.dev;
    dev[DEV]["model"] = (d.model || "") + "  (" + d.ip_seen + ")";
    dev[DEV]["mac"] = d.mac;
    for (var i = 0; i < TEXT_FIELDS.length; i++) {
        var k = TEXT_FIELDS[i];
        dev[DEV][k] = (d[k] === undefined || d[k] === null) ? "" : ("" + d[k]);
    }
    for (var e = 0; e < ENUM_FIELDS.length; e++) {
        var ek = ENUM_FIELDS[e];
        if (d[ek] !== "" && d[ek] !== undefined && d[ek] !== null) dev[DEV][ek] = Number(d[ek]);
    }
    applyVisibility();
    st("found: " + (d.model || "EBYTE") + " " + (d.ip_seen || ""));
    return j;
}

function buildEdits() {
    var e = {};
    for (var i = 0; i < TEXT_FIELDS.length; i++) {
        var v = dev[DEV][TEXT_FIELDS[i]];
        if (v !== "" && v !== undefined && v !== null && v !== DASH) e[TEXT_FIELDS[i]] = "" + v;
    }
    for (var j = 0; j < ENUM_FIELDS.length; j++) e[ENUM_FIELDS[j]] = dev[DEV][ENUM_FIELDS[j]];
    return e;
}

function verifyReadback(d) {
    var bad = [];
    for (var k in LAST_EDITS) {
        if (String(d[k]) !== String(LAST_EDITS[k])) bad.push(k);
    }
    return bad;
}

defineRule("ebyte_search", {
    whenChanged: DEV + "/search",
    then: function () {
        beginFill();
        clearFields();
        st("searching on Ethernet 2...");
        runShellCommand(CLI + " read", {
            captureOutput: true,
            exitCallback: function (code, out) {
                if (code !== 0) { clearFields(); st("search error (code " + code + ")"); }
                else { fillFromJson(out); }
                endFill();
            }
        });
    }
});

defineRule("ebyte_default", {
    whenChanged: DEV + "/default",
    then: function () {
        beginFill();
        for (var i = 0; i < TEXT_FIELDS.length; i++) dev[DEV][TEXT_FIELDS[i]] = "" + TEMPLATE[TEXT_FIELDS[i]];
        for (var e = 0; e < ENUM_FIELDS.length; e++) dev[DEV][ENUM_FIELDS[e]] = TEMPLATE[ENUM_FIELDS[e]];
        applyVisibility();
        st("template loaded — review and press Write");
        endFill();
    }
});

var EDIT_TOPICS = [];
(function () {
    var all = TEXT_FIELDS.concat(ENUM_FIELDS);
    for (var i = 0; i < all.length; i++) EDIT_TOPICS.push(DEV + "/" + all[i]);
})();

defineRule("ebyte_changed", {
    whenChanged: EDIT_TOPICS,
    then: function () { if (!FILLING) st("template changed"); }
});

defineRule("ebyte_mode_vis", {
    whenChanged: [DEV + "/l1_mode", DEV + "/l2_mode"],
    then: function () { applyVisibility(); }
});

defineRule("ebyte_write", {
    whenChanged: DEV + "/write",
    then: function () {
        var mac = dev[DEV]["mac"];
        if (!mac) { st("press Search first"); return; }
        LAST_EDITS = buildEdits();
        st("writing to flash...");
        runShellCommand(CLI + " write '" + mac + "' '" + JSON.stringify(LAST_EDITS) + "'", {
            captureOutput: true,
            exitCallback: function (c, o) {
                var j = parseJ(o);
                if (!j || !j.ok) { st("write error: " + (j ? j.error : "no response")); return; }
                st("rebooting device (V_OUT OFF)...");
                dev["wb-gpio"]["V_OUT"] = false;
                setTimeout(function () {
                    dev["wb-gpio"]["V_OUT"] = true;
                    st("device booting...");
                    setTimeout(function () {
                        runShellCommand(CLI + " read", {
                            captureOutput: true,
                            exitCallback: function (c2, o2) {
                                beginFill();
                                var jr = fillFromJson(o2);
                                endFill();
                                if (!jr || !jr.found) { st("after write: device not found"); return; }
                                var bad = verifyReadback(jr.dev);
                                var vtxt = bad.length ? ("mismatch: " + bad.join(",")) : "config matches";
                                st("verify: " + vtxt + "; RS-485 test...");
                                runShellCommand(CLI + " rs485test '" + mac + "'", {
                                    captureOutput: true,
                                    exitCallback: function (c3, o3) {
                                        var jr3 = parseJ(o3) || {};
                                        var rtxt = jr3.skip ? ("RS-485: skipped (" + jr3.detail + ")")
                                            : (jr3.ok ? ("RS-485: OK — " + jr3.detail)
                                                      : ("RS-485: FAIL — " + (jr3.detail || "")));
                                        st("done. " + vtxt + ". " + rtxt);
                                    }
                                });
                            }
                        });
                    }, 12000);
                }, 6000);
            }
        });
    }
});
