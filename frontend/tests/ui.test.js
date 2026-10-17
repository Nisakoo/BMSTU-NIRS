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
    this.attributes = new Map();
    this.hidden = false;
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

  append(...children) {
    for (const child of children) {
      child.parent = this;
      this.children.push(child);
    }
  }

  replaceChildren(...children) {
    for (const child of children) child.parent = this;
    this.children = children;
  }

  remove() {
    if (!this.parent) return;
    this.parent.children = this.parent.children.filter(child => child !== this);
    this.parent = null;
  }

  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name) ?? null; }
  removeAttribute(name) { this.attributes.delete(name); }
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
  listStatuses = [200],
  dialogs = [],
  transcripts = {},
  feedbackStatuses = [204],
} = {}) {
  const ids = [
    "#saiForm", "#saiPrompt", "#saiMessages", ".sai-send", "#saiStatus", "#saiStatusText", "#saiLogout",
    "#saiSidebar", "#saiBackdrop", "#saiHistoryToggle", "#saiNewStory", "#saiHistory",
    "#saiHistoryState", "#saiHistoryRetry", "#saiUserLogin", "#saiTitle", "#saiLength",
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  // <template> with the Krosh block: every clone is a fresh element.
  elements["#saiKroshTemplate"] = {
    content: {
      firstElementChild: {
        cloneNode: () => {
          const block = new FakeElement();
          block.className = "sai-krosh";
          return block;
        },
      },
    },
  };
  // <template> with the five face images, found by their score.
  elements["#saiFacesTemplate"] = {
    content: {
      querySelector: selector => ({
        cloneNode: () => {
          const image = new FakeElement();
          image.className = "sai-face-img";
          image.selector = selector;
          return image;
        },
      }),
    },
  };
  const chips = [new FakeElement("Про дружбу")];
  const requests = [];
  const timers = new Map();
  const timerDelays = [];
  let nextTimer = 0;
  let createCalls = 0;
  const authRequests = [];
  const historyRequests = [];
  const feedbackRequests = [];
  const redirects = [];
  let listCalls = 0;
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
    if (args[0].endsWith("/feedback")) {
      feedbackRequests.push(args);
      const status = feedbackStatuses[feedbackRequests.length - 1] ?? feedbackStatuses.at(-1);
      return { status, json: async () => ({}) };
    }
    // History reads are kept apart so dialog request counts stay comparable.
    if (args[0] === "/api/v1/dialogs" && args.length === 1) {
      historyRequests.push(args[0]);
      const status = listStatuses[listCalls] ?? listStatuses.at(-1);
      listCalls += 1;
      const body = typeof dialogs === "function" ? dialogs() : dialogs;
      return { status, json: async () => ({ dialogs: body }) };
    }
    if (args[0].endsWith("/messages") && args.length === 1) {
      historyRequests.push(args[0]);
      const id = decodeURIComponent(args[0].split("/")[4]);
      return transcripts[id] ?? { status: 404, json: async () => ({ detail: "Dialog not found." }) };
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
  const bubbles = () => messages.children
    .filter(row => row.className !== "sai-krosh" && row.className !== "sai-feedback")
    .map(row => row.children.at(-1));
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
    logout: elements["#saiLogout"],
    messages,
    krosh: () => messages.children.filter(row => row.className === "sai-krosh"),
    sidebar: elements["#saiSidebar"],
    backdrop: elements["#saiBackdrop"],
    toggle: elements["#saiHistoryToggle"],
    newStory: elements["#saiNewStory"],
    history: elements["#saiHistory"],
    historyState: elements["#saiHistoryState"],
    historyRetry: elements["#saiHistoryRetry"],
    userLogin: elements["#saiUserLogin"],
    title: elements["#saiTitle"],
    historyItems: () => elements["#saiHistory"].children.map(entry => entry.children[0]),
    historyRequests,
    feedbackRequests,
    feedbackBars: () => messages.children.filter(row => row.className === "sai-feedback"),
    length: elements["#saiLength"],
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

const SAVED = [
  { dialog_id: "d-2", title: "Ракета", created_at: "2026-10-17T10:00:00Z", updated_at: "2026-10-17T11:00:00Z" },
  { dialog_id: "d-1", title: null, created_at: "2026-10-16T10:00:00Z", updated_at: "2026-10-16T10:00:00Z" },
];

function transcript(title, messages) {
  return { status: 200, json: async () => ({ dialog_id: "x", title, messages }) };
}

test("the sidebar shows the login and saved stories as text", async () => {
  const ui = await setup(deferred(), { dialogs: SAVED });
  assert.equal(ui.userLogin.textContent, "krosh");
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Ракета", "Без названия"]);
  assert.deepEqual(ui.historyItems().map(item => item.getAttribute("aria-current")), [null, null]);
  assert.equal(ui.historyState.textContent, "");
  assert.equal(ui.historyRetry.hidden, true);
  assert.equal(ui.title.textContent, "Новая история");
  assert.equal(ui.messages.children.length, 1);
  assert.equal(ui.krosh().length, 1);
  assert.equal(ui.newStory.disabled, false);
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs"]);
});

test("an empty story list explains where stories will appear", async () => {
  const ui = await setup(deferred());
  assert.equal(ui.historyItems().length, 0);
  assert.equal(ui.historyState.textContent, "Здесь появятся ваши истории");
});

test("opening a saved story shows its messages and streams that dialog", async () => {
  const response = deferred();
  const ui = await setup(response, {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 11, role: "user", content: "Крош строит ракету", created_at: "2026-10-17T10:00:00Z", feedback: null },
        { id: 12, role: "assistant", content: "Однажды…", created_at: "2026-10-17T10:00:01Z", feedback: null },
      ]),
    },
  });

  ui.historyItems()[0].dispatch("click");
  await settle();

  assert.equal(ui.source.closed, true);
  const reopened = FakeEventSource.instances.at(-1);
  assert.equal(reopened.url, "/api/v1/dialogs/d-2/events");
  assert.equal(ui.title.textContent, "Ракета");
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["Крош строит ракету", "Однажды…"]);
  assert.equal(ui.historyItems()[0].getAttribute("aria-current"), "true");
  assert.equal(ui.send.disabled, true);

  reopened.emit("ready");
  assert.equal(ui.send.disabled, false);
  ui.prompt.value = "Что дальше?";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.requests.at(-1)[0], "/api/v1/dialogs/d-2/messages");
});

