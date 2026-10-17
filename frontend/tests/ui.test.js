import "./no-web-locks.js";
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
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatch(type, event = {}) {
    let result;
    const dispatchedEvent = { preventDefault() {}, ...event };
    for (const listener of this.listeners.get(type) ?? []) {
      result = listener(dispatchedEvent);
    }
    return result;
  }

  append(child) {
    this.children.push(child);
  }

  setAttribute() {}
  focus() { return this.dispatch("focus"); }
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

async function settle() {
  for (let i = 0; i < 5; i += 1) await new Promise(resolve => setImmediate(resolve));
}

const USER = { id: "user-1", login: "krosh", role: "user" };

function authResponse(status) {
  return { status, json: async () => (status === 200 ? USER : { error: "unauthorized" }) };
}

async function setup(submitResponse, {
  autoReady = true,
  createStatus = 201,
  createStatuses,
  meStatuses = [200],
  refreshStatuses = [401],
  logoutResponse = Promise.resolve({ status: 204 }),
} = {}) {
  const ids = ["#saiForm", "#saiPrompt", "#saiMessages", ".sai-send", "#saiStatus", "#saiStatusText", ".sai-hint", "#saiLogout"];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  const chips = [new FakeElement("Про дружбу")];
  const requests = [];
  const timers = new Map();
  const timerDelays = [];
  let nextTimer = 0;
  let createCalls = 0;
  const authRequests = [];
  const redirects = [];
  const nextStatus = (statuses, path) =>
    statuses[authRequests.filter(request => request === path).length - 1] ?? statuses.at(-1);
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
  globalThis.window.location = { replace: url => redirects.push(url) };
  globalThis.EventSource = FakeEventSource;
  globalThis.fetch = async (...args) => {
    if (args[0] === "/api/v1/auth/logout") {
      authRequests.push(args[0]);
      return logoutResponse;
    }
    if (args[0] === "/api/v1/users/me" || args[0] === "/api/v1/auth/refresh") {
      authRequests.push(args[0]);
      return authResponse(nextStatus(
        args[0] === "/api/v1/users/me" ? meStatuses : refreshStatuses,
        args[0],
      ));
    }
    requests.push(args);
    if (args[0] === "/api/v1/dialogs") {
      const status = createStatuses?.[createCalls] ?? createStatus;
      createCalls += 1;
      return { status, json: async () => ({ dialog_id: "dialog-1" }) };
    }
    return submitResponse.promise;
  };

  await import(`../src/script.js?case=${++moduleCounter}`);
  await settle();
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
    await settle();
    return true;
  };
  return {
    source,
    form,
    prompt,
    send,
    status,
    hint: elements[".sai-hint"],
    logout: elements["#saiLogout"],
    bubbles,
    requests,
    authRequests,
    redirects,
    chips,
    window: globalThis.window,
    timers,
    timerDelays,
    runNextTimer,
  };
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

test("automatic focus keeps the Krosh hint visible", async () => {
  const ui = await setup(deferred());
  assert.equal(ui.hint.classList.contains("is-hidden"), false);
});

test("pressing or touching the prompt dismisses the Krosh hint", async () => {
  for (const type of ["pointerdown", "touchstart"]) {
    const ui = await setup(deferred());
    ui.prompt.dispatch(type);
    assert.equal(ui.hint.classList.contains("is-hidden"), true, type);

    ui.prompt.dispatch(type);
    assert.equal(ui.hint.classList.contains("is-hidden"), true, `${type} is idempotent`);
  }
});

test("non-pointer prompt events keep the Krosh hint visible", async () => {
  for (const type of ["focus", "keydown", "input", "paste", "drop"]) {
    const ui = await setup(deferred());
    ui.prompt.dispatch(type, type === "keydown" ? { key: "а", shiftKey: true } : {});
    assert.equal(ui.hint.classList.contains("is-hidden"), false, type);
  }
});

test("choosing a preset dismisses the Krosh hint", async () => {
  const ui = await setup(deferred());
  ui.chips[0].dispatch("click");
  assert.equal(ui.hint.classList.contains("is-hidden"), true);
  assert.match(ui.prompt.value, /Кроша и Ёжика/);
  assert.equal(ui.prompt.style.height, "30px");
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
  assert.equal(ui.hint.classList.contains("is-hidden"), false);
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

test("a guest is redirected to the login page without creating a dialog", async () => {
  const ui = await setup(deferred(), { meStatuses: [401], refreshStatuses: [401] });
  assert.deepEqual(ui.authRequests, ["/api/v1/users/me", "/api/v1/auth/refresh"]);
  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.requests.length, 0);
  assert.equal(FakeEventSource.instances.length, 0);
  assert.equal(ui.send.disabled, true);
});

test("an expired access token is renewed before the dialog is created", async () => {
  const ui = await setup(deferred(), { meStatuses: [401], refreshStatuses: [200] });
  assert.deepEqual(ui.authRequests, ["/api/v1/users/me", "/api/v1/auth/refresh"]);
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.requests[0][0], "/api/v1/dialogs");
  assert.equal(ui.send.disabled, false);
});

