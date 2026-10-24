# Bluetooth and Wi-Fi Modes Implementation Plan (Plan 1c)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let teams drive the robot without a USB cable:
- **Bluetooth:** `--bluetooth` auto-detects a paired robot.
- **Wi-Fi:** `--wifi-setup` joins the robot to a network from the CLI, and `--ws` detects the robot model over Wi-Fi.

Both are checked on hardware.

**Architecture:**
- **Bluetooth uses Classic SPP,** which the OS exposes as a serial port. So it reuses `SerialLink` unchanged.
- **Detection:** `find_robot()` gains a Bluetooth mode that probes paired `Bittle…_SSP` / `Nybble…_SSP` ports by name.
- **Wi-Fi:**
  - It already uses `WsLink`.
  - This plan adds robot detection over WebSocket (sending `?` as a task), so `--ws` no longer needs `--robot`.
  - It adds a one-time `--wifi-setup` that sends the firmware's `w%SSID%password` over USB or Bluetooth and prints the robot's `ws://` URL.
- **Out of scope:** BLE (bleak) goes to Plan 2 (Android), which needs BLE anyway.

**Tech Stack:** Same as Plan 1: Python, pyserial, websockets, unittest. No new dependencies.

---

## Context (verified 2026-10-23 unless marked)

### Bluetooth SPP (macOS, Bittle X, firmware B10_260527)
- **Pairing:** after pairing in macOS Bluetooth settings, `/dev/cu.Bittle0D_SSP` appears. The name is `<uniqueName>_SSP` (`bluetoothManager.h:73`).
- **It works with no code changes:** `SerialLink(open_serial("/dev/cu.Bittle0D_SSP")).send("?")` returned `G | Bittle X | B10_260527 | ?` in 0.39 s, then 0.05 s on a second try.
- **Stale pairings can be listed:** `/dev/cu.BittleEE_SSP` was a pairing for a different robot. It opened in about 1 s but never answered, so a probe must time out quickly.
- **These ports report no USB vendor ID** (`vid=None`), so today's `find_robot()` skips them on purpose.
- **Firmware:** it runs both SPP and a BLE server after a 3 s start-up client scan (`bluetoothManager.h:114-185`).
- **Not verified:** Windows (expected: a "Standard Serial over Bluetooth link" COM port) and Linux (expected: `rfcomm` binding, `/dev/rfcomm0`). Motion over Bluetooth is not yet tested.

### BLE (for reference only; this plan doesn't use it)
- The robot advertises as `Bittle0D_BLE`.
- Nordic UART: service `6E400001-…`, the client writes to `6E400002-…`, and replies are notified on `6E400003-…`.
- On connect, the firmware sends `Petoi <MODEL>` and **forces `d` (rest)** (`bleUart.h` `detectBle()`). A command sent before that greeting is overwritten.

### Wi-Fi
- **Join command:** `w%SSID%password` over serial (`reaction.h:436-470`).
  - The firmware parses the SSID up to the second `%`, and the password after it.
  - On success it prints `Successfully connected Wifi to IP Address: <ip>` and stores a flag, so the robot reconnects later.
  - If `webServerConnected` is already true, it does nothing.
- **Server:** WebSocket on port 81, already implemented in `WsLink`, with a heartbeat every 15 s. Only tested against `MockFirmware`.
- **Unverified on hardware:**
  - the `results` text for `?`;
  - whether `completed` for `kwkF 3` waits for the cycles (deferred echo);
  - whether the reconnect after a reboot is automatic.

## Decisions (proposed, for Kai to approve)

1. **Bluetooth means Classic SPP** through the existing serial link. BLE waits for Plan 2.
2. **Name pattern for Bluetooth ports:** a device or description matching `(bittle|nybble).*_ssp` (case-insensitive), `rfcomm` (Linux), or `bluetooth link` (Windows COM description, unverified). Each candidate is probed with `?` and a **3 s** timeout. If several robots answer, the first wins; `--port` picks a specific one.
3. **`--wifi-setup` reads the Wi-Fi password with `getpass`.** It's never echoed, logged, or stored by our code, and the firmware's own reply (which masks most of the password) is not printed. The tool prints only the IP and the `--ws` URL. SSIDs or passwords containing `%` are rejected with a clear message, since `%` is the firmware's separator.
4. **`--ws` detects the robot** by sending `?` as a WebSocket task. If the reply has no model name, it falls back to `--robot` (default `bittle`) with a warning.
5. **No commits,** as in Plan 1, until Kai says so.