test("a missing story keeps the current dialog and reloads the list", async () => {
  const ui = await setup(deferred(), { dialogs: SAVED });

  ui.historyItems()[1].dispatch("click");
  await settle();

  assert.equal(ui.status.textContent, "история не найдена");
  assert.notEqual(ui.source.closed, true);
  assert.equal(FakeEventSource.instances.length, 1);
  assert.equal(ui.send.disabled, false);
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs", "/api/v1/dialogs/d-1/messages", "/api/v1/dialogs"]);
});

test("stories cannot be switched while the agent answers", async () => {
  const response = deferred();
  const ui = await setup(response, { dialogs: SAVED, transcripts: { "d-2": transcript("Ракета", []) } });
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  assert.equal(ui.newStory.disabled, true);
  assert.equal(ui.historyItems()[0].disabled, true);
  response.resolve({ status: 202 });
  await submission;

  ui.historyItems()[0].dispatch("click");
  ui.newStory.dispatch("click");
  await settle();
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs"]);
  assert.equal(ui.requests.filter(([path]) => path === "/api/v1/dialogs").length, 1);
  assert.equal(ui.historyItems()[0].disabled, true);

  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Ответ" });
  ui.source.emit("message_end");
  await settle();
  assert.equal(ui.newStory.disabled, false);
  assert.equal(ui.historyItems()[0].disabled, false);
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs", "/api/v1/dialogs"]);
});

