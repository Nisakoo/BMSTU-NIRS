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
  focus() {
    globalThis.document.activeElement = this;
    return this.dispatch("focus");
  }
  contains(node) {
    return node === this || this.children.some(child => child.contains?.(node));
  }
  requestSubmit() { return this.dispatch("submit"); }
  select() { this.selected = true; }
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

function authResponse(status, user = USER) {
  return { status, json: async () => (status === 200 ? user : { error: "unauthorized" }) };
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
  deleteStatuses = [204],
  reportStatuses = [201],
  news = [],
  newsSeenStatuses = [204],
  clipboard = "ok",
  execCommandResult = true,
  user = USER,
  passwordResponses = [{ status: 204 }],
} = {}) {
  const ids = [
    "#saiForm", "#saiPrompt", "#saiMessages", ".sai-send", "#saiStatus", "#saiStatusText", "#saiLogout",
    "#saiSidebar", "#saiBackdrop", "#saiHistoryToggle", "#saiNewStory", "#saiHistory",
    "#saiHistoryState", "#saiHistoryRetry", "#saiUserLogin", "#saiTitle", "#saiLength",
    "#saiLengthButton", "#saiLengthPanel", "#saiLengthValue", "#saiLengthCurrent", "#saiLengthDots",
    "#saiNews", "#saiAdminLink", "#saiSettingsButton", "#saiSettings", "#saiSettingsClose",
    "#saiPasswordForm", "#saiCurrentPassword", "#saiNewPassword", "#saiRepeatPassword",
    "#saiPasswordSave", "#saiPasswordStatus",
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  // The range starts at "Любая" and sits inside the panel, like in the page.
  elements["#saiLength"].value = "0";
  elements["#saiLengthPanel"].hidden = true;
  elements["#saiNews"].hidden = true;
  elements["#saiAdminLink"].hidden = true;
  elements["#saiSettings"].hidden = true;
  elements["#saiAdminLink"].setAttribute("href", "/admin/");
  elements["#saiLengthPanel"].append(elements["#saiLengthDots"]);
  elements["#saiLengthDots"].append(elements["#saiLength"]);
  elements["#saiLengthButton"].append(elements["#saiLengthValue"]);
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
  const deleteRequests = [];
  const reportRequests = [];
  const newsRequests = [];
  const newsSeenRequests = [];
  const passwordRequests = [];
  const redirects = [];
  let listCalls = 0;
  const nextStatus = (statuses, path) =>
    statuses[authRequests.filter(request => request === path).length - 1] ?? statuses.at(-1);
  // Clipboard API, or none outside a secure context, and the textarea fallback.
  const copied = [];
  const execCopies = [];
  const body = new FakeElement();
  const clipboards = {
    ok: { writeText: async text => { copied.push(text); } },
    denied: { writeText: async () => { throw new Error("NotAllowedError"); } },
    none: undefined,
  };
  Object.defineProperty(globalThis, "navigator", {
    value: { clipboard: clipboards[clipboard] },
    configurable: true,
  });
  FakeEventSource.instances = [];
  globalThis.document = new FakeElement();
  Object.assign(globalThis.document, {
    activeElement: null,
    body,
    querySelector: selector => elements[selector],
    querySelectorAll: () => chips,
    createElement: tag => Object.assign(new FakeElement(), { tagName: tag.toUpperCase() }),
    execCommand: command => {
      const area = body.children.find(child => child.tagName === "TEXTAREA");
      execCopies.push({ command, text: area?.value, selected: area?.selected ?? false });
      return execCommandResult;
    },
  });
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
    if (args[0] === "/api/v1/users/me/password") {
      passwordRequests.push(args);
      const next = passwordResponses[passwordRequests.length - 1] ?? passwordResponses.at(-1);
      if (next instanceof Error) throw next;
      if (typeof next?.then === "function") return next;
      return { status: next.status, json: async () => next.body ?? {} };
    }
    if (args[0] === "/api/v1/auth/logout") {
      authRequests.push(args[0]);
      return logoutResponse;
    }
    if (args[0] === "/api/v1/users/me" || args[0] === "/api/v1/auth/refresh") {
      authRequests.push(args[0]);
      return authResponse(nextStatus(
        args[0] === "/api/v1/users/me" ? meStatuses : refreshStatuses,
        args[0],
      ), user);
    }
    if (args[0].endsWith("/feedback")) {
      feedbackRequests.push(args);
      const status = feedbackStatuses[feedbackRequests.length - 1] ?? feedbackStatuses.at(-1);
      return { status, json: async () => ({}) };
    }
    if (args[0] === "/api/v1/reports/news") {
      newsRequests.push(args);
      if (typeof news === "number") return { status: news, json: async () => ({}) };
      return { status: 200, json: async () => ({ news }) };
    }
    if (args[0] === "/api/v1/reports/news/seen") {
      newsSeenRequests.push(args);
      const status = newsSeenStatuses[newsSeenRequests.length - 1] ?? newsSeenStatuses.at(-1);
      return { status, json: async () => ({}) };
    }
    if (args[0].endsWith("/report")) {
      reportRequests.push(args);
      const status = reportStatuses[reportRequests.length - 1] ?? reportStatuses.at(-1);
      return { status, json: async () => ({}) };
    }
    if (args[1]?.method === "DELETE") {
      deleteRequests.push(args);
      const status = deleteStatuses[deleteRequests.length - 1] ?? deleteStatuses.at(-1);
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
    .map(row => row.children.find(child => child.className === "sai-bubble"));
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
    deleteRequests,
    reportRequests,
    newsRequests,
    newsSeenRequests,
    passwordRequests,
    settingsButton: elements["#saiSettingsButton"],
    settings: elements["#saiSettings"],
    settingsClose: elements["#saiSettingsClose"],
    passwordForm: elements["#saiPasswordForm"],
    currentPassword: elements["#saiCurrentPassword"],
    newPassword: elements["#saiNewPassword"],
    repeatPassword: elements["#saiRepeatPassword"],
    passwordSave: elements["#saiPasswordSave"],
    passwordStatus: elements["#saiPasswordStatus"],
    newsBox: elements["#saiNews"],
    adminLink: elements["#saiAdminLink"],
    historyRows: () => elements["#saiHistory"].children,
    feedbackBars: () => messages.children.filter(row => row.className === "sai-feedback"),
    length: elements["#saiLength"],
    lengthButton: elements["#saiLengthButton"],
    lengthPanel: elements["#saiLengthPanel"],
    lengthValue: elements["#saiLengthValue"],
    lengthCurrent: elements["#saiLengthCurrent"],
    lengthDots: elements["#saiLengthDots"],
    document: globalThis.document,
    bubbles,
    requests,
    authRequests,
    redirects,
    chips,
    window: globalThis.window,
    timers,
    timerDelays,
    runNextTimer,
    copied,
    execCopies,
    body,
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
  assert.equal(ui.userLogin.title, "krosh");
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Ракета", "Без названия"]);
  assert.deepEqual(ui.historyItems().map(item => item.getAttribute("aria-current")), [null, null]);
  assert.equal(ui.historyState.textContent, "");
  assert.equal(ui.historyRetry.hidden, true);
  assert.equal(ui.title.textContent, "Новая история");
  assert.equal(ui.title.title, "Новая история");
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
  assert.equal(ui.title.title, "Ракета");
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
  assert.equal(ui.title.title, "Крош строит ракету");
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

  ui.length.value = "2";
  ui.length.dispatch("input");
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
  assert.equal(ui.length.value, "2");
});

test("the length button is locked together with the prompt", async () => {
  const response = deferred();
  const ui = await setup(response, { autoReady: false });
  assert.equal(ui.lengthButton.disabled, true);
  assert.equal(ui.length.disabled, true);
  ui.source.emit("ready");
  assert.equal(ui.lengthButton.disabled, false);

  ui.lengthButton.dispatch("click");
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  assert.equal(ui.lengthButton.disabled, true);
  assert.equal(ui.lengthPanel.hidden, true);
  assert.equal(ui.lengthButton.getAttribute("aria-expanded"), "false");
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.lengthButton.disabled, true);
  ui.source.emit("message_end");
  assert.equal(ui.lengthButton.disabled, false);
});

