// @litert-lm/core pinned to 0.18.0, the version Google's hosted chat demo ships. 0.18.1's JS does not match its own
// WASM (Engine.create fails with "getMutableMainExecutorSettings is not a function" on a Pixel 7 Pro, 2026-10-23).
export { Engine, SamplerType } from "https://cdn.jsdelivr.net/npm/@litert-lm/core@0.18.0/+esm";