## File structure

| File | Change |
|---|---|
| `opencat_gemma/links.py` | `candidate_ports(bluetooth)`, `find_robot(bluetooth=False)`, `wifi_setup(link, ssid, password)`, `detect_ws_robot(link)` |
| `opencat_gemma/__main__.py` | `--bluetooth`, `--wifi-setup`; `--ws` uses `detect_ws_robot` |
| `tests/test_links.py`, `tests/test_cli.py` | Tests for the above |
| `README.md`, `docs/protocol.md` | Bluetooth and Wi-Fi setup per OS; protocol notes (SPP, BLE greeting, `w%…%…`) |

---

### Task 1: Bluetooth port discovery

**Files:** Modify `opencat_gemma/links.py` and `tests/test_links.py`.

- [ ] **Step 1: Failing tests.** Add to `tests/test_links.py`:

```python
class CandidatePortsTest(unittest.TestCase):
    PORTS = [
        SimpleNamespace(device="/dev/cu.wchusbserial1", vid=6790, description="USB Single Serial"),
        SimpleNamespace(device="/dev/cu.Bittle0D_SSP", vid=None, description="n/a"),
        SimpleNamespace(device="/dev/cu.Bluetooth-Incoming-Port", vid=None, description="n/a"),
        SimpleNamespace(device="/dev/rfcomm0", vid=None, description="n/a"),
        SimpleNamespace(device="COM7", vid=None, description="Standard Serial over Bluetooth link (COM7)"),
    ]

    def ports(self, bluetooth):
        with mock.patch.object(links.list_ports, "comports", return_value=self.PORTS):
            return list(links.candidate_ports(bluetooth))

    def test_usb_mode_lists_ports_with_vendor_id(self):
        self.assertEqual(self.ports(False), ["/dev/cu.wchusbserial1"])

    def test_bluetooth_mode_lists_petoi_ssp_rfcomm_and_windows_bt_ports(self):
        self.assertEqual(self.ports(True), ["/dev/cu.Bittle0D_SSP", "/dev/rfcomm0", "COM7"])
```

Add one test to the existing `FindRobotTest`, reusing its `FakeSerial` and patching pattern. The Bluetooth probe must use a short timeout: assert that `find_robot(bluetooth=True)` calls `send("?", timeout=3)`. A simple way is to patch `links.SerialLink.send` with a mock that returns `"Bittle X | ?"` and check its `call_args`.

- [ ] **Step 2:** Run `.venv/bin/python -m unittest tests.test_links` and confirm the new tests fail.

- [ ] **Step 3: Implement.** In `links.py`, add `import re`, then:

```python
# Paired Bluetooth serial ports: macOS /dev/cu.<name>_SSP, Linux rfcomm, Windows "Standard Serial over Bluetooth link"
BT_PORT = re.compile(r"(bittle|nybble).*_ssp|rfcomm|bluetooth link", re.I)


def candidate_ports(bluetooth=False):
    """USB ports report a vendor id; paired Bluetooth serial ports don't, so they are matched by name."""
    for p in list_ports.comports():
        if bluetooth:
            if BT_PORT.search(f"{p.device} {p.description}"):
                yield p.device
        elif p.vid is not None:
            yield p.device
```

Change `find_robot` to:

```python
def find_robot(bluetooth=False):
    """Probe ports with '?'. Returns (SerialLink, robot) for the first Petoi robot that answers.

    Stale Bluetooth pairings are listed but never answer, so every probe has a short timeout.
    """
    for device in candidate_ports(bluetooth):
        try:
            link = SerialLink(open_serial(device))
        except (serial.SerialException, OSError):
            continue
        try:
            robot = robot_from_reply(link.send("?", timeout=3))
        except (TimeoutError, serial.SerialException, OSError):
            robot = None
        if robot:
            print(f"Found {robot} on {device}")
            return link, robot
        link.close()
    where = "a paired Bluetooth port (pair the robot's <name>_SSP first)" if bluetooth else "USB"
    raise RuntimeError(f"No Petoi robot found on {where}. Check power, pairing/cable, and that no other app has the port open.")
```

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. Everything passes, including the existing `FindRobotTest`.

---

### Task 2: `--bluetooth` in the CLI

**Files:** Modify `opencat_gemma/__main__.py` and `tests/test_cli.py`.

- [ ] **Step 1: Failing test.** Add to `ChatTest`:

```python
    def test_bluetooth_flag_uses_bluetooth_discovery(self):
        link = FakeLink()
        with mock.patch.object(cli, "find_robot", return_value=(link, "bittle")) as find, \
             mock.patch.object(cli, "ask", return_value='["ksit"]'), redirect_stdout(io.StringIO()):
            cli.main(["--bluetooth", "sit"])
        find.assert_called_once_with(bluetooth=True)
        self.assertEqual(link.sent, ["ksit"])
```

- [ ] **Step 2:** Confirm it fails (`--bluetooth` is an unknown argument).

- [ ] **Step 3: Implement.**
  - Add `p.add_argument("--bluetooth", action="store_true", help="find a paired robot over Bluetooth (pair <name>_SSP first)")`.
  - In `main()`, replace `link, robot = find_robot()` with `link, robot = find_robot(bluetooth=args.bluetooth)`.
  - In the existing branch `if args.dry_run or args.ws or args.port:`, nothing changes: `--port` still wins over `--bluetooth`.

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass.

---

### Task 3: Robot detection over WebSocket

**Files:** Modify `opencat_gemma/links.py`, `opencat_gemma/__main__.py` and `tests/test_links.py`.

- [ ] **Step 1: Failing tests.** In `tests/test_links.py`:

```python
class DetectWsRobotTest(unittest.TestCase):
    def test_reply_with_model_name(self):
        fw = MockFirmware(reply=lambda m: {"type": "response", "taskId": m["taskId"], "status": "completed",
                                           "results": ["G\r\nBittle X\r\nB10_260527\r\n?\r\n"]})
        self.addCleanup(fw.close)
        link = WsLink(fw.url)
        self.addCleanup(link.close)
        self.assertEqual(links.detect_ws_robot(link), "bittle")

    def test_reply_without_model_name_returns_none(self):
        fw = MockFirmware()  # replies "<command minus first char>\r\nk"
        self.addCleanup(fw.close)
        link = WsLink(fw.url)
        self.addCleanup(link.close)
        self.assertIsNone(links.detect_ws_robot(link))
```

- [ ] **Step 2:** Confirm they fail.

- [ ] **Step 3: Implement** in `links.py`:

```python
def detect_ws_robot(link):
    """Ask over WebSocket which robot this is. Returns 'bittle'/'nybble', or None if the reply names no model."""
    try:
        return robot_from_reply(link.send("?", timeout=5))
    except (TimeoutError, RuntimeError):
        return None
```

In `__main__.py` `main()`:
- in the early branch, only set `robot = args.robot or "bittle"` when **not** `args.ws`;
- after opening `WsLink`, when `args.ws and not args.robot`, run `robot = detect_ws_robot(link) or "bittle"`, and print a warning when detection returned `None`;
- make sure `contract = load(robot)` happens after detection, inside the existing `try/finally`.

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass, including the existing CLI tests.

---

### Task 4: `--wifi-setup`

**Files:** Modify `opencat_gemma/links.py`, `opencat_gemma/__main__.py`, `tests/test_links.py` and `tests/test_cli.py`.

- [ ] **Step 1: Failing tests.** In `tests/test_links.py`:

```python
class WifiSetupTest(unittest.TestCase):
    def test_sends_join_command_and_returns_ip(self):
        ser = FakeSerial({"w%Lab%s3cret": b"WifiSSID: \tLab\r\nPassword: \t**cret\r\n"
                                         b"Successfully connected Wifi to IP Address: 192.168.1.50\r\nw\r\n"})
        self.assertEqual(links.wifi_setup(SerialLink(ser), "Lab", "s3cret"), "192.168.1.50")
        self.assertEqual(ser.written, b"w%Lab%s3cret\n")

    def test_failure_raises_without_echoing_password(self):
        ser = FakeSerial({"w%Lab%s3cret": b"connection failed\r\nw\r\n"})
        with self.assertRaises(RuntimeError) as e:
            links.wifi_setup(SerialLink(ser), "Lab", "s3cret")
        self.assertNotIn("s3cret", str(e.exception))

    def test_percent_sign_rejected(self):
        with self.assertRaises(ValueError):
            links.wifi_setup(SerialLink(FakeSerial({})), "Lab%2", "pw")
```

In `tests/test_cli.py`:

```python
    def test_wifi_setup_prompts_and_prints_ws_url(self):
        link = FakeLink()
        out = io.StringIO()
        with mock.patch.object(cli, "find_robot", return_value=(link, "bittle")), \
             mock.patch.object(cli, "wifi_setup", return_value="192.168.1.50") as setup, \
             mock.patch("builtins.input", return_value="Lab"), \
             mock.patch.object(cli.getpass, "getpass", return_value="s3cret"), redirect_stdout(out):
            cli.main(["--wifi-setup"])
        setup.assert_called_once_with(link, "Lab", "s3cret")
        self.assertIn("ws://192.168.1.50:81", out.getvalue())
        self.assertNotIn("s3cret", out.getvalue())
        self.assertTrue(link.closed)
```

- [ ] **Step 2:** Confirm they fail.

- [ ] **Step 3: Implement** in `links.py`:

```python
IP_LINE = re.compile(r"IP Address:\s*(\d{1,3}(?:\.\d{1,3}){3})")


def wifi_setup(link, ssid, password, timeout=40):
    """Join the robot to Wi-Fi with the firmware's 'w%SSID%password' command (over USB or Bluetooth serial).

    Returns the robot's IP. The firmware remembers the network. The password is never printed by this function.
    """
    if "%" in ssid or "%" in password:
        raise ValueError("Wi-Fi name and password can't contain '%' (the firmware uses it as a separator)")
    reply = link.send(f"w%{ssid}%{password}", timeout=timeout)
    match = IP_LINE.search(reply)
    if not match:
        raise RuntimeError("The robot did not report an IP address. Check the Wi-Fi name and password; "
                           "if the robot is already on Wi-Fi, find its IP in your router.")
    return match.group(1)
```

In `__main__.py`:
- add `import getpass`, and import `wifi_setup` from `.links`;
- add `p.add_argument("--wifi-setup", action="store_true", help="join the robot to Wi-Fi (over USB or --bluetooth), then print its ws:// URL")`;
- in `main()`, right after `parse_args`:

```python
    if args.wifi_setup:
        link, _ = (SerialLink(open_serial(args.port)), None) if args.port else find_robot(bluetooth=args.bluetooth)
        try:
            ssid = input("Wi-Fi name (SSID): ").strip()
            ip = wifi_setup(link, ssid, getpass.getpass("Wi-Fi password (not shown): "))
        finally:
            link.close()
        print(f"Robot is on Wi-Fi. Use: python -m opencat_gemma --ws ws://{ip}:81")
        return
```

- [ ] **Step 4:** Run `.venv/bin/python -m unittest discover tests`. All tests pass.

---

### Task 5: Docs

**Files:** Modify `README.md` and `docs/protocol.md`.

- [ ] **README:** add a "Connect without a cable" section.
  - **Bluetooth:**
    - Pair the robot's `<name>_SSP` device in your OS settings. Ignore `<name>_BLE`; that one is for phone apps.
    - Then run `python -m opencat_gemma --bluetooth`.
    - macOS is verified. Windows (COM port) and Linux (`sudo rfcomm bind 0 <MAC>` → `/dev/rfcomm0`) are **not verified**.
    - Tip: if an old pairing for another robot is listed, detection skips it after 3 s; use `--port` to choose.
  - **Wi-Fi:**
    - One-time `--wifi-setup` (over USB or `--bluetooth`).
    - Then `--ws ws://<ip>:81`.
    - The robot remembers the network. Its IP may change when the router reassigns it.
    - Never commit Wi-Fi passwords.
  - Update "Verification status" from Task 6's results.
- [ ] **`docs/protocol.md`:** add a "Bluetooth" section covering SPP naming, the measured `?` latency, stale pairings, and the BLE facts from Context (UUIDs, greeting, forced `d`), for Plan 2. Update the Wi-Fi section with `--wifi-setup` and the Task 6 results.

---

### Task 6: Hardware check (Kai present, robot on the floor)

- [ ] **Bluetooth, USB unplugged:**
  1. `python -m opencat_gemma --bluetooth` finds `bittle` on `/dev/cu.Bittle0D_SSP` (and skips `BittleEE_SSP`).
  2. "stand up then sit": the robot does it.
  3. "walk 3 steps then sit": the robot walks 3 cycles, then sits.
  4. Ctrl+C during "walk 20 steps": the robot stops.