test("the length button opens and closes the panel and focuses the slider", async () => {
  const ui = await setup(deferred());
  assert.equal(ui.lengthPanel.hidden, true);
  assert.equal(ui.lengthButton.getAttribute("aria-expanded"), "false");
  assert.equal(ui.lengthValue.textContent, "Любая");
  assert.equal(ui.lengthButton.getAttribute("aria-label"), "Длина истории: Любая");

  ui.lengthButton.dispatch("click");
  assert.equal(ui.lengthPanel.hidden, false);
  assert.equal(ui.lengthButton.getAttribute("aria-expanded"), "true");
  assert.equal(ui.document.activeElement, ui.length);

  ui.lengthButton.dispatch("click");
  assert.equal(ui.lengthPanel.hidden, true);
  assert.equal(ui.lengthButton.getAttribute("aria-expanded"), "false");
});

test("moving the slider updates the labels and the lit dots", async () => {
  const ui = await setup(deferred());
  ui.lengthButton.dispatch("click");
  const steps = [["0", "Любая"], ["1", "2 мин"], ["2", "5 мин"], ["3", "10 мин"]];

  for (const [value, label] of steps) {
    ui.length.value = value;
    ui.length.dispatch("input");
    assert.equal(ui.lengthValue.textContent, label);
    assert.equal(ui.lengthCurrent.textContent, `(${label.toLowerCase()})`);
    assert.equal(ui.length.getAttribute("aria-valuetext"), label);
    assert.equal(ui.lengthButton.getAttribute("aria-label"), `Длина истории: ${label}`);
    assert.equal(ui.lengthDots.dataset.step, value);
  }
});

test("escape and a click outside close the length panel", async () => {
  const ui = await setup(deferred());
  ui.lengthButton.dispatch("click");
  ui.document.dispatch("keydown", { key: "Escape" });
  assert.equal(ui.lengthPanel.hidden, true);
  assert.equal(ui.document.activeElement, ui.lengthButton);

  ui.lengthButton.dispatch("click");
  ui.document.dispatch("click", { target: ui.length });
  assert.equal(ui.lengthPanel.hidden, false, "a click inside keeps the panel");
  ui.document.dispatch("click", { target: ui.lengthButton });
  assert.equal(ui.lengthPanel.hidden, false, "the button handles its own click");
  ui.document.dispatch("click", { target: ui.prompt });
  assert.equal(ui.lengthPanel.hidden, true);
  assert.equal(ui.lengthButton.getAttribute("aria-expanded"), "false");

  ui.document.dispatch("keydown", { key: "Escape" });
  assert.equal(ui.document.activeElement, ui.length, "escape on a closed panel changes nothing");
});

