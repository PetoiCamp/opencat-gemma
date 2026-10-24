# The phone web page: where things run

`web/demo.html` (and the test page `web/index.html`) are static files: HTML, JavaScript and the checked-in contract files. They are hosted at <https://gemma.petoi.com/web/> (demo: <https://gemma.petoi.com/web/demo.html>). They can also be served from a laptop over USB (`adb reverse`, `http://localhost:8000`) when you change the code. Either way, nothing runs on the server.

## What each part does once the page is hosted

| Part | Where it comes from | Where it runs |
|---|---|---|
| Page code (`demo.html`, `gemma.js`, `ble.js`, …) and the contract files | Your `https` host (static files only) | In Chrome on the phone |
| LiteRT-LM engine (JS + WASM) | jsDelivr CDN (`@litert-lm/core@0.18.0`) | On the phone |
| The model (`gemma-4-E2B-it-web.litertlm`, 2.0 GB) | First visit: picked from the phone's storage. Later visits: the copy the page keeps in OPFS (see below). | — |
| **Gemma inference** | — | **The phone's GPU, through WebGPU** |
| Bluetooth to the robot | — | Phone ↔ robot directly (Web Bluetooth) |

**What that means:**

- **Requests never leave the phone.** The host doesn't see prompts or commands, because there's no backend.
- **The network is needed to load the page** on each visit (host and CDN). Gemma and Bluetooth don't need it after that. Working fully offline would need a service worker, which is not built.
- **`https` is required.** WebGPU and Web Bluetooth only work on secure pages: `https://…`, or `localhost`, which is how the USB setup works.
- **Use Chrome.** Brave turns Web Bluetooth off by default (see the README).
- **Not built yet:** the demo doesn't download the model from Hugging Face when there's no copy yet; it asks for the file instead. The test page (`index.html`) can load from a URL.

## OPFS: the model copy on the phone

OPFS (Origin Private File System) is a private folder the browser keeps for each origin (scheme + host + port).

- **Per origin and per browser.** The copy made at `http://localhost:8000` is not visible at a hosted `https://…` address, or in another browser. The first visit there asks for the model file again.
- **Private.** It doesn't show in the phone's Files app, and other sites can't read it.
- **Large files are fine.** Chrome reported a quota of about 10.7 GB on a Pixel 7 Pro (2026-10-23).
- **Writes are all or nothing.** Data is written to a temporary `.crswap` file and committed only when the copy completes, which took about 33 s for 2 GB on the Pixel 7 Pro. `web/model_store.js` writes a small `model.json` record only after a complete copy, so a copy cut short (a reload or a closed tab) is never loaded.
- **It can disappear.**
  - Clearing Chrome's site data deletes the copy.
  - The browser may evict it under storage pressure. The page reported `navigator.storage.persisted()` = `false`. Asking for persistence (`navigator.storage.persist()`) is not implemented.
  - Keep the original file, so you can pick it again.
