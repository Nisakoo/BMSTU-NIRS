import assert from "node:assert/strict";
import test from "node:test";

class FakeElement {
  constructor(text = "") {
    this.textContent = text;
    this.value = "";
    this.disabled = false;
    this.children = [];
    this.listeners = new Map();
    this.style = {};
    this.dataset = {};
    this.classes = new Set();
    this.classList = {
      add: name => this.classes.add(name),
      remove: name => this.classes.delete(name),
      contains: name => this.classes.has(name),
    };
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  dispatch(type, event = {}) {
    return this.listeners.get(type)?.({ preventDefault() {}, ...event });
  }

  append(child) {
    this.children.push(child);
  }

  setAttribute() {}
  focus() {}
  requestSubmit() { return this.dispatch("submit"); }
  get scrollHeight() { return 30; }
}

class FakeEventSource {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.listeners = new Map();
    FakeEventSource.instances.push(this);
  }

  addEventListener(type, listener) {
    this.listeners.set(type, listener);
  }

  emit(type, data = {}) {
    this.listeners.get(type)?.({ data: JSON.stringify(data) });
  }

  emitRaw(type, data) {
    this.listeners.get(type)?.({ data });
  }

  fail() { this.onerror?.(); }

  close() { this.closed = true; }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

let moduleCounter = 0;

async function setup(submitResponse, { autoReady = true, createStatus = 201, createStatuses } = {}) {
  const ids = ["#saiForm", "#saiPrompt", "#saiMessages", ".sai-send", "#saiStatus", "#saiStatusText", ".sai-hint"];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  const chips = [new FakeElement("Про дружбу")];
  const requests = [];
  const timers = new Map();
  const timerDelays = [];
  let nextTimer = 0;
  let createCalls = 0;
  FakeEventSource.instances = [];
  globalThis.document = {
    querySelector: selector => elements[selector],
    querySelectorAll: () => chips,
    createElement: () => new FakeElement(),
  };
  globalThis.window = new FakeElement();
  globalThis.window.setTimeout = (callback, delay) => {
    const id = ++nextTimer;
    timers.set(id, callback);
    timerDelays.push(delay);
    return id;
  };
  globalThis.window.clearTimeout = id => timers.delete(id);
  globalThis.EventSource = FakeEventSource;
  globalThis.fetch = async (...args) => {
    requests.push(args);
    if (args[0] === "/api/v1/dialogs") {
      const status = createStatuses?.[createCalls] ?? createStatus;
      createCalls += 1;
      return { status, json: async () => ({ dialog_id: "dialog-1" }) };
    }
    return submitResponse.promise;
  };

  await import(`../src/script.js?case=${++moduleCounter}`);
  await new Promise(resolve => setImmediate(resolve));
  const source = FakeEventSource.instances[0];
  if (autoReady) source?.emit("ready", { dialog_id: "dialog-1" });
  const form = elements["#saiForm"];
  const prompt = elements["#saiPrompt"];
  const messages = elements["#saiMessages"];
  const send = elements[".sai-send"];
  const status = elements["#saiStatusText"];
  const bubbles = () => messages.children.map(row => row.children.at(-1));
  const runNextTimer = async () => {
    const next = timers.entries().next().value;
    if (!next) return false;
    const [id, callback] = next;
    timers.delete(id);
    callback();
    await new Promise(resolve => setImmediate(resolve));
    return true;
  };
  return { source, form, prompt, send, status, bubbles, requests, chips, window: globalThis.window, timers, timerDelays, runNextTimer };
}

test("dialog creation retries and recovers without a page reload", async () => {
  const ui = await setup(deferred(), { createStatuses: [503, 201] });
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.timers.size, 1);
  assert.match(ui.status.textContent, /повторная попытка/);

  await ui.runNextTimer();
  const source = FakeEventSource.instances[0];
  assert.ok(source);
  assert.equal(ui.requests.length, 2);
  assert.equal(ui.timers.size, 0);
  assert.equal(ui.send.disabled, true);
  source.emit("ready");
  assert.equal(ui.send.disabled, false);
  assert.equal(await ui.runNextTimer(), false);
  assert.equal(ui.requests.length, 2);
});