test("every slider step sends its minutes and any length sends none", async () => {
  const responses = Array.from({ length: 4 }, () => ({ status: 202 }));
  const ui = await setup({ get promise() { return Promise.resolve(responses.shift()); } });
  const bodies = () => ui.requests
    .filter(([path]) => path.endsWith("/messages"))
    .map(([, init]) => JSON.parse(init.body));

  for (const value of ["1", "2", "3", "0"]) {
    ui.length.value = value;
    ui.length.dispatch("input");
    ui.prompt.value = `Шаг ${value}`;
    await ui.form.dispatch("submit");
    ui.source.emit("message_end");
    await settle();
  }

  assert.deepEqual(bodies(), [
    { request: "Шаг 1", reading_minutes: 2 },
    { request: "Шаг 2", reading_minutes: 5 },
    { request: "Шаг 3", reading_minutes: 10 },
    { request: "Шаг 0" },
  ]);
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
  if (bar.className === className) return bar;
  for (const child of bar.children) {
    const found = part(child, className);
    if (found) return found;
  }
  return undefined;
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


const TRASH = 1;

function confirmParts(row) {
  const [text, remove, cancel] = row.children;
  return { text, remove, cancel };
}

async function savedStories(options = {}) {
  const ui = await setup(deferred(), { dialogs: SAVED, ...options });
  await settle();
  return ui;
}

test("every saved story has a labelled delete button", async () => {
  const ui = await savedStories();
  const trashes = ui.historyRows().map(row => row.children[TRASH]);

  assert.deepEqual(trashes.map(button => button.getAttribute("aria-label")), [
    "Удалить историю «Ракета»",
    "Удалить историю «Без названия»",
  ]);
  assert.ok(trashes.every(button => button.className === "sai-history-delete"));
});

test("the delete confirmation is cancelled by its button or escape", async () => {
  const ui = await savedStories();

  ui.historyRows()[0].children[TRASH].dispatch("click");
  let parts = confirmParts(ui.historyRows()[0]);
  assert.equal(parts.text.textContent, "Удалить историю?");
  assert.equal(parts.remove.textContent, "Удалить");
  assert.equal(parts.cancel.textContent, "Отмена");
  assert.equal(ui.document.activeElement, parts.cancel);

  parts.cancel.dispatch("click");
  assert.equal(ui.historyItems()[0].textContent, "Ракета");
  assert.equal(ui.document.activeElement, ui.historyRows()[0].children[TRASH]);

  ui.historyRows()[1].children[TRASH].dispatch("click");
  ui.historyRows()[0].children[TRASH].dispatch("click");
  assert.equal(ui.historyItems()[1].textContent, "Без названия", "only one confirmation at a time");
  ui.document.dispatch("keydown", { key: "Escape" });
  assert.equal(ui.historyItems()[0].textContent, "Ракета");
  assert.equal(ui.document.activeElement, ui.historyRows()[0].children[TRASH]);
  assert.deepEqual(ui.deleteRequests, []);
});

test("deleting another story keeps the open one", async () => {
  const ui = await savedStories();
  const created = ui.requests.length;

  ui.historyRows()[0].children[TRASH].dispatch("click");
  await confirmParts(ui.historyRows()[0]).remove.dispatch("click");
  await settle();

  assert.deepEqual(ui.deleteRequests.map(([path, init]) => [path, init.method]), [
    ["/api/v1/dialogs/d-2", "DELETE"],
  ]);
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
  assert.equal(ui.requests.length, created, "no new dialog is created");
  assert.equal(ui.title.textContent, "Новая история");
});

test("deleting the open story starts a new one", async () => {
  const ui = await savedStories({
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 11, role: "user", content: "Крош", created_at: "x", feedback: null },
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: null },
      ]),
    },
  });
  ui.historyItems()[0].dispatch("click");
  await settle();
  FakeEventSource.instances.at(-1).emit("ready");
  assert.equal(ui.title.textContent, "Ракета");
  const created = ui.requests.length;

  ui.historyRows()[0].children[TRASH].dispatch("click");
  await confirmParts(ui.historyRows()[0]).remove.dispatch("click");
  await settle();

  assert.equal(ui.requests.length, created + 1);
  assert.equal(ui.requests.at(-1)[0], "/api/v1/dialogs");
  assert.equal(ui.title.textContent, "Новая история");
  assert.equal(ui.krosh().length, 1);
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
});

test("a failed delete keeps the story and says so", async () => {
  const ui = await savedStories({ deleteStatuses: [503] });

  ui.historyRows()[0].children[TRASH].dispatch("click");
  await confirmParts(ui.historyRows()[0]).remove.dispatch("click");
  await settle();

  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Ракета", "Без названия"]);
  assert.equal(ui.status.textContent, "Не удалось удалить историю");
});

