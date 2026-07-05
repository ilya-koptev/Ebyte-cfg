# Using the dashboard

The tool installs a virtual device **“EBYTE configurator”** in homeui
(**Devices** tab). All controls are in English, matching the vendor app.

Layout (top → bottom): **Search** · **Status** · **Default** · network · serial ·
Modbus · Link 1 · Link 2 · Net AT · **Write**.

## 1. Connect the device

- Plug the EBYTE Ethernet into the controller's **Ethernet 2** (the config port).
- Wire its **RS-485 (A/B)** to the controller's **RS485-2**.
- Power the EBYTE from **V_OUT** — required so the tool can reboot it to apply
  changes and run the RS-485 test.

Give it a few seconds to boot after plugging in.

## 2. Search

Press **Search**. It clears the form, scans Ethernet 2, and fills every field.
Status shows e.g. `found: NE2-D11 192.168.69.58`. If nothing is found it shows
`device not found` (check the cable / that the device finished booting).

## 3. Default (optional)

Press **Default** to load a known-good template into the form (IP `192.168.69.10`,
9600 8N2, transparent Modbus, Link 1 = TCP server, DHCP off, Net AT off …).
Status: `template loaded — review and press Write`. Nothing is written yet.

## 4. Change what you need — e.g. the IP

Edit any field, e.g. set **Local IP** to `192.168.69.20`. Enum fields (Work Mode,
Baud, Parity, DHCP, Modbus gateway …) are **dropdowns**. As soon as you change
anything, Status shows `template changed`.

Field visibility follows the Link mode: **TCP server** hides the remote fields
(shown as `—`), **Disable** hides all of that link's fields. Dashed fields are not
written.

## 5. Write

Press **Write**. The tool:

1. writes all fields to the device **flash**,
2. **reboots** the device (power-cycles V_OUT, ~15 s),
3. **reads it back and verifies** the values,
4. runs an **RS-485 bridge test** (serial ↔ TCP).

## 6. Confirm it's OK

Watch **Status**. A good result looks like:

```
done. config matches. RS-485: OK — TCP->485:True  485->TCP:True @9600 8N2
```

- `config matches` — every written value read back correctly.
- `RS-485: OK` — data passed both ways over RS485-2 at the configured baud/format.
- `RS-485: skipped (...)` appears if Link 1 isn't **TCP server** (the bridge test
  needs a listening local port) or the mode isn't transparent.
- `mismatch: <fields>` — those fields didn't take (re-check and Write again).

## Notes

- Serial / Modbus / Link changes only take effect **after the reboot** in step 5 —
  that's why Write always power-cycles.
- Editing **Data bits** is safe (5–8 only); the tool refuses invalid values.
- To restore a device to a clean baseline: **Default → Write**.
