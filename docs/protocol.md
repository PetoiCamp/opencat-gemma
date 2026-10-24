# Robot protocol notes

What the starter relies on, and how sure we are of each part. Firmware tested: B10_260527 on a Bittle X, over USB. Quaddle (ESP32-S3 firmware family, Q_261022) was checked on 2026-10-23 for `?` over USB and Bluetooth LE and for step-count walks over USB; its notes are marked "Quaddle".

## Serial

- 115200 baud, 8N1. Send `<command>\n`.
- When a command is done, the robot prints the command's first letter (here `k`) on its own line. The starter waits for that line.
- **Don't change DTR or RTS when opening the port.** The starter leaves them at pyserial's defaults.
  - Setting `ser.dtr = ser.rts = False` on the pyserial object makes pyserial lower DTR and RTS while opening the port; on macOS that pulsed the ESP32 reset line and **rebooted the robot**. This was observed with Bittle X on 2026-10-23.
  - During the reboot, the firmware clears the serial input (`Flush the serial buffer...`), so a `?` sent then is lost (observed on Bittle X, macOS, 2026-10-23).
  - Boot takes over 7 s (observed on Bittle X, macOS, 2026-10-23).
  - With the defaults, opening the port does not reboot the robot, and `?` is answered immediately (verified on macOS).
  - Windows and Linux are **not verified**.
- **Watch out: boot output begins with a lone `k` line,** which looks the same as a command's "done" echo (observed on Bittle X, macOS, 2026-10-23). If the robot reboots mid-session, which could happen, for example after a brown-out, a command sent at that moment could appear to complete. If you see `* Start *` in the output, the robot has rebooted (observed on Bittle X, macOS, 2026-10-23).

Observed on Bittle X:

```
sent:   kbalance
reply:  balance
        k
```

`?` returns the model and firmware version, one item per line (`find_robot` uses this to pick the robot):

```
sent:   ?
reply:  G
        Bittle X
        B10_260527
        ?
```

`find_robot` probes USB serial ports that report a vendor id, sends `?`, keeps the first port whose reply contains a contract's `model` name ("Bittle", "Nybble", "Quaddle"), and closes every other port it opened.

**Wake retry (Quaddle).** A Quaddle in charge sleep only wakes on the first command: it prints `Charge sleep: serial wake` and sends no echo, and the command is not run. So if the first `?` gets no echo within 3 s, `find_robot` sends `?` once more (3 s again). The second `?` was answered in 0.06 s with `Quaddle | Q_261022 | ?`. Opening the port does not reboot a Quaddle.

## Gait arguments

- `kwkF 3` works. The robot walks 3 cycles (about 1.3 s each), then stands up by itself (`up`). The `k` is printed only after it stops, about 4.3 s in total:

  ```
  sent:   kwkF 3
  reply:  ... up
          k          (about 4.3 s later)
  ```

  `kbk N` takes the same code path in the firmware source (read, not run on hardware).
- **Quaddle:** `kwkF 3` and `kbkF 3` count cycles (about 0.5 s each), stand up, and echo `k` at the end, the same as Bittle X. Its backward (`…B`) and turning (`…L`/`…R`) gaits loop until the next command, so they are timed turns. Whether `kvt90L` stops by itself is not known, so it is timed too.
- Values under 200 are cycles; 200 or more are milliseconds. This comes from reading the firmware; only the cycle case was run.
- **Angle turns never stop.** With `kwkL 90` the yaw read `5363.72` (outside +-180), the turn never ended, and the robot had to be power-cycled. With a gyro, a number after a turn is always read as degrees, so timed turns are not possible either.
- **So turns are sent bare** (`kwkL` / `kwkR`). A bare gait echoes `k` right away and keeps going until the next command. The starter waits `--turn-seconds` (default 2.0), then sends `kbalance`. The allowlist rejects turn angles.

## WebSocket

**Not yet verified on hardware.** Written from the firmware source (OpenCatEsp32 `src/webServer.h`, `main` @ `84dd6ef`) and tested only against a mock firmware in `tests/`.

- Endpoint: `ws://<ip>:81`.
- Request:

  ```json
  {"type": "command", "taskId": "1729700000000000000", "commands": ["kwkF 3"], "timestamp": 1729700000000}
  ```
- Replies:

  ```json
  {"type": "response", "taskId": "1729700000000000000", "status": "running"}
  {"type": "response", "taskId": "1729700000000000000", "status": "completed", "results": ["..."]}
  ```
- One task runs at a time. Errors carry the running task's id, or no id at all; the starter treats any error message as a failure and sends the stop.
- The server disconnects a client after 40 s without a heartbeat. The starter sends `{"type": "heartbeat", "timestamp": ms}` every 15 s from a background thread.
- The server also pushes sensor events (`event_us`, `event_cam`). The starter ignores them.
- **One command per task.** The firmware runs a multi-command task back to back, starting each command as soon as the previous one replies. A turn in the middle of a group would be cut off immediately, so the starter sends one command per task and times the turn between tasks.
- **Unverified on hardware:** the exact `results` text, and whether the deferred echo for `kwkF N` also delays `completed`.

