# TODO

## Questions for the OpenCatEsp32 firmware author

Firmware under test: Bittle X, `B10_260527`, BiBoard V1.0 (build default `RevDE`), macOS, USB serial.

### 1. Double IR distance sensor: how should a host program read it?

**Context.** We read the sensor with the generic pin-read command, `R` `a` `<pin>` `~`, on pins 34 (`ANALOG1`) and 35 (`ANALOG2`). The reply is `=`, then the value, then `R`, each on its own line. We read it with the robot sitting still and an object held still about 5 cm in front of its face.

- **With the module off** (`Xd`): the readings flip between two levels, about 1000 and about 50, whether or not an object is there. We saw no step between "object present" and "object absent".
- **With the module on** (`XD`): an object gives a steady **high** reading on both pins, about 2400–3000. With no object, the readings jump erratically between about 0 and 2900.
- Meanwhile `XD` head tracking works well: the robot follows a tennis ball.

**Questions:**
1. **`XD` is required in practice (measured 2026-10-23).** What does it change electrically? We only see `pinMode(LED_PIN, OUTPUT)` and `manualHeadQ = true` in `doubleInfraredDistanceSetup()`.

   Here is the same guided test with the module **off** (`ir_probe.py --guided --no-xd`). Compare it with the module-on table under question 2:

   | Ball | none | 30 cm | 20 cm | 10 cm | 5 cm | none again |
   |---|---|---|---|---|---|---|
   | Median raw (34 / 35) | 3005 / 2398 | 3404 / 4095 | 2968 / 2880 | **4095 / 4095** | 73 / 93 | 4095 / 4095 |

   - With the module off, the readings don't track distance: 10 cm reads the same as "nothing".
   - With the module on, they step down cleanly.
2. ~~Should the raw value rise or fall as an object gets closer?~~ **Answered by measurement (2026-10-23):** it falls, as `fit()` assumes. We used the guided test (`ir_probe.py --guided`, `XD` on, a tennis ball held still, the median of about 38 reads per step):

   | Ball | Raw median, pin 34 / 35 | `fit()` |
   |---|---|---|
   | none | 4095 / 4095 | ~73 cm |
   | 30 cm | ~3900 / ~3890 | ~48 cm |
   | 20 cm | 2450 / 3000 | ~27 / ~32 cm |
   | 10 cm | 704 / 780 | ~18 cm |
   | 5 cm | 51 / 48 | ~6 cm |

   - **Calibration:** `fit()` overestimates mid-range distances. Is it calibrated for an older sensor version?
   - **Unexplained:** the "no ball again" step read 1786 / 60, not 4095.
3. Is single-sample noise expected? The firmware filters heavily (dead zone, anti-jump, low-pass). A single read at 10 cm ranged from 14 to 3312, but the median over 4 s was a stable 704. Is taking the median of about 10 reads the recommended approach for a host program?
4. Could the firmware add a **query command** that returns its own filtered `dL`/`dR` (cm), so a host can ask "how far is the nearest object?" without re-implementing the filtering?
5. Does the `R` command's `pinMode(pin, INPUT)` before `analogRead` affect ADC readings on GPIO 34/35 with the ESP32 core used for this firmware?

The troubleshooting script is `ir_probe.py` in this folder. Run it with `.venv/bin/python ir_probe.py 10 [--xd]`.

### 2. Angle turns never stop (`kwkL 90`)

`kwkL 90` started the turn but never reached its target, and the robot had to be power-cycled. The log showed:

```
Started turning gait: wkL initial yaw: 5363.72
target angle: 53.72
turning direction: LEFT (CW)
```

**Questions:**
1. The yaw reads 5363.72, outside ±180. Is it unwrapped? Is the target-reached check in `imu.h` comparing an unwrapped yaw with a normalised target?
2. Why did it load `wkArmL` (the arm variant) rather than `wkL`, on a Bittle X without an arm?
3. Could a turn have a **time limit** even when the gyro is present? Right now a number after `kwkL` is always read as degrees.

The starter kit currently works around this by never sending turn angles: it times turns on the computer and then sends `kbalance`.

### 3. Wi-Fi: commands requested for host programs

1. **A serial command to erase stored Wi-Fi credentials.** Today the only way is holding the BOOT button for about 2 s, which calls `resetWifiManager()` (`reaction.h:198-224`, `webServer.h:674`). A token, e.g. `w!` or a sub-command of `w`, would let a program or a classroom reset robots without touching the board.
2. **An echo after a successful `w%SSID%password`.** On success the firmware prints the IP and then calls `ESP.restart()`, so the usual `w` echo never arrives. Our host code now stops at the IP line, but an explicit "joined, rebooting" line would make this unambiguous.
3. **The failure message over BLE.** "Timeout: Fail to connect Wifi!" is printed with `Serial.println` only, so it never reaches BLE or WebSocket clients. Could it use `printToAllPorts`?
4. **A way to stop a running WebSocket task.** While a task runs (e.g. `kwkF 20`), any new task is rejected with `Previous web task is still running`, including a stop. On 2026-10-23, Ctrl+C over Wi-Fi could not stop a walk. Rejecting a task does clear the running one's bookkeeping (`errorWebTask`) without stopping the motion, so our host retries once. Could the firmware let a stop (`d`, `kbalance`, or a `{"type":"cancel"}` message) pre-empt the running task?

### 4. Smaller protocol questions

1. **WebSocket timing.** Over WebSocket, does `completed` for `kwkF 3` arrive after the 3 cycles finish, as the serial `k` echo does (via `deferSkillTokenEcho`)? Or does it arrive when the gait starts?
2. **Reboot echo.** After a reboot the firmware prints a lone `k` line first. A host waiting for a command's `k` echo could mistake that for "done". Could the boot banner avoid printing a bare `k`?
