# Bluetooth Demo Page: Design

Date: 2026-10-23. Status: approved by the user in chat; this document is for review before the plan.

## Goal

A clean demo on an Android phone. You type a request, Gemma 4 E2B on the phone turns it into robot commands, the allowlist checks them, and the robot runs them over Bluetooth LE, with a big Stop button. It sits beside the existing test harness (`web/index.html`) and doesn't replace it.

## Decisions

- **Page delivery:** served from the Mac over USB for now (`http://localhost:8000/web/demo.html` through `adb reverse`). `localhost` is a secure context, which WebGPU and Web Bluetooth need. Hosting on `https` is decided later. The page must not depend on `localhost`, so it can be hosted unchanged.
- **Input:** typed text only. Voice is out of scope until on-device speech recognition is researched; Chrome's recognizer may send audio to Google's servers.
- **Robot link:** Bluetooth LE only (`web/ble.js`). Wi-Fi from a phone page is blocked on Android 17 (`docs/protocol.md`).
- **Robots:** whatever `?` identifies (Bittle, Nybble, Quaddle), using the existing contracts. Only Bittle X is verified on hardware.

## User flow

1. Open the page. The status line shows the model and robot state.
2. **Model:**
   - First visit: the user picks `gemma-4-E2B-it-web.litertlm`. The page copies it into the origin private file system (OPFS), then loads it.
   - Later visits: the model loads from OPFS automatically, with no picker.
   - A "Change model" control lets the user pick again (and replaces the stored copy).
   - If the OPFS copy fails (quota, unsupported), the page loads straight from the picked file and says that the model will need to be picked again next time.
3. **Connect robot:** one tap, then Chrome's device chooser (a tap is required on every visit). The status shows the robot's name and model. On disconnect, the status says so and Go is disabled until the robot is connected again.
4. **Request:** type, then tap **Go**. A chat history entry shows:
   - the request;
   - Gemma's commands, or "not allowed, robot untouched" (with the reason), or "nothing to do" for `[]`;
   - each command as it is sent, with ✓ and the robot's reply, or ✗ and the error;
   - the Gemma time and the total time.
5. **STOP:** full width, always visible. It aborts a running plan, which sends `kbalance`; when idle it sends `kbalance` directly. The page also stops a running plan when it is hidden (as in the test page).

## Screen layout (top to bottom)

- A status line: model (`not loaded` / `loading…` / `ready` / `error: …`) and robot (`not connected` / `Bittle0D_BLE (bittle)` / `disconnected`).
- The model controls (a file picker shown only when needed, plus "Change model"), and **Connect robot**.
- The chat history (scrolls; the newest entry at the bottom).
- The request input and **Go**.
- **STOP**: full width, red, at least 56 px tall, enabled whenever a robot is connected.
- Light and dark mode through `prefers-color-scheme`. Phone width with a 16 px gutter and no horizontal scroll. No eval or debug controls.

## Code structure

| Unit | Responsibility | Depends on |
|---|---|---|
| `web/gemma.js` (new, extracted from `index.html`) | `createGemma(model, robot)` → `{ ask(text) → {out, secs, commands, error}, setRobot(robot) }`. Loads the engine, prefills the system prompt once, and clones per request with deferred delete (the `clone_defer` rule from `2026-10-23-web-prefill-reuse.md`). Loads the robot's prompt, pattern, and codes. | `@litert-lm/core@0.18.0`, `parse.js` |
| `web/model_store.js` (new) | `saveModel(file, root)`, `loadModel(root)` → `File` or `null`, `clearModel(root)`. `root` is an OPFS directory handle (`navigator.storage.getDirectory()`), injected so tests can fake it. | OPFS API |
| `web/demo.html` (new) | UI and wiring only: status, chat history, Connect, Go, STOP, stop on hide. | `gemma.js`, `model_store.js`, `ble.js`, `runner.js` |
| `web/index.html` (changed) | The test harness, now using `gemma.js` instead of its inline Gemma code. Its behaviour and the `window.__test` hook stay the same. | `gemma.js`, … |
| `web/ble.js`, `web/runner.js`, `web/parse.js` | Unchanged. | |

## Error handling

- Model load or prefill failure: the status shows `error: <message>`, and Go stays disabled.
- Gemma reply not allowed: the chat entry shows the reason, and nothing is sent.
- Robot error or timeout during a plan: `runner.run` already sends `kbalance`. The chat entry marks the failed command ✗ and shows the error; if STOP also failed, it shows "switch the robot off".
- A STOP the user requested is shown as "stopped", not as an error.

## Testing

- `node --test web/`: new tests for `model_store.js` with a fake directory handle (save then load returns the same bytes, load without a saved model returns `null`, clear removes it, a failed write leaves no partial file) and for `gemma.js` pure helpers if any are extracted. Existing tests (25) keep passing; Python (132) is unchanged.
- `index.html` refactor: rerun the eval on the phone; expected 15/16 at about 2 s per request, as before.
- Hardware checks on the Pixel 7 Pro with the Bittle X:
  - first visit (pick, copy, load);
  - reload (automatic load from OPFS, with the time recorded);
  - Connect;
  - "stand up then sit";
  - "walk forward 5 steps", then STOP;
  - a refused request;
  - hiding the page mid-walk.

## Out of scope

Voice input, `https` hosting, Wi-Fi, iPhone, choosing between several robots beyond Chrome's chooser, and changes to the safety rules.

## Risks

- **OPFS copy of 2 GB:** speed and quota on phones are untested. There's a fallback to the picked file (see the flow).
- **Moving the inline Gemma code into `gemma.js`:** a regression risk for the test harness, covered by rerunning the eval.