test("an answered new story appears in the list with its title and stays current", async () => {
  const response = deferred();
  let saved = [];
  const ui = await setup(response, { dialogs: () => saved });
  ui.prompt.value = "Крош строит ракету";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 202 });
  await submission;

  saved = [{ dialog_id: "dialog-1", title: "Крош строит ракету", created_at: "x", updated_at: "y" }];
  ui.source.emit("message_start");
  ui.source.emit("message_end");
  await settle();

  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Крош строит ракету"]);
  assert.equal(ui.historyItems()[0].getAttribute("aria-current"), "true");
  assert.equal(ui.title.textContent, "Крош строит ракету");
});

test("a new story creates a fresh dialog with a greeting", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: { "d-2": transcript("Ракета", [{ id: 11, role: "user", content: "Крош", created_at: "x", feedback: null }]) },
  });
  ui.historyItems()[0].dispatch("click");
  await settle();
  FakeEventSource.instances.at(-1).emit("ready");

  ui.newStory.dispatch("click");
  await settle();

  assert.equal(ui.requests.filter(([path]) => path === "/api/v1/dialogs").length, 2);
  assert.equal(FakeEventSource.instances.at(-1).url, "/api/v1/dialogs/dialog-1/events");
  assert.equal(ui.title.textContent, "Новая история");
  assert.equal(ui.bubbles().length, 0);
  assert.equal(ui.krosh().length, 1);
  assert.deepEqual(ui.historyItems().map(item => item.getAttribute("aria-current")), [null, null]);
});

test("a failed story list offers a retry while the chat keeps working", async () => {
  const ui = await setup(deferred(), { listStatuses: [503, 200], dialogs: SAVED });
  assert.equal(ui.historyState.textContent, "Не удалось загрузить истории");
  assert.equal(ui.historyRetry.hidden, false);
  assert.equal(ui.send.disabled, false);

  ui.historyRetry.dispatch("click");
  await settle();
  assert.equal(ui.historyRetry.hidden, true);
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Ракета", "Без названия"]);
});

test("a 401 on the story list refreshes the session and retries once", async () => {
  const ui = await setup(deferred(), { listStatuses: [401, 200], refreshStatuses: [200], dialogs: SAVED });
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs", "/api/v1/dialogs"]);
  assert.equal(ui.historyItems().length, 2);
  assert.deepEqual(ui.redirects, []);
});

test("the history panel opens from the header and closes on choice or backdrop", async () => {
  const ui = await setup(deferred(), { dialogs: SAVED, transcripts: { "d-2": transcript("Ракета", []) } });
  ui.toggle.dispatch("click");
  assert.equal(ui.sidebar.classList.contains("is-open"), true);
  assert.equal(ui.backdrop.hidden, false);
  assert.equal(ui.toggle.getAttribute("aria-expanded"), "true");

  ui.backdrop.dispatch("click");
  assert.equal(ui.sidebar.classList.contains("is-open"), false);
  assert.equal(ui.backdrop.hidden, true);
  assert.equal(ui.toggle.getAttribute("aria-expanded"), "false");

  ui.toggle.dispatch("click");
  ui.historyItems()[0].dispatch("click");
  await settle();
  assert.equal(ui.sidebar.classList.contains("is-open"), false);
});

test("a guest never requests the story list", async () => {
  const ui = await setup(deferred(), { meStatuses: [401], refreshStatuses: [401] });
  assert.deepEqual(ui.historyRequests, []);
  assert.equal(ui.newStory.disabled, true);
});

test("Krosh greets a new story and leaves once the first message is accepted", async () => {
  const response = deferred();
  const ui = await setup(response);
  assert.equal(ui.krosh().length, 1);
  assert.equal(ui.bubbles().length, 0);

  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  assert.equal(ui.krosh().length, 1);
  response.resolve({ status: 202 });
  await submission;

  assert.equal(ui.krosh().length, 0);
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История"]);
});

test("Krosh stays with the draft when the first message fails", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 503 });
  await submission;

  assert.equal(ui.krosh().length, 1);
  assert.equal(ui.prompt.value, "История");
});

test("a saved story opens without Krosh, an empty one shows him", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [{ id: 11, role: "user", content: "Крош", created_at: "x", feedback: null }]),
      "d-1": transcript(null, []),
    },
  });

  ui.historyItems()[0].dispatch("click");
  await settle();
  assert.equal(ui.krosh().length, 0);
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["Крош"]);

  FakeEventSource.instances.at(-1).emit("ready");
  ui.historyItems()[1].dispatch("click");
  await settle();
  assert.equal(ui.krosh().length, 1);
  assert.equal(ui.bubbles().length, 0);
});