test("a story already deleted elsewhere is simply removed", async () => {
  const ui = await savedStories({ deleteStatuses: [404] });

  ui.historyRows()[0].children[TRASH].dispatch("click");
  await confirmParts(ui.historyRows()[0]).remove.dispatch("click");
  await settle();

  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
  assert.notEqual(ui.status.textContent, "Не удалось удалить историю");
});

test("a 401 on delete refreshes the session and retries once", async () => {
  const ui = await savedStories({ deleteStatuses: [401, 204], refreshStatuses: [200] });

  ui.historyRows()[0].children[TRASH].dispatch("click");
  await confirmParts(ui.historyRows()[0]).remove.dispatch("click");
  await settle();

  assert.equal(ui.deleteRequests.length, 2);
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
  assert.deepEqual(ui.redirects, []);
});

test("delete buttons are locked while the agent answers", async () => {
  const response = deferred();
  const ui = await setup(response, { dialogs: SAVED });
  await settle();
  ui.prompt.value = "История";
  const submission = ui.form.dispatch("submit");
  response.resolve({ status: 202 });
  await submission;

  assert.ok(ui.historyRows().every(row => row.children[TRASH].disabled));
  ui.source.emit("message_end", { message_id: 1 });
  await settle();
  assert.ok(ui.historyRows().every(row => !row.children[TRASH].disabled));
});


function copyButton(bubble) {
  return bubble.parent.children.find(child => child.className === "sai-copy");
}

test("a copy button sits by the user's message and a finished answer only", async () => {
  const ui = await answered();
  const [request] = ui.bubbles();
  assert.equal(copyButton(request).getAttribute("aria-label"), "Скопировать сообщение");
  assert.equal(copyButton(request).textContent, "Копировать");

  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Однажды" });
  assert.equal(copyButton(ui.bubbles()[1]), undefined);
  ui.source.emit("message_end", { message_id: 42 });
  await settle();
  assert.ok(copyButton(ui.bubbles()[1]));

  ui.prompt.value = "Ещё";
  ui.form.dispatch("submit");
  await settle();
  ui.source.emit("message_start");
  ui.source.emit("message_error", { message: "Agent request failed." });
  assert.equal(copyButton(ui.bubbles().at(-1)), undefined);
});

test("copy puts the exact text to the clipboard and says so for a moment", async () => {
  const ui = await rated();
  const [, answer] = ui.bubbles();
  answer.textContent = "Однажды Крош\nнашёл карту";
  const button = copyButton(answer);

  await button.dispatch("click");

  assert.deepEqual(ui.copied, ["Однажды Крош\nнашёл карту"]);
  assert.deepEqual(ui.execCopies, []);
  assert.equal(button.textContent, "Скопировано");
  assert.ok(button.classList.contains("is-done"));
  assert.equal(ui.timerDelays.at(-1), 1500);
  await ui.runNextTimer();
  assert.equal(button.textContent, "Копировать");
  assert.ok(!button.classList.contains("is-done"));
});

for (const clipboard of ["none", "denied"]) {
  test(`copy falls back to a hidden textarea when the Clipboard API is ${clipboard}`, async () => {
    const ui = await answered({ clipboard });
    const button = copyButton(ui.bubbles()[0]);

    await button.dispatch("click");

    assert.deepEqual(ui.execCopies, [{ command: "copy", text: "История", selected: true }]);
    assert.equal(ui.body.children.length, 0);
    assert.equal(button.textContent, "Скопировано");
  });
}

test("a failed copy is reported in the status line", async () => {
  const ui = await answered({ clipboard: "none", execCommandResult: false });
  const button = copyButton(ui.bubbles()[0]);

  await button.dispatch("click");

  assert.equal(ui.status.textContent, "Не удалось скопировать");
  assert.equal(button.textContent, "Копировать");
  assert.equal(ui.body.children.length, 0);
});

test("copy works while the agent answers and sends no requests", async () => {
  const ui = await answered();
  ui.source.emit("message_start");
  assert.equal(ui.send.disabled, true);
  const sent = ui.requests.length;

  await copyButton(ui.bubbles()[0]).dispatch("click");

  assert.deepEqual(ui.copied, ["История"]);
  assert.equal(ui.requests.length, sent);
  assert.equal(ui.feedbackRequests.length, 0);
});

test("every message of a saved story can be copied", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 11, role: "user", content: "Крош", created_at: "x", feedback: null },
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: null },
      ]),
    },
  });
  ui.historyItems()[0].dispatch("click");
  await settle();

  for (const bubble of ui.bubbles()) await copyButton(bubble).dispatch("click");

  assert.deepEqual(ui.copied, ["Крош", "Однажды…"]);
});


function find(root, className) {
  if (root.className === className) return root;
  for (const child of root.children ?? []) {
    const found = find(child, className);
    if (found) return found;
  }
  return undefined;
}

function findAll(root, className) {
  const own = root.className === className ? [root] : [];
  return own.concat(...(root.children ?? []).map(child => findAll(child, className)));
}

function report(bar) {
  const panel = find(bar, "sai-report-panel");
  return {
    flag: find(bar, "sai-report"),
    panel,
    reasons: panel ? findAll(panel, "sai-report-reason") : [],
    comment: panel && find(panel, "sai-report-comment"),
    send: panel && find(panel, "sai-report-send"),
    cancel: panel && find(panel, "sai-report-cancel"),
  };
}

