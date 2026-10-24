# opencat-gemma

Talk to a Petoi robot (Bittle X, Nybble Q or Quaddle) with Gemma running 100% on-device.

## Hackathon quick start

This repo gives your team **two working demos**, so you can skip the setup trouble and start on your own idea within the first hour. Each demo already does the hard parts: Gemma turns a typed request into robot commands, a safety check rejects anything not allowed, and the robot moves.

**The rule:** every project must use a Gemma-based model running 100% on-device, with inference on the phone, board or robot you demo. These demos make no cloud calls; the network is only used to download the code and the model.

### 1. Pick a starting demo

| | Phone demo (Android) | Laptop demo |
|---|---|---|
| Gemma runs on | **The phone** (Chrome, LiteRT-LM, WebGPU) | The laptop (Ollama) |
| Robot link | Bluetooth | USB cable, Bluetooth or Wi-Fi |
| Code | JavaScript, `web/` | Python, `opencat_gemma/` |
| Fits well with | Mobile AI track; Google partner tech (Android, Pixel, LiteRT) | Fast prototyping in Python; Physical AI / IoT & Robotics |
| You need | An Android phone with Chrome and the model file | A laptop with Python 3 and Ollama |
| Start here | Open <https://gemma.petoi.com/web/demo.html> in Chrome ([steps](#android-phone-web-experimental)) | [Quickstart (laptop)](#quickstart-laptop) |

### 2. Before you touch the robot (2 minutes)

- **Find your robot's name.** Each robot advertises over Bluetooth as `<name>_BLE`, for example `Bittle0D_BLE`. Several robots will be nearby, so pick yours by name. Ask the Petoi team which name is yours.
- **Only one connection at a time.** Close the Petoi phone app and the Petoi Desktop App. Only one phone, page or laptop can be connected to a robot at once, so agree on who drives.
- **Charged battery, flat floor, about 1 m of clear space.** Keep a hand near the power switch.
- **How to stop:**
  - Phone demo: the big red **STOP** button. Leaving the page also stops a moving robot.
  - Laptop demo: **Ctrl+C**.
  - Either way, the robot stands still (`kbalance`).
- **Acrobatics are allowed with no confirmation step** (flips, roll, jump). Only ask for them with space around the robot.
- **Normal behaviour:** a Bittle X lies down when Bluetooth connects; the first command makes it stand. Walks always stop by themselves after a step count. Turns are stopped by the demo after 2 s.

### 3. When something goes wrong