test("a new story brings Krosh back after a conversation", async () => {
  const response = deferred();
  const ui = await setup(response);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 202 });
  await submission;
  ui.source.emit("message_start");
  ui.source.emit("message_end");
  await settle();
  assert.equal(ui.krosh().length, 0);

  ui.newStory.dispatch("click");
  await settle();
  assert.equal(ui.krosh().length, 1);
  assert.equal(ui.bubbles().length, 0);
});

test("the chosen story length is sent with every next request", async () => {
  const responses = [{ status: 202 }, { status: 202 }, { status: 202 }];
  const ui = await setup({ get promise() { return Promise.resolve(responses.shift()); } });
  const bodies = () => ui.requests
    .filter(([path]) => path.endsWith("/messages"))
    .map(([, init]) => JSON.parse(init.body));

  ui.prompt.value = "Первая";
  await ui.form.dispatch("submit");
  ui.source.emit("message_end");
  await settle();

  ui.length.value = "5";
  ui.prompt.value = "Вторая";
  await ui.form.dispatch("submit");
  ui.source.emit("message_end");
  await settle();

  ui.newStory.dispatch("click");
  await settle();
  FakeEventSource.instances.at(-1).emit("ready");
  ui.prompt.value = "Третья";
  await ui.form.dispatch("submit");

  assert.deepEqual(bodies(), [
    { request: "Первая" },
    { request: "Вторая", reading_minutes: 5 },
    { request: "Третья", reading_minutes: 5 },
  ]);
  assert.equal(ui.length.value, "5");
});

test("the length picker is locked together with the prompt", async () => {
  const response = deferred();
  const ui = await setup(response, { autoReady: false });
  assert.equal(ui.length.disabled, true);
  ui.source.emit("ready");
  assert.equal(ui.length.disabled, false);

  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  assert.equal(ui.length.disabled, true);
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.length.disabled, true);
  ui.source.emit("message_end");
  assert.equal(ui.length.disabled, false);
});

async function answered(options = {}) {
  const response = deferred();
  const ui = await setup(response, options);
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 202 });
  await submission;
  return ui;
}

function buttons(bar) {
  return Object.fromEntries(
    bar.children
      .filter(child => child.className === "sai-face")
      .map(button => [button.dataset.value, button]),
  );
}

function part(bar, className) {
  return bar.children.find(child => child.className === className);
}

const pressed = bar => Object.values(buttons(bar))
  .filter(button => button.getAttribute("aria-pressed") === "true")
  .map(button => button.dataset.value);

async function rated(options) {
  const ui = await answered(options);
  ui.source.emit("message_start");
  ui.source.emit("message_end", { message_id: 42 });
  await settle();
  return ui;
}

test("five faces appear only under a finished answer", async () => {
  const ui = await answered();
  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Ответ" });
  assert.equal(ui.feedbackBars().length, 0);

  ui.source.emit("message_end", { message_id: 42 });
  await settle();

  const [bar] = ui.feedbackBars();
  assert.equal(part(bar, "sai-feedback-q").textContent, "Как тебе история?");
  const faces = buttons(bar);
  assert.deepEqual(Object.keys(faces), ["1", "2", "3", "4", "5"]);
  assert.deepEqual(
    Object.values(faces).map(face => face.getAttribute("aria-label")),
    [
      "Оценка 1 из 5: Совсем не понравилось",
      "Оценка 2 из 5: Скорее не понравилось",
      "Оценка 3 из 5: Так себе",
      "Оценка 4 из 5: Понравилось",
      "Оценка 5 из 5: Очень понравилось!",
    ],
  );
  for (const [score, face] of Object.entries(faces)) {
    const [image, tip] = face.children;
    assert.equal(image.selector, `[data-score="${score}"]`);
    assert.equal(tip.className, "sai-face-tip");
    assert.equal(face.getAttribute("aria-pressed"), "false");
  }
  assert.equal(buttons(bar)["2"].children[1].textContent, "Скорее не понравилось");
  assert.equal(part(bar, "sai-feedback-say").textContent, "");
  assert.equal(ui.messages.children.at(-1), bar);
});