async function reportOpen(options) {
  const ui = await rated(options);
  const [bar] = ui.feedbackBars();
  await report(bar).flag.dispatch("click");
  return { ui, bar };
}

test("a report flag sits under a finished answer", async () => {
  const ui = await rated();
  const { flag, panel } = report(ui.feedbackBars()[0]);

  assert.equal(flag.textContent, "Пожаловаться");
  assert.equal(flag.getAttribute("aria-label"), "Пожаловаться на историю");
  assert.equal(flag.getAttribute("aria-expanded"), "false");
  assert.equal(flag.disabled, false);
  assert.equal(panel, undefined);
});

test("the report panel offers reasons and waits for one", async () => {
  const { bar } = await reportOpen();
  const { flag, panel, reasons, comment, send, cancel } = report(bar);

  assert.equal(flag.getAttribute("aria-expanded"), "true");
  assert.equal(panel.getAttribute("role"), "dialog");
  assert.equal(find(panel, "sai-report-title").textContent, "Что не так с историей?");
  assert.deepEqual(reasons.map(reason => [reason.dataset.reason, reason.textContent]), [
    ["scary", "Страшно"],
    ["rude", "Грубо или обидно"],
    ["wrong", "Неправильно или непонятно"],
    ["other", "Другое"],
  ]);
  assert.equal(comment.maxLength, 500);
  assert.equal(send.textContent, "Отправить");
  assert.equal(cancel.textContent, "Отмена");
  assert.equal(send.disabled, true);

  reasons[1].dispatch("click");
  assert.deepEqual(reasons.map(reason => reason.getAttribute("aria-pressed")), ["false", "true", "false", "false"]);
  assert.equal(send.disabled, false);
  reasons[3].dispatch("click");
  assert.deepEqual(reasons.map(reason => reason.getAttribute("aria-pressed")), ["false", "false", "false", "true"]);
});

test("the report panel closes by its cancel button or escape", async () => {
  const { ui, bar } = await reportOpen();
  report(bar).cancel.dispatch("click");
  assert.equal(report(bar).panel, undefined);
  assert.equal(report(bar).flag.getAttribute("aria-expanded"), "false");
  assert.equal(ui.document.activeElement, report(bar).flag);

  await report(bar).flag.dispatch("click");
  ui.document.dispatch("keydown", { key: "Escape" });
  assert.equal(report(bar).panel, undefined);
  assert.equal(ui.reportRequests.length, 0);
});

for (const status of [201, 409]) {
  test(`a sent report (${status}) marks the answer as reported`, async () => {
    const { ui, bar } = await reportOpen({ reportStatuses: [status] });
    const { reasons, comment, send } = report(bar);
    reasons[0].dispatch("click");
    comment.value = "  Испугался  ";

    await send.dispatch("click");

    assert.deepEqual(ui.reportRequests.map(([path, init]) => [path, init.method, init.body]), [
      ["/api/v1/dialogs/dialog-1/messages/42/report", "POST", JSON.stringify({ reason: "scary", comment: "Испугался" })],
    ]);
    const { flag, panel } = report(bar);
    assert.equal(panel, undefined);
    assert.equal(flag.textContent, "Жалоба отправлена");
    assert.equal(flag.disabled, true);
    assert.ok(flag.classList.contains("is-sent"));
    assert.equal(ui.status.textContent, "Спасибо! Взрослые посмотрят");
  });
}

test("a failed report keeps the panel with the choice", async () => {
  const { ui, bar } = await reportOpen({ reportStatuses: [503] });
  const { reasons, comment, send } = report(bar);
  reasons[2].dispatch("click");
  comment.value = "Неправда";

  await send.dispatch("click");

  const after = report(bar);
  assert.equal(after.panel, report(bar).panel);
  assert.ok(after.panel);
  assert.equal(after.reasons[2].getAttribute("aria-pressed"), "true");
  assert.equal(after.comment.value, "Неправда");
  assert.equal(after.send.disabled, false);
  assert.equal(after.flag.disabled, false);
  assert.equal(ui.status.textContent, "Не удалось отправить жалобу");
});

test("a 401 on report refreshes the session and retries once", async () => {
  const { ui, bar } = await reportOpen({ reportStatuses: [401, 201], refreshStatuses: [200] });
  report(bar).reasons[1].dispatch("click");

  await report(bar).send.dispatch("click");

  assert.equal(ui.reportRequests.length, 2);
  assert.equal(report(bar).flag.textContent, "Жалоба отправлена");
  assert.deepEqual(ui.redirects, []);
});

test("only one report panel is open at a time", async () => {
  const ui = await rated();
  ui.prompt.value = "Ещё";
  ui.form.dispatch("submit");
  await settle();
  ui.source.emit("message_start");
  ui.source.emit("message_end", { message_id: 44 });
  await settle();
  const [first, second] = ui.feedbackBars();

  await report(first).flag.dispatch("click");
  await report(second).flag.dispatch("click");

  assert.equal(report(first).panel, undefined);
  assert.ok(report(second).panel);
});

