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
  
**Answer:**
XD will turn on the infrared light source so that it can actively emit infrared light, and the receiver will read the reflected strength to determine the distance. 

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

**Answer:**
The reflected signal is non-linear to the distance. That's why we have a fitting function. 
   
3. Is single-sample noise expected? The firmware filters heavily (dead zone, anti-jump, low-pass). A single read at 10 cm ranged from 14 to 3312, but the median over 4 s was a stable 704. Is taking the median of about 10 reads the recommended approach for a host program?
**Answer:**
Reading 10 times takes too much time via serial communication. It's better to modify the OpenCatEsp32 firmware directly to return the mean value of 10 reads. 

4. Could the firmware add a **query command** that returns its own filtered `dL`/`dR` (cm), so a host can ask "how far is the nearest object?" without re-implementing the filtering?
**Answer:**
Yes, you can add it. 

5. Does the `R` command's `pinMode(pin, INPUT)` before `analogRead` affect ADC readings on GPIO 34/35 with the ESP32 core used for this firmware?
**Answer:**
It ensures the pin is configured to analogRead mode before reading. 

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
**Answer:**
The yaw will drift over time and is unwrapped. You can zero the current yaw when receiving a turning command. 

2. Why did it load `wkArmL` (the arm variant) rather than `wkL`, on a Bittle X without an arm?
**Annswer:**
It won't load "wkArmL" if you call "wkL".
   
3. Could a turn have a **time limit** even when the gyro is present? Right now a number after `kwkL` is always read as degrees.
**Answer:**
Only degrees for a turn are meaningful. However, you may add a rule that "kwkL t1000" defines a 1000-millisecond timing. 

The starter kit currently works around this by never sending turn angles: it times turns on the computer and then sends `kbalance`.

### 3. Wi-Fi: commands requested for host programs

1. **A serial command to erase stored Wi-Fi credentials.** Today the only way is holding the BOOT button for about 2 s, which calls `resetWifiManager()` (`reaction.h:198-224`, `webServer.h:674`). A token, e.g. `w!` or a sub-command of `w`, would let a program or a classroom reset robots without touching the board.
**Answer:**
"w!" should be good to reset.

2. **An echo after a successful `w%SSID%password`.** On success the firmware prints the IP and then calls `ESP.restart()`, so the usual `w` echo never arrives. Our host code now stops at the IP line, but an explicit "joined, rebooting" line would make this unambiguous.
**Answer:**
It's better to echo the IP address before restarting.

3. **The failure message over BLE.** "Timeout: Fail to connect Wifi!" is printed with `Serial.println` only, so it never reaches BLE or WebSocket clients. Could it use `printToAllPorts`?
**Answer:**
Yes

4. **A way to stop a running WebSocket task.** While a task runs (e.g. `kwkF 20`), any new task is rejected with `Previous web task is still running`, including a stop. On 2026-10-23, Ctrl+C over Wi-Fi could not stop a walk. Rejecting a task does clear the running one's bookkeeping (`errorWebTask`) without stopping the motion, so our host retries once. Could the firmware let a stop (`d`, `kbalance`, or a `{"type":"cancel"}` message) pre-empt the running task?
**Answer:**
Yes, it's possible to modify the firmware. 

### 4. Smaller protocol questions

1. ~~**WebSocket timing.**~~ **Answered (2026-10-23, Bittle X and Quaddle):** `completed` for `kwkF 3` arrives only after the walk ends, the same as the serial `k` echo. Because of this, a stop sent during a walk is rejected as "Previous web task is still running" (see 3.4).
2. **Reboot echo.** After a reboot the firmware prints a lone `k` line first. A host waiting for a command's `k` echo could mistake that for "done". Could the boot banner avoid printing a bare `k`?
**Answer:**
You should wait for the reboot to finish before running the host program. 

### 5. Quaddle (ESP32-S3 firmware), observed on firmware `Q_261022`, 2026-10-23

1. **What does `kvt90L` ("spin 90 left") do?**
   - It loads like a looping gait: `k` arrives about 0.2 s after sending, and there is no further output.
   - Does **one cycle** turn about 90°, or is "90" a speed or style variant?
   - Is it meant to stop by itself after 90°, or to loop until the next command?
   - The starter kit currently treats it as a timed turn: it sends `kbalance` after 2 s.