## Bluetooth (BLE)

The starter uses Bluetooth LE through `bleak` (`opencat_gemma/ble.py`). No pairing is needed.

- **Names:** the robot advertises as `Bittle0D_BLE`; macOS has also shown the same robot as `Bittle0D_SSP` (a cached name). A Quaddle advertised as `Quaddle03_BLE`. So names are matched by prefix (each contract's `ble_prefix`, plus `petoi` for the `Petoi_BLE` fallback name; case-insensitive), and candidates are tried strongest signal first.
- **Nordic UART service** `6E400001-B5A3-F393-E0A9-E50E24DCCA9E`:
  - the client writes commands (`command + "\n"`, without response) to RX `6E400002-...`;
  - the robot notifies replies on TX `6E400003-...`. Notifications can split a line anywhere, so the link joins them and only complete lines count.
- **Handshake: two styles.**
  - **ESP32 (BiBoard) firmware** (`bleUart.h` `detectBle()`): after subscribing to TX, the firmware sends `Petoi <MODEL>` and then **forces rest**. Seen: `b"Petoi Bittle Xpg\r\nrest\r\nd\r\n"`. A command sent before the `d` line is overwritten. The robot therefore lies down on connect; the first command makes it stand.
  - **ESP32-S3 firmware (Quaddle):** nothing is sent on connect and there is no forced rest. The robot answers only when asked `?`. The **first** `?` after connecting gets a handshake reply sent as separate notifications **with no line breaks**: seen `Petoi QuaddleuQuaddleQ_261022?` (`Petoi Quaddle`, `u`, `Quaddle`, the version, `?`). Later `?` replies are normal lines (`Quaddle\r\nQ_261022\r\n?\r\n`). Writing with or without response made no visible difference.
  - **So `BleLink.connect()` works with both:**
    1. Subscribe, then wait up to 2 s for any pushed text.
    2. If something arrives (ESP32 style), wait up to 8 s for the `d` line; if it doesn't come, carry on.
    3. Clear the buffer and **always send `?`**.
    4. Accept the reply when a complete line is `?`, or when the text contains `Petoi` and ends with `?` (the S3 handshake without line breaks). Give up after 5 s.
    5. `find_ble_robot()` identifies the robot from that reply.
  - On an S3 robot this adds the 2 s push wait to the connect. Always asking `?` after the ESP32 greeting is verified on Bittle X (`--bluetooth --name Bittle0D`, chat works, 2026-10-23).
- Measured (Bittle X, macOS, 2026-10-23):
  - the scan finds the robot and it connects in 0.6 s;
  - `find_ble_robot()` takes about 17 s in total (an 8 s scan, the connect, and the greeting wait);
  - `?` round trip: 0.04 s.
- Verified in chat mode over BLE: stand up and sit, walking with steps, and the Ctrl+C stop.
- Only one BLE client can be connected, so the Petoi phone app must be closed.

### Why not Classic SPP

SPP shows up as a serial port (`/dev/cu.<uniqueName>_SSP`, firmware `bluetoothManager.h:73`), so `SerialLink` could use it. On macOS it stopped working after its first success (Bittle X, firmware B10_260527, 2026-10-23):
- `?` was answered once, in 0.05 s, right after pairing.
- After that, every probe got no reply, including after a robot power cycle.
- After a write, the port's `close()` blocked indefinitely inside macOS (a faulthandler dump showed `serialposix.py:533 in close`). Open then close without writing returned in 1.5 s, and `reset_output_buffer()` before `close()` did not help. A stuck run kept holding the port.
- A pairing for a different robot (`/dev/cu.BittleEE_SSP`) opened in about 1 s but never answered.

SPP discovery was therefore removed. A paired port can still be used by hand with `--port`; it may work. `WRITE_TIMEOUT_S` stays so a dead port raises instead of blocking a write.

### Web Bluetooth (Chrome on Android)

The web page (`web/ble.js`, a port of `BleLink`) uses the same Nordic UART service and handshake. Observed on a Pixel 7 Pro (Android 17, Chrome 156.0.8078.47) with a Bittle X (B10_260527), 2026-10-23:

- **Chooser:** Chrome's device chooser listed the robot with name-prefix filters. It showed `Bittle0D_BLE` the first time and `Bittle0D_SSP` (the cached name, as on macOS) the second time; both connected over BLE.
- **Connect:** 21.9 s and 12.1 s from the tap to `?` answered. That includes the time spent picking in the chooser, which wasn't measured separately.
- **`?` reply:** `G | Bittle X | B10_260527 | ?` the first time, `Bittle X | B10_260527 | ?` the second. Both mapped to `bittle`.
- **Echoes:** `ksit` → `sit | k` in 0.88 s, `kbalance` → `balance | k` in 0.67 s, `kwkF 3` → `wkF | up | k` about 4.5 s after sending. `kwkL` echoes `wkArmL | k` right away, and the page's `kbalance` 2 s later stopped the turn.
- **`kbf` (backflip):** reply (`|` = line break) `bf | ICM:…\tk | ICM:…\trc | ICM:…\tup | k`, about 9 s in total, and the robot ended upright. After the flip the IMU sees the robot upside down, and the **firmware itself** runs `rc` (recover, `reaction.h` `IMU_EXCEPTION_FLIPPED`). The skill's first `k` ends an IMU line, because IMU readings are printed without a newline, so the link (which waits for a line that is exactly `k`) correctly returned only on the last `k`, after the recovery. Pinned by tests in `tests/test_ble.py` and `web/ble.test.mjs`. **Residual risk:** if that first `k` ever arrived on its own line, the link would return before `rc`. Over USB, a command sent then interrupts the recovery (serial input aborts a running skill in `skill.h`). BLE input isn't checked there ("the BT_BLE is unhandled here"), so over BLE it probably waits; not verified.
- **Stop mid-walk:** during `kwkF 10`, `kbalance` was accepted in about 0.6 s, and the robot stopped and stood. Unlike the Wi-Fi notes, no retry was needed.
- **Page hidden mid-walk** (switched to another app): the page sent `kbalance` while hidden, the robot stopped, and the link stayed up.
- **Screen locked about 30 s while idle:** the link stayed connected (`gatt.connected` true), and `ksit` worked after unlocking.
- **Browsers:** all of the above is Chrome. In **Brave** (Android), the page and Gemma worked, but `requestDevice` failed with "Web Bluetooth API globally disabled": Brave turns Web Bluetooth off by default. Enabling it in `brave://flags` (search "Web Bluetooth") should help, but was not tested.
- **Not tested:** Nybble Q and Quaddle over Web Bluetooth, longer screen-off times, other phones, and a page served over https from a real host.

### Wi-Fi from a web page (phones): blocked for now

Tried on 2026-10-23: Pixel 7 Pro (Android 17, SDK 37), Chrome 156.0.8078.47 (targetSdk 36), Bittle X at `ws://192.168.1.129:81` on the same 2.4 GHz network. **No web page could open the robot's WebSocket.** The page in Chrome on the phone (`web/index.html`) therefore has no Wi-Fi mode; it uses Bluetooth LE.

- **The network path works:** from `adb shell` on the phone, `ping` reaches the robot and a raw WebSocket handshake gets `HTTP/1.1 101 Switching Protocols` (`Server: arduino-WebSocketsServer`).
- **Chrome fails before connecting:** `WebSocket connection to 'ws://192.168.1.129:81/' failed: Error in connection establishment: net::ERR_LOCAL_NETWORK_PERMISSION_MISSING`. A `fetch()` to the same address fails the same way. This happened from `http://localhost:8000` (served over `adb reverse`) and from `https://example.com`, with a real tap, and no permission prompt ever appeared.
- **Mixed content isn't the blocker on Chrome:** from the `https` page, Chrome only warned ("Insecure access is deprecated") and still tried the `ws://` connection.
- **The blocker is Android's local network permission:**
  - `dumpsys package com.android.chrome` shows `android.permission.ACCESS_LOCAL_NETWORK: granted=true, flags=[REVOKED_COMPAT|…]`.
  - `appops get com.android.chrome` shows `ACCESS_LOCAL_NETWORK: ignore`, with a `rejectTime` matching the tap.
  - Granting **Nearby devices** to Chrome (Settings → Apps → Chrome → Permissions) did not change this, and Settings shows no separate "local network" entry.
- **This contradicts Google's docs.** They say apps targeting SDK 36 or lower on Android 17 get an implicit grant, and must not request `ACCESS_LOCAL_NETWORK` before targeting SDK 37 ([Local network permission](https://developer.android.com/privacy-and-security/local-network-permission)). Another Android browser reported the same error for `192.168.x.x` on Android 17 on 2026-10-17, after a recent update ([AABrowser #170](https://github.com/kododake/AABrowser/issues/170)). The cause isn't confirmed; it may be a recent Android 17 change.
- **Not tried:** forcing the permission over adb (`adb shell am compat …` or `appops set …`). It might work on a test phone, but normal users can't do it.
- **iPhone, not tested (no device):**
  - Safari on iOS 26 has WebGPU ([web.dev](https://web.dev/blog/webgpu-supported-major-browsers)).
  - A page would have to be served over `https` (there is no `adb reverse` equivalent), and I believe WebKit refuses `ws://` from `https` pages.
  - iOS also has its own Local Network permission.
  - So expect Wi-Fi from a web page to be blocked there too.
- **What works instead:** Web Bluetooth from Chrome on Android (see above), the laptop kit's `--ws`, or a native app, which can request the permission properly. Re-test when Chrome targets SDK 37.

## Robot name (`n`)

- A bare `n` returns the robot's stored name, then the `n` echo. Verified on Quaddle over USB (2026-10-23): `SerialLink.send("n", 4)` returned `Quaddle03 | n`.
- `n<NAME>` (at most 16 characters) sets a new name. It takes effect after the robot is switched off and on. Renaming is not yet verified on hardware.
- The robot advertises over Bluetooth LE as `<name>_BLE`, e.g. `Quaddle03_BLE`. `--bluetooth --name <name>` matches `<name>` or `<name>_BLE`. Selecting a robot by name over Bluetooth is verified (Quaddle03 with Bittle0D nearby, 2026-10-23).

## Robot Wi-Fi

**2.4 GHz only.** The BiBoard's ESP32 can't join 5 GHz networks.

**On success, the robot reboots without the `w` echo.** It prints the IP, then `Rebooting to use web server.`, then calls `ESP.restart()` after 3 s (`reaction.h:466-474`). So a host must stop at the IP line instead of waiting for the echo; `wifi_setup()` does. If the robot is already on Wi-Fi, it replies `Wifi already connected to IP Address: <ip>` and then sends the `w` echo. Joining can take ~36 s: 3 attempts of ~10 s, plus 2 s between them (`webServer.h` `connectWifi`).

Over USB or Bluetooth LE, send `w%SSID%password`. The firmware parses the SSID up to the second `%` and the password after it. On success it prints `Successfully connected Wifi to IP Address: <ip>` and stores a flag so the robot reconnects later; if a web server is already connected it does nothing (`reaction.h:436-470`). Verified 2026-10-23: the robot joined over BLE, rebooted, and came back on Wi-Fi.

`python -m opencat_gemma --wifi-setup` (optionally with `--bluetooth` or `--port`) sends this command, reads the IP from the reply, and prints `--ws ws://<ip>:81`. The password is read with `getpass` and is never printed or stored. `%` in the SSID or password is rejected.

With `--ws` and no `--robot`, the starter sends `?` as a WebSocket task to detect the model, and falls back to Bittle with a warning if the reply names none.

**Verified (Bittle X, B10_260527, 2026-10-23):**
- the WebSocket connects in 0.03 s;
- `?` returns `results` text equivalent to `Bittle X | B10_260527 | ?` (the same as serial), in 0.09 s;
- detection gives `bittle`.

**Motion verified (2026-10-23):**
- `completed` for a walk arrives only when the walk ends, like the serial `k`.
- **Stopping needs a retry.** A stop sent during a walk is rejected with `Previous web task is still running`. That rejection also clears the running task (`errorWebTask`), so `WsLink.send()` retries once, and the second stop is accepted.
- Ctrl+C stopped a 20-step walk this way.

Never commit Wi-Fi passwords to a repo.

## Hardware verification

Dated 2026-10-23.

**Verified** (Bittle X, firmware B10_260527, macOS, USB, 2026-10-23):
- `?` identification.
- `kbalance` / `ksit` echo `k`.
- `kwkF 3`: 3 cycles of about 1.3 s each, auto `up`, then `k` after about 4.3 s.
- `find_robot` detection in about 1 s without a reboot.
- Chat mode end to end:
  - stand up and sit;
  - walking with a step count, which stops by itself;
  - the timed turn (`kwkL`/`kwkR`, then `kbalance`);
  - the Ctrl+C stop during a walk;
  - a refused request sending nothing.

**Failed:**
- `kwkL 90` never stopped.

**Bluetooth LE (Bittle X, macOS, 2026-10-23):** the scan finds the robot, and it connects in 0.6 s. Chat mode works (stand/sit, walking, Ctrl+C).

**Wi-Fi (Bittle X, macOS, 2026-10-23):** `--wifi-setup` works over BLE. Detection and chat mode work over WebSocket, including Ctrl+C with the retry. (Classic SPP answered `?` once, then failed; see above.)

**Quaddle (firmware Q_261022, macOS, 2026-10-23):** `?` over USB (after the wake retry) and over Bluetooth LE (the handshake reply above); `kwkF 3` / `kbkF 3` step counts; `ktrB` loops until `kbalance`; `kbalance` stops `kwkL`. These were checked with direct commands; the starter's chat mode, its Bluetooth connect and Wi-Fi have not yet been run on a Quaddle.

**Not yet verified:**
- Nybble Q.
- Windows and Linux (USB and Bluetooth).