- [ ] **Wi-Fi:**
  1. `python -m opencat_gemma --bluetooth --wifi-setup`. Kai types the SSID and password. Expect the robot's `ws://` URL.
  2. `python -m opencat_gemma --ws ws://<ip>:81`. Expect the robot detected as `bittle`. **Record the actual `results` text for `?`.**
  3. "walk 3 steps then sit": the robot walks, then sits. **Record whether `completed` for `kwkF 3` arrives after the walk ends (about 4 s) or right away.** If right away, add a fixed wait per step in `run()` for WebSocket only, as a follow-up task.
  4. Ctrl+C during "walk 20 steps": the robot stops.
- [ ] **Record the results** in `docs/protocol.md` and in the README's verification status.

---

## Revision (2026-10-23): Bluetooth via BLE instead of Classic SPP. Approved direction, Kai chose option 1.

### Why
- **SPP on macOS stopped working after its first success.**
  - `/dev/cu.Bittle0D_SSP` answered `?` once, in 0.05 s, right after pairing.
  - After that, every probe got no reply, including after a robot power cycle.
  - After a write, the port's `close()` **blocks indefinitely** inside macOS. Evidence: a faulthandler dump at `serialposix.py:533 in close`.
  - Open → close without writing returns in 1.5 s, and `reset_output_buffer()` before `close()` doesn't help.
  - A stuck `--bluetooth` run kept holding the port.
- **BLE worked every time:**
  - the scan finds the robot;
  - it connects in 0.6 s;
  - the Nordic UART service is present.
- **BLE fits the other plans:** it's cross-platform through `bleak`, and it's what Plan 2 (Android) needs.

### What changes
- **New dependency:** `bleak` (pin the installed version in `requirements.txt`).
- **New `opencat_gemma/ble.py`:**
  - `BleLink`, with the same `send(command, timeout)` / `close()` interface as `SerialLink`;
  - `find_ble_robot()`.
  - All bleak coroutines run on **one** background event loop thread, so the sync API matches the other links.
- **Connect handshake** (firmware `bleUart.h` `detectBle()`):
  1. subscribe to TX notifications;
  2. wait for the forced-rest echo line `d`, at most 8 s. Seen once: `Petoi Bittle Xpg\r\nrest\r\nd\r\n`;
  3. the text before it holds `Petoi <MODEL>`, which identifies the robot.

  If no `d` arrives but the greeting names a model, continue anyway.
- **Robot names:** advertised names are matched by prefix (`bittle`/`nybble`), case-insensitive. macOS has shown the same robot as `Bittle0D_BLE` and as `Bittle0D_SSP` (cached name), so the `_BLE` suffix isn't required. Candidates are tried strongest-signal first.
- **Classic-SPP discovery is removed:** `candidate_ports(bluetooth)`, the `find_robot(bluetooth=…)` parameter, and their tests. `find_robot()` goes back to USB-only. A paired SPP port can still be used manually with `--port`, documented as "may work; flaky on macOS". `WRITE_TIMEOUT_S` stays.
- **CLI:**
  - `--bluetooth` calls `find_ble_robot()`;
  - `--wifi-setup --bluetooth` sends the Wi-Fi join over BLE.

### Tasks
- [ ] **R1: `BleLink` + `find_ble_robot`, test-first.** Tests use a fake client, an object with async `connect`, `start_notify(uuid, cb)`, `write_gatt_char(uuid, data, response)` and `disconnect`, which calls `cb(None, bytes)` to simulate notifications. `BleakScanner.discover` is patched. Cover:
  - the handshake waits for `d`, returns the greeting, and detects `bittle`;
  - `send()` writes `command + "\n"` to RX, returns on the token echo, and times out without one;
  - notifications split across chunks are joined;
  - `close()` disconnects even when `send` raised;
  - `find_ble_robot` skips a device whose connect fails, picks the strongest signal, and raises a clear error when none is found.
- [ ] **R2: CLI wiring and SPP removal.** Remove `candidate_ports`, `BT_PORT`, the bluetooth parameter and their tests. Make `--bluetooth` use `find_ble_robot()` for chat, single-shot and `--wifi-setup`. Update the CLI tests to patch `find_ble_robot`.
- [ ] **R3: Docs.**
  - README "Connect without a cable" → **Bluetooth: no pairing needed.** Just run `--bluetooth`; the robot is found over BLE. Note that the robot lies down (rests) when Bluetooth connects; this is firmware behaviour.
  - Mention `--port <name>_SSP` as an unreliable alternative.
  - `docs/protocol.md`: add the SPP failure evidence and the BLE handshake.
- [ ] **R4: Hardware check (Kai present):** the Bluetooth part of Task 6, now over BLE, followed by the Wi-Fi part.