test("an unavailable auth backend keeps the page and retries the check", async () => {
  const ui = await setup(deferred(), { meStatuses: [503, 200] });
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.send.disabled, true);
  assert.match(ui.status.textContent, /повторная попытка/);
  assert.deepEqual(ui.timerDelays, [3000]);

  await ui.runNextTimer();
  assert.deepEqual(ui.authRequests, ["/api/v1/users/me", "/api/v1/users/me"]);
  assert.equal(ui.requests[0][0], "/api/v1/dialogs");
});

test("a 401 on dialog creation refreshes once and retries", async () => {
  const ui = await setup(deferred(), { createStatuses: [401, 201], refreshStatuses: [200] });
  assert.deepEqual(ui.authRequests, ["/api/v1/users/me", "/api/v1/auth/refresh"]);
  assert.equal(ui.requests.length, 2);
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.send.disabled, false);
});

test("a 401 on dialog creation after a failed refresh redirects to login", async () => {
  const ui = await setup(deferred(), { createStatus: 401, refreshStatuses: [401] });
  assert.equal(ui.requests.length, 1);
  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.timers.size, 0);
});

test("a repeated 401 after a successful refresh redirects to login", async () => {
  const ui = await setup(deferred(), { createStatus: 401, refreshStatuses: [200] });
  assert.equal(ui.requests.length, 2);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("a 401 on submission refreshes and resends the message once", async () => {
  const responses = [{ status: 401 }, { status: 202 }];
  const ui = await setup({ get promise() { return Promise.resolve(responses.shift()); } }, {
    refreshStatuses: [200],
  });
  ui.prompt.value = "История";
  await ui.form.dispatch("submit");

  const submissions = ui.requests.filter(([path]) => path.endsWith("/messages"));
  assert.equal(submissions.length, 2);
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История"]);
  assert.deepEqual(ui.redirects, []);
});

test("an expired session on submission redirects without showing the message", async () => {
  const ui = await setup({ promise: Promise.resolve({ status: 401 }) }, { refreshStatuses: [401] });
  ui.prompt.value = "История";
  await ui.form.dispatch("submit");

  assert.equal(ui.bubbles().length, 0);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("an SSE error without a session redirects to login", async () => {
  const ui = await setup(deferred(), { meStatuses: [200, 401], refreshStatuses: [401] });
  ui.source.fail();
  await settle();
  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.source.closed, true);
});

test("a closed SSE connection with a valid session is reopened once until ready", async () => {
  const ui = await setup(deferred());
  ui.source.readyState = 2;
  ui.source.fail();
  await settle();
  assert.equal(FakeEventSource.instances.length, 2);
  const reopened = FakeEventSource.instances[1];
  assert.equal(reopened.url, ui.source.url);

  reopened.readyState = 2;
  reopened.fail();
  await settle();
  assert.equal(FakeEventSource.instances.length, 2);
  assert.match(ui.status.textContent, /обновите страницу/);

  reopened.readyState = 1;
  reopened.emit("ready");
  assert.equal(ui.send.disabled, false);
  reopened.readyState = 2;
  reopened.fail();
  await settle();
  assert.equal(FakeEventSource.instances.length, 3);
});

test("an SSE error while the browser reconnects keeps the same connection", async () => {
  const ui = await setup(deferred());
  ui.source.readyState = 0;
  ui.source.fail();
  await settle();
  assert.equal(FakeEventSource.instances.length, 1);
  assert.deepEqual(ui.authRequests, ["/api/v1/users/me", "/api/v1/users/me"]);
  assert.deepEqual(ui.redirects, []);
});

test("logout ends the session, closes the stream and opens the login page", async () => {
  const ui = await setup(deferred());
  await ui.logout.dispatch("click");
  await settle();

  assert.deepEqual(ui.authRequests.slice(1), ["/api/v1/auth/logout"]);
  assert.equal(ui.source.closed, true);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("logout locks the button and ignores repeated clicks", async () => {
  const response = deferred();
  const ui = await setup(deferred(), { logoutResponse: response.promise });
  ui.logout.dispatch("click");
  ui.logout.dispatch("click");
  assert.equal(ui.logout.disabled, true);
  response.resolve({ status: 204 });
  await settle();

  assert.deepEqual(ui.authRequests.slice(1), ["/api/v1/auth/logout"]);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("logout cancels a pending dialog retry", async () => {
  const ui = await setup(deferred(), { createStatus: 503 });
  assert.equal(ui.timers.size, 1);
  await ui.logout.dispatch("click");
  await settle();

  assert.equal(ui.timers.size, 0);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("a failed logout keeps the chat and lets the user try again", async () => {
  for (const respond of [
    () => Promise.resolve({ status: 503 }),
    () => Promise.reject(new TypeError("Failed to fetch")),
  ]) {
    const ui = await setup(deferred(), { logoutResponse: { then: (...args) => respond().then(...args) } });
    await ui.logout.dispatch("click");
    await settle();

    assert.deepEqual(ui.redirects, []);
    assert.equal(ui.logout.disabled, false);
    assert.equal(ui.status.textContent, "Не удалось выйти. Попробуйте ещё раз");
    assert.notEqual(ui.source.closed, true);
  }
});