test("a saved story shows which answers were reported", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 11, role: "user", content: "Крош", created_at: "x", feedback: null, reported: false },
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: null, reported: true },
        { id: 13, role: "user", content: "Дальше", created_at: "x", feedback: null, reported: false },
        { id: 14, role: "assistant", content: "Потом…", created_at: "x", feedback: null, reported: false },
      ]),
    },
  });
  ui.historyItems()[0].dispatch("click");
  await settle();

  const [reported, fresh] = ui.feedbackBars().map(bar => report(bar).flag);
  assert.equal(reported.textContent, "Жалоба отправлена");
  assert.equal(reported.disabled, true);
  assert.equal(fresh.textContent, "Пожаловаться");
  await fresh.dispatch("click");
  report(ui.feedbackBars()[1]).reasons[0].dispatch("click");
  await report(ui.feedbackBars()[1]).send.dispatch("click");
  assert.equal(ui.reportRequests[0][0], "/api/v1/dialogs/d-2/messages/14/report");
});


function newsParts(box) {
  const say = find(box, "sai-news-say");
  const actions = find(box, "sai-news-actions");
  return {
    face: find(box, "sai-news-face"),
    say: say?.textContent,
    buttons: actions ? actions.children : [],
  };
}

const seenIds = ui => ui.newsSeenRequests.map(([, init]) => JSON.parse(init.body).report_ids);

test("no news means no Krosh banner", async () => {
  const ui = await setup(deferred());

  assert.equal(ui.newsRequests.length, 1);
  assert.equal(ui.newsBox.hidden, true);
  assert.equal(ui.newsSeenRequests.length, 0);
});

test("one reviewed report greets the user with its story title", async () => {
  const ui = await setup(deferred(), {
    news: [{ report_id: 3, dialog_id: "d-2", dialog_title: "<b>Ракета</b>" }],
  });
  const { face, say, buttons } = newsParts(ui.newsBox);

  assert.equal(ui.newsBox.hidden, false);
  assert.equal(ui.newsBox.getAttribute("role"), "status");
  assert.ok(face);
  assert.equal(say, "Взрослые посмотрели твою жалобу на историю «<b>Ракета</b>». Спасибо, что рассказал!");
  assert.deepEqual(buttons.map(button => button.textContent), ["Хорошо", "Открыть историю"]);
  assert.equal(ui.prompt.disabled, false);

  buttons[0].dispatch("click");
  await settle();

  assert.equal(ui.newsBox.hidden, true);
  assert.deepEqual(seenIds(ui), [[3]]);
});

test("several reports are counted and a deleted story is not named", async () => {
  const several = await setup(deferred(), {
    news: [
      { report_id: 3, dialog_id: "d-2", dialog_title: "Ракета" },
      { report_id: 2, dialog_id: null, dialog_title: null },
    ],
  });
  assert.equal(newsParts(several.newsBox).say, "Взрослые посмотрели твои жалобы (2). Спасибо, что рассказал!");
  assert.deepEqual(newsParts(several.newsBox).buttons.map(button => button.textContent), ["Хорошо"]);
  newsParts(several.newsBox).buttons[0].dispatch("click");
  await settle();
  assert.deepEqual(seenIds(several), [[3, 2]]);

  const deleted = await setup(deferred(), {
    news: [{ report_id: 2, dialog_id: null, dialog_title: null }],
  });
  assert.equal(newsParts(deleted.newsBox).say, "Взрослые посмотрели твою жалобу на одну историю. Спасибо, что рассказал!");
  assert.deepEqual(newsParts(deleted.newsBox).buttons.map(button => button.textContent), ["Хорошо"]);
});

test("the banner opens the reviewed story", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    news: [{ report_id: 3, dialog_id: "d-2", dialog_title: "Ракета" }],
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 11, role: "user", content: "Крош", created_at: "x", feedback: null, reported: false, report: null },
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: null, reported: true, report: "reviewed" },
      ]),
    },
  });

  newsParts(ui.newsBox).buttons[1].dispatch("click");
  await settle();

  assert.equal(ui.newsBox.hidden, true);
  assert.deepEqual(seenIds(ui), [[3]]);
  assert.equal(ui.title.textContent, "Ракета");
  const { flag } = report(ui.feedbackBars()[0]);
  assert.equal(flag.textContent, "Взрослые посмотрели — спасибо!");
  assert.equal(flag.getAttribute("aria-label"), "Взрослые посмотрели — спасибо!");
  assert.equal(flag.disabled, true);
  assert.ok(flag.classList.contains("is-reviewed"));
});

test("news failures stay silent and the banner comes once per page", async () => {
  const failed = await setup(deferred(), { news: 503 });
  assert.equal(failed.newsBox.hidden, true);
  assert.notEqual(failed.status.textContent, "Не удалось загрузить новости");
  assert.equal(failed.document.querySelector("#saiStatus").dataset.state, "ready");

  const unsaved = await setup(deferred(), {
    news: [{ report_id: 3, dialog_id: "d-2", dialog_title: "Ракета" }],
    newsSeenStatuses: [503],
  });
  newsParts(unsaved.newsBox).buttons[0].dispatch("click");
  await settle();
  assert.equal(unsaved.newsBox.hidden, true);
  assert.equal(unsaved.document.querySelector("#saiStatus").dataset.state, "ready");

  unsaved.newStory.dispatch("click");
  await settle();
  assert.equal(unsaved.newsRequests.length, 1);
  assert.equal(unsaved.newsBox.hidden, true);
});