**Answer:**
The program will monitor the gyroscope reading and break the loop when the yaw angle changes that amount.   
     
2. **Could step or angle counts apply to turning and backward gaits?**
   - `kwkF 3` / `kbkF 3` count cycles and then stop (this works well, about 0.5 s per cycle).
   - Turning (`…L`/`…R`, `kvt90L`) and backward (`…B`, e.g. `ktrB`) gaits loop until the next command.
   - Supporting `kvt90L 1` (one cycle) or `ktrB 3` would let a host turn or back up a known amount without timing it.
   - Do angle turns (`kwkL 90`) stop reliably on Quaddle? They never stopped on Bittle X (see section 2).
  
   
3. **Wake-from-sleep swallows the first command.**
   - When Quaddle is in charge sleep, the first command only wakes it. Its output is `Charge sleep: serial wake`, with no echo, and the command is not run.
   - Could the wake still run the command, or at least echo the token, so a host doesn't have to retry?
**Answer:**
It's better to allow it.

4. **The first BLE `?` reply has no line breaks.**
   - The first `?` after a BLE connect returns the handshake as separate notifications, with no newlines between them: `Petoi Quaddle`, `u`, `Quaddle`, `Q_261022`, `?`.
   - Later `?` replies are normal lines (`Quaddle\r\nQ_261022\r\n?\r\n`).
   - Could the handshake parts end with `\r\n` too, so hosts can parse every reply line by line?
**Answer:**
It's better to always have newlines.   
     
5. **Bluetooth stops advertising while charging?**
   - With the USB cable plugged in, Quaddle was not found in BLE scans for several minutes, even while awake and answering `?` over USB.
   - After unplugging, it was found immediately. It had advertised once earlier while plugged in.
   - Is BLE intentionally off during charge or charge-sleep?
**Answer:**
When you plug in USB, the program can sometimes detect the voltage change and freeze the robot's loop to avoid movement during charging. It will show the charging status, and you need to flip it to wake it up. It won't do anything if you don't wake it up.   
     
6. **BLE connect behavior differs from BiBoard firmware.**
   - BiBoard pushes `Petoi <MODEL>` on connect and forces rest (`d`).
   - Quaddle stays silent until asked `?`, and does not force rest.
   - Is the Quaddle behavior the intended direction for all robots? Hosts currently have to support both.
**Answer:**
Quaddle is based on ESP32S3. Its communication connection is different from the ESP32 for the mobile App. We modified the app but haven't published it yet. 
     
7. **Seven commands in the Quaddle Gemma prompt don't exist on the robot** (checked 2026-10-23 on firmware `Q_261022`). The Quaddle serial prompt for Gemma lists `kgdb` (good boy), `khg` (hug), `kchr` (cheer), `kmw` (moonwalk), `kcmh` (come here), `khu` (raise hand) and `kdg` (dig).
   - The robot answers each with `?<name>?` (e.g. `?gdb?`) and doesn't move.
   - They're also absent from the latest S3 source.
   - Should they be removed from the prompt, or are these skills planned for Quaddle?
**Answer:**
They are planned for Quaddle, but you can remove them for now to avoid confusion.   
   
8. **An unknown skill still gets the `k` "done" echo.** After `?gdb?` the firmware prints `k`, so a host that waits for the echo reports success for a command that did nothing. Could an unknown skill skip the echo, or print a distinct error token?
**Answer:**
You can remove those absent skills from the prompt so that the LLM will not call them.  
   
9. **Degree turns never stop on Quaddle either, and the Gemma prompt uses them.**
   - On `Q_261022`, `kvtL 90` printed `initial yaw: 7495.53`, `target angle: 25.53`, and kept turning until an external stop.
   - It's the same unwrapped-yaw symptom as Bittle (section 2).
   - The Quaddle Gemma prompt maps "spin / turn around" to `kvtL 360` and says `kvtL/kvtR` take degrees, so a spin request would not end by itself.
**Answer:**
The turning can finish in our tests. Maybe it's because we always test soon after rebooting, and the yaw never accumulates that large a value. We could write a wrapper to constrain the angle within 360.
     
10. **`XO` (mouse mode) disconnects BLE UART clients and echoes `k` rather than `X`.** Is that intended? A host connected over BLE loses its link on `XO`.
**Answer:**
Yes. "XO" will turn Quaddle into a Bluetooth mouse. It will advertise itself as a mouse device. 