test("an answer that failed or has no id gets no rating buttons", async () => {
  const failed = await answered();
  failed.source.emit("message_start");
  failed.source.emit("message_error", { message: "Agent request failed." });
  assert.equal(failed.feedbackBars().length, 0);

  const anonymous = await answered();
  anonymous.source.emit("message_start");
  anonymous.source.emit("message_end");
  assert.equal(anonymous.feedbackBars().length, 0);
});

test("a face rates, another face changes and the same face clears", async () => {
  const ui = await rated();
  const [bar] = ui.feedbackBars();
  const faces = buttons(bar);
  const say = part(bar, "sai-feedback-say");

  await faces["4"].dispatch("click");
  assert.deepEqual(pressed(bar), ["4"]);
  assert.ok(faces["4"].classList.contains("is-selected"));
  assert.ok(bar.classList.contains("is-rated"));
  assert.equal(say.textContent, "Копатыч доволен");

  await faces["5"].dispatch("click");
  assert.deepEqual(pressed(bar), ["5"]);
  assert.ok(!faces["4"].classList.contains("is-selected"));
  assert.equal(say.textContent, "Крош в восторге!");

  await faces["5"].dispatch("click");
  assert.deepEqual(pressed(bar), []);
  assert.ok(!bar.classList.contains("is-rated"));
  assert.equal(say.textContent, "");

  assert.deepEqual(
    ui.feedbackRequests.map(([path, init]) => [path, init.method, init.body ?? null]),
    [
      ["/api/v1/dialogs/dialog-1/messages/42/feedback", "PUT", JSON.stringify({ score: 4 })],
      ["/api/v1/dialogs/dialog-1/messages/42/feedback", "PUT", JSON.stringify({ score: 5 })],
      ["/api/v1/dialogs/dialog-1/messages/42/feedback", "DELETE", null],
    ],
  );
});

test("a failed rating is rolled back with a message", async () => {
  const ui = await rated({ feedbackStatuses: [204, 503] });
  const [bar] = ui.feedbackBars();
  const faces = buttons(bar);
  await faces["3"].dispatch("click");

  await faces["1"].dispatch("click");

  assert.deepEqual(pressed(bar), ["3"]);
  assert.equal(part(bar, "sai-feedback-say").textContent, "Лосяш задумался");
  assert.equal(ui.status.textContent, "Не удалось сохранить оценку");
  assert.equal(faces["1"].disabled, false);
});

test("a 401 on rating refreshes the session and retries once", async () => {
  const ui = await rated({ feedbackStatuses: [401, 204], refreshStatuses: [200] });
  const [bar] = ui.feedbackBars();

  await buttons(bar)["2"].dispatch("click");

  assert.equal(ui.feedbackRequests.length, 2);
  assert.deepEqual(pressed(bar), ["2"]);
  assert.deepEqual(ui.redirects, []);
});

test("a saved story shows its stored ratings", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 11, role: "user", content: "Крош", created_at: "x", feedback: null },
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: 1 },
        { id: 13, role: "user", content: "Дальше", created_at: "x", feedback: null },
        { id: 14, role: "assistant", content: "Потом…", created_at: "x", feedback: null },
      ]),
    },
  });

  ui.historyItems()[0].dispatch("click");
  await settle();

  const bars = ui.feedbackBars();
  assert.equal(bars.length, 2);
  assert.deepEqual(pressed(bars[0]), ["1"]);
  assert.equal(part(bars[0], "sai-feedback-say").textContent, "Ёжик грустит");
  assert.deepEqual(pressed(bars[1]), []);
  await buttons(bars[0])["1"].dispatch("click");
  assert.deepEqual(ui.feedbackRequests.map(([path, init]) => [path, init.method]), [
    ["/api/v1/dialogs/d-2/messages/12/feedback", "DELETE"],
  ]);
});