| Symptom | Fix |
|---|---|
| Phone: "Web Bluetooth API globally disabled" | You're in Brave. Use Chrome, or enable Web Bluetooth in `brave://flags`. |
| Phone: the page asks for the model file again | The copy was cut short by a reload. Pick the file again and wait for `ready` before reloading. |
| Phone: the page doesn't load | Hosted: check the address (<https://gemma.petoi.com/web/demo.html>) and the phone's internet. Your own copy: is the cable plugged in, is `python3 -m http.server 8000` running, and did you run `adb reverse tcp:8000 tcp:8000` (again after re-plugging)? |
| Phone: "WebGPU: NO", or the model won't load | Update Chrome. Only a Pixel 7 Pro was tested; older phones may not support WebGPU or have enough memory. |
| Phone: Connect finds no robot, or fails (e.g. "Unsupported device") | The robot is off, or something else is connected to it: the phone's or computer's own Bluetooth settings (disconnect the robot there), the Petoi app, another tab, or a teammate's laptop. |
| Mac Chrome: "Connect failed: Unsupported device" every time | The Mac has the robot **paired** under its classic Bluetooth name (e.g. `Bittle0D_SSP`). Open System Settings → Bluetooth, choose **Forget This Device** for that entry, reload the page and connect again. This kit never uses the classic pairing. |
| Phone: robot over Wi-Fi | Not possible from a phone page yet: Android 17 blocks Chrome from the local network. Use Bluetooth. |
| Laptop: "Can't reach Ollama" or model missing | `ollama serve`, then `ollama pull gemma4:e2b-it-qat`. |
| Laptop: the USB port is busy | Close the Petoi Desktop App and any serial monitor. |
| Laptop (macOS): `[Errno 65] No route to host` over Wi-Fi | Allow Local Network for your terminal app (see [Connect without a cable](#connect-without-a-cable)), or use Terminal.app. |
| Robot won't join Wi-Fi | The robot needs a 2.4 GHz network. |
| "turn 90 degrees" only turns for 2 s | By design: angle turns never stopped on this firmware, so turns are timed. |

## Supported robots

| Robot | Firmware family | Verified on hardware |
|---|---|---|
| Bittle X | ESP32 (BiBoard) | USB, Bluetooth LE and Wi-Fi, chat mode end-to-end (macOS, firmware B10_260527) |
| Nybble Q | ESP32 (BiBoard) | Not yet verified on hardware |
| Quaddle | ESP32-S3 | Firmware Q_261022 (2026-10-23). Verified: USB detection; Bluetooth LE detection, including choosing it by name (`--bluetooth --name Quaddle03`) with a Bittle also nearby; chat over Bluetooth (stand/sit, `kwkF 3`, `kbkF 2`, timed turn, Ctrl+C stop). Wi-Fi: `--wifi-setup` over USB, detection over WebSocket, chat (stand/sit, `kwkF 3`), and the Ctrl+C stop with retry. |

Each robot is one `contract/<robot>.json` (see "Adding a robot").

A starter kit for hackathon teams. Gemma runs on-device, either on an Android phone (Chrome, LiteRT) or on a laptop ([Ollama](https://ollama.com)), and the robot connects over Bluetooth, USB or Wi-Fi. No cloud calls.

## How it works

```
request → Gemma (on-device) → JSON commands → check (allowlist) → plan (make finite) → robot (USB / Wi-Fi)
                                                       │ reject → robot untouched
safety net: timeout / Ctrl+C / error → "kbalance" (stand still)
```

Plain chat with a small model answers the same wrong command for every request (we saw `UART: kwh`, "wave head", for everything). `kwh` is a real command, just the wrong one. So there are three layers:

- **Prompt with meanings:** the system prompt lists every allowed code, what it does, and a few examples.
- **Schema-constrained output:** Ollama is given a JSON schema with a regex, so replies must look like a command.
- **Allowlist check:** the reply is validated again against the same regex before anything is sent. Not every runtime enforces schemas, so we never trust model output.

## Quickstart (laptop)

Needs Python 3 (tested on 3.15) and Ollama. Tested on macOS only; Windows and Linux not yet verified.

macOS/Linux:

```bash
ollama pull gemma4:e2b-it-qat
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

Windows (not yet verified):

```bat
ollama pull gemma4:e2b-it-qat
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

Linux note: you may need serial-port permission, e.g. `sudo usermod -aG dialout $USER`, then log out and back in.

Plug in the robot, switch it on, and close the Petoi Desktop App and any serial monitor (only one program can hold the USB port). Then start chat mode (macOS/Linux; on Windows use `.venv\Scripts\python -m opencat_gemma`):

```bash
.venv/bin/python -m opencat_gemma
```

```
Found bittle on /dev/cu.usbserial-...      (macOS example)
Chatting with bittle. Ctrl+C stops a move; Ctrl+D (or Ctrl+C here) quits.
Bittle> walk forward then sit
```

The robot is detected over USB by sending `?`. This detection only happens without `--port`, `--ws` or `--dry-run`. `--dry-run` and `--port` default to Bittle, so use `--robot nybble` or `--robot quaddle` for the others. With `--ws` and no `--robot`, the model is detected over Wi-Fi, falling back to Bittle with a warning. Type a request at the `Bittle>` prompt (or `Nybble>`, `Quaddle>`). Ctrl+C during a move stops the robot. To quit chat: Ctrl+D (macOS/Linux) or Ctrl+Z then Enter (Windows); Ctrl+C at the prompt also quits.

Port names differ by OS if you pass `--port`: macOS `/dev/cu.usbserial-...`, Windows `COM3`-style, Linux `/dev/ttyUSB0` or `/dev/ttyACM0`.

Other ways to run it:

```bash
# One request, then exit
.venv/bin/python -m opencat_gemma "walk forward then sit"

# No robot needed: show what Gemma returned and what would be sent
.venv/bin/python -m opencat_gemma --dry-run "walk forward then sit"
.venv/bin/python -m opencat_gemma --dry-run --robot nybble "say hi"
.venv/bin/python -m opencat_gemma --dry-run --robot quaddle "walk backward 2 steps"

# Wi-Fi instead of USB (see "Connect without a cable")
.venv/bin/python -m opencat_gemma --ws ws://192.168.1.50:81 "walk forward then sit"
```

Flags: `--robot {bittle,nybble,quaddle}`, `--port PORT`, `--bluetooth`, `--name NAME`, `--robot-name [NEW]`, `--wifi-setup`, `--ws URL`, `--model MODEL`, `--turn-seconds N` (default 2.0), `--dry-run`. Run with `--help` for details.

If Ollama is not running or the model is missing, you get a message telling you what to run (`ollama serve` or `ollama pull ...`).

## Connect without a cable

Both were checked on Bittle X with macOS (2026-10-23). Windows and Linux are not yet verified.

**Bluetooth (BLE, no pairing needed)**
- **Before you start (any Petoi robot):** if the robot shows up as *connected* in your computer's Bluetooth device list (macOS: System Settings → Bluetooth), disconnect it there, or remove it, first. Our tool makes its own connection. Once the system connection is gone, running `--bluetooth` makes the system ask for Bluetooth permission; allow it. (Observed on macOS with Quaddle, 2026-10-23.)
- Run `.venv/bin/python -m opencat_gemma --bluetooth`. With several robots nearby, use `--bluetooth --name <name>` instead (see "Several robots in one room" below). The robot is found by scanning for a `Bittle...`, `Nybble...`, `Quaddle...` or `Petoi...` name (about 8 s), strongest signal first, and identified with `?`.
- **Bittle X and Nybble Q lie down (rest) when Bluetooth connects.** This is firmware behaviour. The first command makes them stand. Quaddle does not.
- **Quaddle may stop advertising Bluetooth while plugged in and charging.** It was not found with the USB cable connected, and was found right after unplugging it (2026-10-23). If `--bluetooth` can't find a Quaddle, unplug the cable, or power-cycle it.
- **Quaddle freezes its motion while charging.** When the USB cable is plugged in, it may show its charging status and ignore movement. Flip it over to wake it up.
- Close the Petoi phone app first. Only one BLE client can be connected at a time.
- Verified on macOS (Bittle X, 2026-10-23):
  - the robot is found automatically (about 15-20 s, mostly scanning);
  - `?` answers in about 0.04 s;
  - chat mode works end to end: stand up and sit, walking with steps, and the Ctrl+C stop.
- Windows and Linux are not yet verified.
- Alternative: pair the robot's Classic Bluetooth `<name>_SSP` device and use `--port <that port>`. This may work, but it was unreliable on macOS (see `docs/protocol.md`).

**Several robots in one room**
- `--bluetooth` on its own connects only if exactly one Petoi robot is nearby. If there are several, it refuses to guess: it lists them with their signal strength and exits, so you never end up driving someone else's robot.
- Always connect with your robot's name:
  1. Over USB, run `.venv/bin/python -m opencat_gemma --robot-name`. It prints your robot's Bluetooth name (for example `Quaddle03_BLE`) and the command to connect.
  2. Optional: give it your team name with `--robot-name Team7` (at most 16 characters: letters, digits, `-` and `_`), then switch the robot off and on. It then advertises as `Team7_BLE`.
  3. Connect with `.venv/bin/python -m opencat_gemma --bluetooth --name Team7`. The name is matched exactly, with or without `_BLE`, ignoring upper/lower case.
- `--robot-name` also works with `--port` or `--bluetooth --name <name>`.
- Status: reading the name over USB on a Quaddle is verified (2026-10-23). Choosing a robot by name over Bluetooth is verified too (Quaddle03 picked with Bittle0D nearby; the bare `--bluetooth` refused and listed both). Renaming is **not yet verified on hardware**.
- The note above still applies: disconnect the robot in your computer's Bluetooth device list first.

**Wi-Fi**
- **The network must be 2.4 GHz.** The robot's ESP32 chip can't join 5 GHz networks. Many routers broadcast both bands under one name; if joining fails, use the router's 2.4 GHz network (sometimes a separate name, e.g. ending in "-2.4G"). Phone hotspots often default to 5 GHz, so switch them to 2.4 GHz ("maximize compatibility" on iPhone).
- One-time setup, over USB, or over Bluetooth LE with `--wifi-setup --bluetooth`: `.venv/bin/python -m opencat_gemma --wifi-setup`. It asks for the Wi-Fi name and password (the password is not shown) and prints the robot's `ws://` URL. `%` is not allowed in either, because the firmware uses it as a separator.
- Then: `.venv/bin/python -m opencat_gemma --ws ws://<ip>:81`.
- **macOS 15+: allow Local Network access.** If you get `[Errno 65] No route to host` even though `ping <ip>` works, macOS is blocking Python from the local network. To fix it:
  - turn on **System Settings → Privacy & Security → Local Network** for the app you run Python from (Terminal, iTerm, VS Code, …);
  - then reopen that app.

  This was seen on macOS 15.1, where `curl` reached the robot but Python was blocked. **iTerm2 was never offered the permission** (it didn't appear in the list), while **Terminal.app** worked. If your terminal app isn't listed, run the starter from Terminal.app.
- Forgot the IP? `.venv/bin/python -m opencat_gemma --bluetooth --wifi-ip` (or over USB without `--bluetooth`) asks the robot and prints it. No password is needed.
- **Erase the stored Wi-Fi network:** there is no software command for this in the current firmware. Use the **BOOT button** on the BiBoard:
  - **Hold it for ~2 s,** until a countdown from 10 finishes printing. The robot erases its Wi-Fi credentials and reboots.
  - **A short press** instead reboots into Wi-Fi Manager mode: the robot opens its own `<name> WifiConfig` network for about 60 s, so you can pick a network from a phone.
  - Both behaviours are from the firmware source (`reaction.h`, `webServer.h`), not yet tried on hardware.
- The robot is expected to remember the network (not yet checked). Its IP may change when the router reassigns it.
- Never commit Wi-Fi passwords.

## Commands

Bittle X has 69 commands, Nybble Q 52 and Quaddle 100. Most are shared; Bittle X also has the flips, roll, jump, and some gaits (`kgp*`, `kph*`, `kmw`, and others). Nybble Q has a few of its own. Examples are below; `contract/<robot>.json` is the full source of truth (see [contract/README.md](contract/README.md)).

**Quaddle differences:** its list combines the command table of the firmware author's Gemma prompt for Quaddle with the public web-coding list (codes in its firmware), minus 7 codes the robot doesn't have (`kgdb khg kchr kmw kcmh khu kdg`, checked on firmware Q_261022).
- It walks backward with `kbkF` (Bittle X and Nybble Q use `kbk`).
- It has its own gaits: `kbdF`, `kmarchF`, `ktiptoeF`, `kdragWkF`, `kpaceF`, `ktriCatF` (steps), and `ksideL`/`ksideR`, `kvt2L`/`kvt2R`, `ktriCatL`/`ktriCatR`, `kcircle2L`, `kslide`, the `kq*` moves (`kqDance`, `kqStep`, `kqWheel`, `kqScoot`, ...), `ktrB`, `kwkB`, `kbkL`/`kbkR`, `kbbbk`, `kgallop`, `kbackScoot` and `kvt90L`/`kvt90R` (timed).
- Its own behaviours include `kbuttUp`, `kpd2`, `krc`, `krc2`, `krcL`/`krcR`, `kjumpSlide` and `khighbar`.
- **Eye colours:** `vcr` red, `vcb` blue, `vco` orange, `vcy` yellow, `vcg` green, `vcp` pink, `vcv` purple. **Eye expressions:** `veH` happy, `veS` sad, `veP` squint, `ved` clear, and the talking forms `velT`, `veTH`, `veTS`, `veTP`, `vetL`, `vet`. None of them move the robot.
- **`T`** replays the skill the robot just learned. **`d`** rests (standby).
- **Joint moves:** `m0 <angle>` turns the head (positive = left), `m8 <angle>` / `m9 <angle>` move the left / right front leg (negative = forward). The angle must be -90 to 90; only joints 0, 8 and 9 are allowed.
- **Mouse mode:** `XO` turns the robot into a Bluetooth mouse (its motion moves the computer's cursor); `Xo` turns it back into a dog. Either one ends the request: any command after it is dropped. **`XO` is refused over `--bluetooth`,** because it disconnects the Bluetooth link; use USB or Wi-Fi.
- **No degree turns:** `kvtL`/`kvtR` are timed turns, sent without a number. `kvtL 90` never stops by itself on current firmware (Q_261022, the same bug as on Bittle X), so the allowlist rejects angles.
- It has none of `kvtF`, `ktbl` or the `kflip*` codes.

## Understanding the sensors' input
Use the serial command 'X' to activate a single sensor's demo. For example, "XD" turns on DoubleDistanceSensor, and "Xd" turns it off. "XT" turns on the DoubleTouchSensor. The supported sensor list is in OpenCat.h. 
You can use the serial command "Ra", "Rd", "Wa", "Wd" to AnalogRead, DigitalRead, AnalogWrite, DigitalWrite certain pins. Read the demo code and comments to understand the signal's properties before writing control logic. 

**Nybble Eye Color**
The Nybble RGB ultrasonic eye color is set with the uppercase token C, followed by five raw bytes and a ~ terminator (byte value 126). The on-wire format is C, red, green, blue, eye index, effect, ~. Red, green, and blue are each 0–125; 126 cannot be used as a color because it is the binary-command terminator. The eye index is 0 for changing both eyes, 1 for the right eye, and 2 for the left eye. The effect is 0 for breathing, 1 for rotate, 2 for flash, and 3 for steady. Rotate and flash apply to all LEDs regardless of the eye index. A single C with no payload cancels manual color and returns the eyes to automatic distance-based colors. An in-firmware example of both eyes breathing red is the byte array {125, 0, 0, 0, 0, 126}.

**Backtouch sensor**
The back-touch sensor is read with analogRead(BACKTOUCH_PIN) on GPIO 38. The ADC is 12-bit, so the raw value is 0–4095. A connected sensor with no touch reads 4095. A reading below 2400 is a touch: integer-divide it by 600 to get a bin from 0 to 3, then map that bin through touchPadMap[] = {1, 3, 4, 2} to a pad index. A reading of 2400 or higher is index 0, meaning no touch. The bins are 0–599 → index 1 (Front Left), 600–1199 → index 3 (Center), 1200–1799 → index 4 (Back), and 1800–2399 → index 2 (Front Right). The location name is touchLocation[index - 1], whose entries in order are "Front Left", "Front Right", "Center", and "Back".

| Group | Examples | Notes |
|---|---|---|
| Walking, steps | `kwkF`, `kbk` (Quaddle: `kbkF`), `ktrF`, `kcrF`, `kvtF` | Optional count 1-20 (default 3). Codes ending in `F` are steps. |
| Walking, timed | `kwkL`, `kwkR`, `kvtL`, `kvtR`, `ktrL`, `kcrR` | The computer waits (default 2.0 s), then sends `kbalance`. |
| Postures | `ksit`, `krest`, `kbalance`, `kup`, `kstr`, `ktbl`, `krc` | Sit, lie down, stand, stretch, table, recover. |
| Behaviors | `khi`, `khsk`, `kfiv`, `knd`, `kpu`, `kpd`, `kwh`, `kbx` | Wave, handshake, high five, nod, push ups, play dead, wave head, boxing. |
| Acrobatics | `kbf`, `kff`, `kflip`, `kflipD`, `kflipF`, `krl`, `kjmp`, `klpov`, `khds` | Flips, roll, jump, leap, handstand. Most are Bittle X only. |

The allowlist accepts every command in the contract and nothing else. There is no confirmation step for acrobatics.

## Safety

- **Walks always carry a step count.** If the request gives none, 3 is used. The robot finishes the walk and stands up by itself.
- **Turns are timed by the computer.** It sends the turn, waits `--turn-seconds` (default 2.0), then sends `kbalance`.
- **Timeout, error or Ctrl+C sends `kbalance`.** Walks time out after `5 + 2 x steps` seconds, other commands after 10 s. If even that stop fails, the program tells you to switch the robot off.
- **The list includes acrobatics** (flips, roll, jump, handstand). Run on the floor with clear space and a charged battery, and do not run them while the USB cable could snag.
- **Hardware testing so far:** only `kwkF 3`, `kbalance`, `ksit`, `?` and chat mode have been tested on a robot. The other commands have not. Nybble Q is not yet tested on hardware.
- **Keep a hand near the power switch,** and run on a flat surface with space around the robot.
- **Known bug: angle turns never stop.** On firmware B10_260527, `kwkL 90` did not end on a Bittle X and the robot had to be power-cycled. So the allowlist rejects angles, and a request like "turn 90 degrees" becomes a plain timed turn. Details in [docs/protocol.md](docs/protocol.md).

## Verification status

Be careful what you assume. Here is what has and has not been checked.

Tested on hardware (Bittle X, USB, firmware B10_260527):
- `kbalance`, `ksit`, `kwkF 3` and `?` behave as described in [docs/protocol.md](docs/protocol.md).
- Chat mode on macOS over USB, end to end:
  - stand up and sit;
  - walking with a step count, which stops by itself;
  - the timed turn (`kwkL`/`kwkR`, then `kbalance`);
  - the Ctrl+C stop during a walk;
  - a refused request ("do a backflip") sending nothing.
- `kwkL 90` failed (the bug above).

Bluetooth LE and Wi-Fi (macOS, Bittle X, 2026-10-23):
- **Bluetooth LE:** chat mode end to end, covering stand/sit, walking with steps, and the Ctrl+C stop.
- **Wi-Fi:**
  - `--wifi-setup` over Bluetooth;
  - robot detection over WebSocket;
  - chat mode, covering stand/sit, walking with steps, and the Ctrl+C stop. The stop needs one retry, because the firmware rejects a new task while a walk runs; see docs/protocol.md.

Not yet verified on hardware:
- Nybble Q.
- Quaddle beyond the checks in "Supported robots": the eye, expression, joint, `T`, `d` and `XO`/`Xo` commands were only sent directly over USB (their replies checked), not yet through chat.
- The changed Bluetooth connect (it now always asks `?`) on Bittle X.
- Windows and Linux (USB and Bluetooth).

Gemma accuracy and latency can be checked without a robot (see below).

## Build your own

- **Any language:** `contract/<robot>.prompt.txt` (system prompt) and `contract/<robot>.schema.json` (output schema) are checked in. Always validate Gemma's reply against the schema's regex before sending anything to a robot.
- **Check Gemma on your machine:** `.venv/bin/python eval/run_eval.py --robot bittle` runs the requests in `eval/cases.<robot>.json` (or `eval/cases.json` if there is none) against Ollama and prints pass/fail and latency. Use `--robot nybble` or `--robot quaddle` for the other contracts.
- **Tests:** `.venv/bin/python -m unittest discover tests` (no Ollama or robot needed).
- **Protocol notes:** [docs/protocol.md](docs/protocol.md).
- **Android phone (web, experimental):** Gemma on the phone and the robot over Bluetooth, from Chrome. See [Android phone](#android-phone-web-experimental) below.

## Android phone (web, experimental)

Gemma 4 E2B runs **on the phone**, in Chrome (LiteRT-LM web 0.18.0, WebGPU), and the robot is driven over Bluetooth LE (Web Bluetooth). Verified on a Pixel 7 Pro (Android 17, Chrome 156) with a Bittle X, 2026-10-23. **The pages are hosted at <https://gemma.petoi.com/web/>:** open them in Chrome. No laptop, cable or setup is needed, and Gemma still runs on your device (see [docs/web.md](docs/web.md)). The hosted demo also worked in desktop Chrome on a Mac with a Quaddle (2026-10-24).

### What you need

- An Android phone with **Chrome**. In Brave, Web Bluetooth is off by default (see "Browsers" below).
- Only if you serve the pages yourself (to change the code): a USB cable, **USB debugging** on the phone, and `adb` and Python 3 on the laptop.
- The model file on the phone (see [The model](#the-model) below).
- The robot switched on, with the **Petoi phone app closed** (only one Bluetooth client can connect).

### The model

**Tested:** `gemma-4-E2B-it-web.litertlm` (Gemma 4 E2B, instruction-tuned, web build, 2,008,432,640 bytes) from the Hugging Face repo [litert-community/gemma-4-E2B-it-litert-lm](https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm). No login needed.

- Direct download: <https://huggingface.co/litert-community/gemma-4-E2B-it-litert-lm/resolve/main/gemma-4-E2B-it-web.litertlm>
- Put it in the phone's **Downloads**: open the link in Chrome on the phone, or download it on the laptop and run `adb push gemma-4-E2B-it-web.litertlm /sdcard/Download/`.
- **Other files in the same repo were not tested** with these pages:
  - `gemma-4-E2B-it.litertlm` (2.6 GB, the same size as the E2B model the Android AI Edge Gallery app shows);
  - `gemma-4-E2B-it-gpu.litertlm`;
  - the chip-specific builds.
- **Gemma 4 E4B** (`litert-community/gemma-4-E4B-it-litert-lm`) was tried before the library version was fixed, and failed for that reason. It was not retried.
- The library version matters: the pages pin `@litert-lm/core` 0.18.0 (`web/litert.js`), because 0.18.1 failed to load the model.

### Open the page

- **Hosted (easiest):** open <https://gemma.petoi.com/web/demo.html> in Chrome. Nothing else to set up.
- **Serving your own copy** (after changing the code):
  1. On the laptop, from the repo root: `python3 -m http.server 8000`.
  2. `adb reverse tcp:8000 tcp:8000`. Run it again after re-plugging the phone.
  3. On the phone, open the `localhost` address below in Chrome. Keep the cable plugged in: the page is served over it.
  - Your own copy and the hosted site keep **separate** model copies, so each asks for the model file on its first visit.

### Which page?

| Page | Use it to | Hosted | Your own copy |
|---|---|---|---|
| **Demo** (`web/demo.html`) | Show it off: type a request, and the robot does it | <https://gemma.petoi.com/web/demo.html> | `http://localhost:8000/web/demo.html` |
| **Test** (`web/index.html`) | Check Gemma (eval: accuracy and speed, no robot needed), try requests, read the raw log | <https://gemma.petoi.com/web/> | `http://localhost:8000/web/` |

Use one page at a time with the robot: only one page can hold the Bluetooth connection. Leaving a page drops its connection.

### Demo page

1. Open <https://gemma.petoi.com/web/demo.html> (or your own copy).
   - **First visit:** the page asks for the model file. Pick `gemma-4-E2B-it-web.litertlm`. It loads (about 17 s), then says "keeping a copy on this phone…" (about 30 s). **Don't reload until it says `ready`,** or the copy is lost.
   - **Later visits:** the model loads from that copy by itself (about 17 s). Use "Change model" to pick a different file.
2. Tap **Connect robot**, pick the robot (`Bittle…_BLE`), and wait about 10 s ("connecting…"). A Bittle X lies down when Bluetooth connects; the first command makes it stand.
3. Type a request (for example "walk forward then sit") and tap **Go**. The chat shows Gemma's commands, then a ✓ and the robot's reply for each command. Requests that aren't allowed show "not allowed, robot untouched".
4. **STOP** (red, full width) stops the robot at any time, even while Gemma is still thinking. Leaving the page (switching apps) also stops a moving robot.

### Test page

1. Open <https://gemma.petoi.com/web/> (or your own copy), pick the model file (on **every** visit; this page keeps no copy), and tap **Load model** (about 7 s, plus about 7 s to read the robot's prompt).
2. **Run eval** runs the 16 requests in `eval/cases.json` and prints pass/fail and timing per request (Pixel 7 Pro: 15/16, about 2 s per request). No robot needed.
3. Optional: tap **Connect robot (Bluetooth)**, type in the box, and tap **Ask**; the robot runs the result. **Stop** stops it. **Copy log** copies the log.

### Browsers, iPhone and Wi-Fi

- **Use Chrome.** Everything here was tested in Chrome 156. Other Chromium-based browsers may work but are not tested.
- **Brave needs setup:**
  - Brave turns Web Bluetooth off by default, so **Connect robot** fails with "Web Bluetooth API globally disabled".
  - To turn it on: open `brave://flags`, search for **Web Bluetooth**, set it to **Enabled**, then tap **Relaunch**. The demo was not tested in Brave after enabling it.
  - Brave also keeps its own copy of the model, because storage is per browser, so the first visit in Brave asks for the model file again.
- **Not on iPhone:** no iOS browser supports Web Bluetooth.
- **No Wi-Fi mode on phones yet:** on Android 17, Chrome is blocked from the local network (`ERR_LOCAL_NETWORK_PERMISSION_MISSING`, see `docs/protocol.md`).
- How it works and where each part runs: [docs/web.md](docs/web.md). Protocol details: `docs/protocol.md`. Results: `docs/superpowers/plans/2026-10-23-web-gemma-connection.md`, `…-web-prefill-reuse.md`, `…-web-bluetooth.md` and `…-bluetooth-demo.md`.

## Adding a robot

A new robot needs data files, not code changes:

1. **Write `contract/<robot>.json`** with `robot` (the prompt's name, e.g. "Bittle X robot dog"), `model` (the name the robot reports to `?`), `ble_prefix` (the start of its Bluetooth name, lowercase), and `examples`.
2. **Generate its `codes`** with `tools/build_contract.py`. It takes Petoi's public web-coding skill list (`motion_skills.js` and `translations.js`) and keeps only the codes in your firmware's skill table:

   ```bash
   .venv/bin/python tools/build_contract.py --robot <robot> --firmware <firmware skill-table header> --web <dir>
   ```

   First add the robot's entry (core codes, exclusions, label fixes, kind rules) to `ROBOTS` in `tools/build_contract.py`.
3. **Regenerate the prompt and schema:** `.venv/bin/python -m opencat_gemma.contract`.
4. **Add `eval/cases.<robot>.json`** using that robot's codes, run `eval/run_eval.py --robot <robot>`, and tune only `examples` until every case passes.

The CLI's `--robot` choices, `?` detection and the Bluetooth scan all read the contract files.

## Extension modules: ideas for Gemma projects

Petoi robots accept add-on sensor modules. None of them is integrated with this starter kit yet, so they are open territory for your project: for example, feeding what a sensor reports into the prompt, or letting Gemma react to it.

- [Extensible modules overview](https://guide.petoi.com/extensible-modules/introduction)
- [Back touch sensor](https://guide.petoi.com/extensible-modules/back-touch-sensor)
- [Petoi AI Vision module](https://guide.petoi.com/extensible-modules/petoi-ai-vision-module)

## License

MIT. See [LICENSE](LICENSE).