test("page close cancels a pending dialog retry", async () => {
  const ui = await setup(deferred(), { createStatus: 503 });
  assert.equal(ui.timers.size, 1);
  ui.window.dispatch("beforeunload");
  assert.equal(ui.timers.size, 0);
  assert.equal(await ui.runNextTimer(), false);
  assert.equal(ui.requests.length, 1);
});

test("repeated failures keep only one three-second retry pending", async () => {
  const ui = await setup(deferred(), { createStatuses: [503, 503, 201] });
  assert.equal(ui.timers.size, 1);
  await ui.runNextTimer();
  assert.equal(ui.requests.length, 2);
  assert.equal(ui.timers.size, 1);
  await ui.runNextTimer();
  assert.equal(ui.requests.length, 3);
  assert.equal(ui.timers.size, 0);
  assert.deepEqual(ui.timerDelays, [3000, 3000]);
  assert.equal(FakeEventSource.instances.length, 1);
});

test("failed dialog creation leaves the form disabled", async () => {
  const ui = await setup(deferred(), { createStatus: 503 });
  assert.equal(ui.source, undefined);
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.prompt.disabled, true);
  assert.match(ui.status.textContent, /backend недоступен/);
});

test("form waits for ready and reconnects on the same EventSource", async () => {
  const ui = await setup(deferred(), { autoReady: false });
  assert.equal(ui.send.disabled, true);
  ui.source.emit("ready");
  assert.equal(ui.send.disabled, false);
  ui.source.fail();
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.status.textContent, "переподключение…");
  ui.source.emit("ready");
  assert.equal(ui.send.disabled, false);
  assert.equal(FakeEventSource.instances.length, 1);
  ui.window.dispatch("beforeunload");
  assert.equal(ui.source.closed, true);
});

test("preset, autosize, and Enter submission remain available", async () => {
  const ui = await setup(deferred());
  ui.chips[0].dispatch("click");
  assert.match(ui.prompt.value, /Кроша и Ёжика/);
  assert.equal(ui.prompt.style.height, "30px");
  ui.prompt.dispatch("keydown", { key: "Enter", shiftKey: true });
  assert.equal(ui.requests.length, 1);
  ui.prompt.dispatch("keydown", { key: "Enter", shiftKey: false });
  assert.equal(ui.requests.length, 2);
  assert.equal(ui.send.disabled, true);
});

test("invalid SSE JSON is reported without displaying payload as HTML", async () => {
  const ui = await setup(deferred());
  ui.source.emitRaw("message_delta", "<script>invalid</script>");
  assert.equal(ui.status.textContent, "некорректное событие от сервера");
  assert.equal(ui.bubbles().length, 0);
});

test("accepted request keeps the form locked until message_end", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  assert.equal(ui.send.disabled, true);
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.bubbles()[0].textContent, "История");
  await ui.form.dispatch("submit");
  assert.equal(ui.requests.length, 2);

  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Ответ" });
  ui.source.emit("message_end");
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История", "Ответ"]);
  assert.equal(ui.send.disabled, false);
});

test("fast SSE error remains visible after the POST completes", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  ui.source.emit("message_start");
  ui.source.emit("message_error", { message: "Agent request failed." });
  assert.equal(ui.bubbles().length, 0);
  response.resolve({ status: 202 });
  await submission;
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История", "Ошибка ответа"]);
  assert.equal(ui.status.textContent, "Agent request failed.");
  assert.equal(ui.send.disabled, false);
});

test("fast SSE deltas stay behind the user message and use one assistant bubble", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Привет" });
  ui.source.emit("message_delta", { delta: ", Крош!" });
  ui.source.emit("message_end");
  assert.equal(ui.bubbles().length, 0);
  response.resolve({ status: 202 });
  await submission;
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История", "Привет, Крош!"]);
  assert.equal(ui.send.disabled, false);
});

test("disconnect during POST leaves the form locked after acceptance", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  ui.source.fail();
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.status.textContent, "переподключение…");
});

test("failed submission preserves the draft and does not show it in chat", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 503 });
  await submission;
  assert.equal(ui.prompt.value, "История");
  assert.equal(ui.bubbles().length, 0);
  assert.equal(ui.send.disabled, false);
});
