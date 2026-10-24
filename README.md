# opencat-gemma

Talk to a Petoi robot (Bittle X or Nybble Q) with Gemma running 100% on-device.

A starter kit for hackathon teams. Everything here runs on your laptop: Gemma through [Ollama](https://ollama.com), then USB serial or Wi-Fi to the robot. No cloud calls.

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

The robot is detected over USB by sending `?`. This detection only happens without `--port`, `--ws` or `--dry-run`. `--dry-run` and `--port` default to Bittle, so use `--robot nybble` for a Nybble. With `--ws` and no `--robot`, the model is detected over Wi-Fi, falling back to Bittle with a warning. Type a request at the `Bittle>` prompt (or `Nybble>`). Ctrl+C during a move stops the robot. To quit chat: Ctrl+D (macOS/Linux) or Ctrl+Z then Enter (Windows); Ctrl+C at the prompt also quits.

Port names differ by OS if you pass `--port`: macOS `/dev/cu.usbserial-...`, Windows `COM3`-style, Linux `/dev/ttyUSB0` or `/dev/ttyACM0`.

Other ways to run it:

```bash
# One request, then exit
.venv/bin/python -m opencat_gemma "walk forward then sit"

# No robot needed: show what Gemma returned and what would be sent
.venv/bin/python -m opencat_gemma --dry-run "walk forward then sit"
.venv/bin/python -m opencat_gemma --dry-run --robot nybble "say hi"

# Wi-Fi instead of USB (see "Connect without a cable")
.venv/bin/python -m opencat_gemma --ws ws://192.168.1.50:81 "walk forward then sit"
```

Flags: `--robot {bittle,nybble}`, `--port PORT`, `--bluetooth`, `--wifi-setup`, `--ws URL`, `--model MODEL`, `--turn-seconds N` (default 2.0), `--dry-run`. Run with `--help` for details.

If Ollama is not running or the model is missing, you get a message telling you what to run (`ollama serve` or `ollama pull ...`).

## Connect without a cable

Both were checked on Bittle X with macOS (2026-10-23). Windows and Linux are not yet verified.

**Bluetooth (BLE, no pairing needed)**
- Run `.venv/bin/python -m opencat_gemma --bluetooth`. The robot is found by scanning for a `Bittle...` or `Nybble...` name (about 8 s), strongest signal first.
- **The robot lies down (rests) when Bluetooth connects.** This is firmware behaviour. The first command makes it stand.
- Close the Petoi phone app first. Only one BLE client can be connected at a time.
- Verified on macOS (Bittle X, 2026-10-23):
  - the robot is found automatically (about 15-20 s, mostly scanning);
  - `?` answers in about 0.04 s;
  - chat mode works end to end: stand up and sit, walking with steps, and the Ctrl+C stop.
- Windows and Linux are not yet verified.
- Alternative: pair the robot's Classic Bluetooth `<name>_SSP` device and use `--port <that port>`. This may work, but it was unreliable on macOS (see `docs/protocol.md`).

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

Bittle X has 69 commands and Nybble Q has 52. Most are shared; Bittle X also has the flips, roll, jump, and some gaits (`kgp*`, `kph*`, `kmw`, and others). Nybble Q has a few of its own. Examples are below; `contract/bittle.json` and `contract/nybble.json` are the full source of truth (see [contract/README.md](contract/README.md)).

| Group | Examples | Notes |
|---|---|---|
| Walking, steps | `kwkF`, `kbk`, `ktrF`, `kcrF`, `kvtF` | Optional count 1-20 (default 3). Codes ending in `F` are steps. |
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
- Windows and Linux (USB and Bluetooth).

Gemma accuracy and latency can be checked without a robot (see below).

## Build your own

- **Any language:** `contract/<robot>.prompt.txt` (system prompt) and `contract/<robot>.schema.json` (output schema) are checked in. Always validate Gemma's reply against the schema's regex before sending anything to a robot.
- **Check Gemma on your machine:** `.venv/bin/python eval/run_eval.py --robot bittle` runs the requests in `eval/cases.json` against Ollama and prints pass/fail and latency. Use `--robot nybble` for the other contract.
- **Tests:** `.venv/bin/python -m unittest discover tests` (no Ollama or robot needed).
- **Protocol notes:** [docs/protocol.md](docs/protocol.md).
- **Android (LiteRT + BLE):** coming. Not available yet.

## Extension modules: ideas for Gemma projects

Petoi robots accept add-on sensor modules. None of them is integrated with this starter kit yet, so they are open territory for your project: for example, feeding what a sensor reports into the prompt, or letting Gemma react to it.

- [Extensible modules overview](https://guide.petoi.com/extensible-modules/introduction)
- [Back touch sensor](https://guide.petoi.com/extensible-modules/back-touch-sensor)
- [Petoi AI Vision module](https://guide.petoi.com/extensible-modules/petoi-ai-vision-module)

## License

MIT. See [LICENSE](LICENSE).