test("a guest never asks for news", async () => {
  const ui = await setup(deferred(), { meStatuses: [401], refreshStatuses: [401] });

  assert.equal(ui.newsRequests.length, 0);
});

test("the reason other needs a comment, other reasons do not", async () => {
  const { ui, bar } = await reportOpen();
  const { reasons, comment, send } = report(bar);

  reasons[3].dispatch("click");
  assert.equal(send.disabled, true);
  assert.equal(comment.getAttribute("aria-required"), "true");
  assert.equal(comment.placeholder, "Расскажи, что не так (обязательно)");
  comment.value = "   ";
  comment.dispatch("input");
  assert.equal(send.disabled, true);
  comment.value = "Скучно";
  comment.dispatch("input");
  assert.equal(send.disabled, false);

  comment.value = "";
  comment.dispatch("input");
  reasons[0].dispatch("click");
  assert.equal(send.disabled, false);
  assert.equal(comment.getAttribute("aria-required"), "false");
  assert.equal(comment.placeholder, "Расскажи, что не так (необязательно)");

  reasons[3].dispatch("click");
  comment.value = "Скучно";
  comment.dispatch("input");
  await send.dispatch("click");
  assert.deepEqual(JSON.parse(ui.reportRequests[0][1].body), { reason: "other", comment: "Скучно" });
});


test("an administrator gets a link back to the admin panel", async () => {
  const ui = await setup(deferred(), { user: { id: "admin-1", login: "sovunya", role: "admin" } });

  assert.equal(ui.adminLink.hidden, false);
  assert.equal(ui.adminLink.getAttribute("href"), "/admin/");
});

test("a regular user and a guest never see the admin link", async () => {
  const user = await setup(deferred());
  assert.equal(user.adminLink.hidden, true);

  const guest = await setup(deferred(), { meStatuses: [401], refreshStatuses: [401] });
  assert.equal(guest.adminLink.hidden, true);
});

function fillPassword(ui, current = "carrot123", next = "radish456", repeat = next) {
  ui.currentPassword.value = current;
  ui.newPassword.value = next;
  ui.repeatPassword.value = repeat;
}

test("the gear opens settings and the window closes by button, escape or backdrop", async () => {
  const ui = await setup(deferred());
  assert.equal(ui.settings.hidden, true);

  for (const close of [
    () => ui.settingsClose.dispatch("click"),
    () => ui.document.dispatch("keydown", { key: "Escape" }),
    () => ui.settings.dispatch("click", { target: ui.settings }),
  ]) {
    ui.settingsButton.dispatch("click");
    assert.equal(ui.settings.hidden, false);
    assert.equal(ui.settingsButton.getAttribute("aria-expanded"), "true");
    assert.equal(ui.document.activeElement, ui.currentPassword);
    fillPassword(ui);
    close();
    assert.equal(ui.settings.hidden, true);
    assert.equal(ui.settingsButton.getAttribute("aria-expanded"), "false");
    assert.equal(ui.document.activeElement, ui.settingsButton);
    assert.deepEqual(
      [ui.currentPassword.value, ui.newPassword.value, ui.repeatPassword.value],
      ["", "", ""],
    );
  }
  assert.deepEqual(ui.passwordRequests, []);
});

test("a click inside the settings card keeps the window open", async () => {
  const ui = await setup(deferred());
  ui.settingsButton.dispatch("click");

  ui.settings.dispatch("click", { target: ui.currentPassword });

  assert.equal(ui.settings.hidden, false);
});

test("the password form checks its fields before sending anything", async () => {
  const ui = await setup(deferred());
  ui.settingsButton.dispatch("click");
  const cases = [
    [["", "radish456", "radish456"], "Пароль должен быть от 8 до 128 символов"],
    [["carrot123", "short", "short"], "Пароль должен быть от 8 до 128 символов"],
    [["carrot123", "x".repeat(129), "x".repeat(129)], "Пароль должен быть от 8 до 128 символов"],
    [["carrot123", "radish456", "radish457"], "Пароли не совпадают"],
    [["carrot123", "carrot123", "carrot123"], "Новый пароль совпадает с текущим"],
  ];

  for (const [[current, next, repeat], message] of cases) {
    fillPassword(ui, current, next, repeat);
    await ui.passwordForm.dispatch("submit");
    assert.equal(ui.passwordStatus.textContent, message);
    assert.equal(ui.passwordStatus.dataset.state, "error");
  }
  assert.deepEqual(ui.passwordRequests, []);
});

test("a changed password clears the fields and says other devices sign in again", async () => {
  const ui = await setup(deferred());
  ui.settingsButton.dispatch("click");
  fillPassword(ui);

  await ui.passwordForm.dispatch("submit");
  await settle();

  assert.equal(ui.passwordRequests.length, 1);
  const [path, options] = ui.passwordRequests[0];
  assert.equal(path, "/api/v1/users/me/password");
  assert.equal(options.method, "PUT");
  assert.deepEqual(JSON.parse(options.body), {
    current_password: "carrot123",
    new_password: "radish456",
  });
  assert.equal(
    ui.passwordStatus.textContent,
    "Пароль изменён. На других устройствах нужно войти заново",
  );
  assert.equal(ui.passwordStatus.dataset.state, "ok");
  assert.deepEqual(
    [ui.currentPassword.value, ui.newPassword.value, ui.repeatPassword.value],
    ["", "", ""],
  );
  assert.equal(ui.settings.hidden, false);
  assert.deepEqual(ui.redirects, []);
});

