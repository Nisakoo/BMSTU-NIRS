// Newer Node versions ship navigator.locks; tests pass fake locks explicitly
// and otherwise run in the same environment as Node 22 and the old behaviour.
Object.defineProperty(globalThis.navigator, "locks", {
  value: undefined,
  configurable: true,
});