test("a wrong current password is cleared and focused", async () => {
  const ui = await setup(deferred(), {
    passwordResponses: [{ status: 400, body: { error: "wrong_password" } }],
  });
  ui.settingsButton.dispatch("click");
  fillPassword(ui);

  await ui.passwordForm.dispatch("submit");
  await settle();

  assert.equal(ui.passwordStatus.textContent, "Неверный текущий пароль");
  assert.equal(ui.currentPassword.value, "");
  assert.equal(ui.newPassword.value, "radish456");
  assert.equal(ui.document.activeElement, ui.currentPassword);
});

test("every other password answer gets its own message", async () => {
  const cases = [
    [{ status: 422, body: { error: "same_password" } }, "Новый пароль совпадает с текущим"],
    [{ status: 422, body: { error: "invalid_fields" } }, "Пароль должен быть от 8 до 128 символов"],
    [{ status: 503, body: { error: "unavailable" } }, "Не удалось сменить пароль. Попробуйте ещё раз"],
    [{ status: 500 }, "Не удалось сменить пароль. Попробуйте ещё раз"],
    [new TypeError("Failed to fetch"), "Не удалось сменить пароль. Попробуйте ещё раз"],
  ];

  for (const [answer, message] of cases) {
    const ui = await setup(deferred(), { passwordResponses: [answer] });
    ui.settingsButton.dispatch("click");
    fillPassword(ui);
    await ui.passwordForm.dispatch("submit");
    await settle();
    assert.equal(ui.passwordStatus.textContent, message);
    assert.equal(ui.passwordStatus.dataset.state, "error");
  }
});

test("the settings window is locked while the password is saved", async () => {
  const answer = deferred();
  const ui = await setup(deferred(), { passwordResponses: [answer.promise] });
  ui.settingsButton.dispatch("click");
  fillPassword(ui);

  const pending = ui.passwordForm.dispatch("submit");
  await settle();
  const controls = [
    ui.currentPassword, ui.newPassword, ui.repeatPassword, ui.passwordSave, ui.settingsClose,
  ];
  assert.ok(controls.every(control => control.disabled));
  await ui.passwordForm.dispatch("submit");
  ui.document.dispatch("keydown", { key: "Escape" });
  ui.settings.dispatch("click", { target: ui.settings });
  assert.equal(ui.settings.hidden, false);
  assert.equal(ui.passwordRequests.length, 1);

  answer.resolve({ status: 204, json: async () => ({}) });
  await pending;
  await settle();
  assert.ok(controls.every(control => !control.disabled));
});

test("a 401 on password change refreshes the session and retries once", async () => {
  const ui = await setup(deferred(), {
    refreshStatuses: [200],
    passwordResponses: [{ status: 401, body: { error: "unauthorized" } }, { status: 204 }],
  });
  ui.settingsButton.dispatch("click");
  fillPassword(ui);

  await ui.passwordForm.dispatch("submit");
  await settle();

  assert.equal(ui.passwordRequests.length, 2);
  assert.ok(ui.authRequests.includes("/api/v1/auth/refresh"));
  assert.equal(
    ui.passwordStatus.textContent,
    "Пароль изменён. На других устройствах нужно войти заново",
  );
});

test("a password change without a session opens the login page", async () => {
  const ui = await setup(deferred(), {
    refreshStatuses: [401],
    passwordResponses: [{ status: 401, body: { error: "unauthorized" } }],
  });
  ui.settingsButton.dispatch("click");
  fillPassword(ui);

  await ui.passwordForm.dispatch("submit");
  await settle();

  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.passwordRequests.length, 1);
});

test("settings keep the answer streaming and the dialog connected", async () => {
  const submitted = deferred();
  const ui = await setup(submitted);
  ui.prompt.value = "Расскажи историю";
  const sending = ui.form.dispatch("submit");
  submitted.resolve({ status: 202 });
  await sending;
  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Жил-был" });

  ui.settingsButton.dispatch("click");
  fillPassword(ui);
  await ui.passwordForm.dispatch("submit");
  await settle();
  ui.settingsClose.dispatch("click");
  ui.source.emit("message_delta", { delta: " Крош" });

  assert.equal(FakeEventSource.instances.length, 1);
  assert.notEqual(ui.source.closed, true);
  assert.equal(ui.send.disabled, true, "the answer is still being written");
  assert.equal(ui.bubbles().at(-1).textContent, "Жил-был Крош");
});

test("passwords never reach browser storage", async () => {
  const touched = [];
  const storage = new Proxy({}, { get: (_target, key) => touched.push(key) });
  globalThis.localStorage = storage;
  globalThis.sessionStorage = storage;
  try {
    const ui = await setup(deferred());
    ui.settingsButton.dispatch("click");
    fillPassword(ui);
    await ui.passwordForm.dispatch("submit");
    await settle();
    assert.deepEqual(touched, []);
  } finally {
    delete globalThis.localStorage;
    delete globalThis.sessionStorage;
  }
});
