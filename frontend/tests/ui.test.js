// @vitest-environment jsdom
import assert from "node:assert/strict";
import { test, vi, afterEach } from "vitest";
import { mount, unmount, flushSync } from "svelte";
import { ChatPage, createChat } from "../src/pages/chat";
import { AgentApi } from "../src/entities/dialog";
import { AuthApi } from "../src/entities/session";

let mounted;
async function cleanup() {
  if (mounted) await unmount(mounted);
  mounted = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
}
afterEach(cleanup);

function fire(target, type, options = {}) {
  if (type === "click") target.click();
  else {
    const EventClass = type === "keydown" ? KeyboardEvent : Event;
    target.dispatchEvent(new EventClass(type, { bubbles: true, cancelable: true, ...options }));
  }
  flushSync();
  return settle();
}
function input(target, value) {
  target.value = value;
  void fire(target, "input");
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
    flushSync();
  }

  emitRaw(type, data) {
    this.listeners.get(type)?.({ data });
    flushSync();
  }

  fail() { this.onerror?.(); flushSync(); }

  close() { this.closed = true; }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}



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
  createdId = "dialog-1",
  preserveSession = false,
  initSession,
  storedVoice,
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
  audioStatuses = [202],
  audioGetStatuses = [200],
  audioDownloadStatuses = [200],
  audioBlob = new Blob(["mp3"]),
} = {}) {
  await cleanup();
  localStorage.clear();
  if (storedVoice !== undefined) localStorage.setItem("smeshariki.voice", storedVoice);
  if (!preserveSession) sessionStorage.clear();
  initSession?.();
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
  const audioRequests = [];
  const audioGetRequests = [];
  const audioDownloadRequests = [];
  const redirects = [];
  let listCalls = 0;
  const nextStatus = (statuses, path) =>
    statuses[authRequests.filter(request => request === path).length - 1] ?? statuses.at(-1);
  // Clipboard API, or none outside a secure context, and the textarea fallback.
  const copied = [];
  const execCopies = [];
  const body = document.body;
  const clipboards = {
    ok: { writeText: async text => { copied.push(text); } },
    denied: { writeText: async () => { throw new Error("NotAllowedError"); } },
    none: undefined,
  };
  Object.defineProperty(navigator, "clipboard", { value: clipboards[clipboard], configurable: true });
  FakeEventSource.instances = [];
  document.execCommand = command => {
    const area = body.querySelector(".sai-copy-buffer");
    execCopies.push({ command, text: area?.value, selected: area?.selectionEnd === area?.value.length });
    return execCommandResult;
  };
  vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(30);
  vi.spyOn(HTMLTextAreaElement.prototype, "clientHeight", "get").mockReturnValue(30);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => {});
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const objectUrls = [];
  const revokedUrls = [];
  URL.createObjectURL = blob => {
    const url = `blob:test-${objectUrls.length + 1}`;
    objectUrls.push({ url, blob });
    return url;
  };
  URL.revokeObjectURL = url => revokedUrls.push(url);
  const storage = localStorage;
  const realTimeout = window.setTimeout.bind(window);
  vi.spyOn(window, "setTimeout").mockImplementation((callback, delay) => {
    if (delay === undefined) return realTimeout(callback);
    const id = ++nextTimer;
    timers.set(id, callback);
    timerDelays.push(delay);
    return id;
  });
  vi.spyOn(window, "clearTimeout").mockImplementation(id => timers.delete(id));
  vi.stubGlobal("EventSource", FakeEventSource);
  vi.stubGlobal("fetch", async (...args) => {
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
    if (args[0].includes("/messages/") && args[0].includes("/audio")) {
      if (/[?&]download=1/.test(args[0])) {
        audioDownloadRequests.push(args);
        const status = audioDownloadStatuses[audioDownloadRequests.length - 1] ?? audioDownloadStatuses.at(-1);
        return { status, blob: async () => audioBlob };
      }
      if (args[1]?.method === "POST") {
        audioRequests.push(args);
        const status = audioStatuses[audioRequests.length - 1] ?? audioStatuses.at(-1);
        return { status, json: async () => ({ status: status === 200 ? "ready" : "pending" }) };
      }
      audioGetRequests.push(args);
      const status = audioGetStatuses[audioGetRequests.length - 1] ?? audioGetStatuses.at(-1);
      if (status === 202) return { status, json: async () => ({ status: "pending" }) };
      return { status, blob: async () => audioBlob };
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
      return (typeof transcripts[id] === "function" ? transcripts[id]() : transcripts[id]) ?? { status: 404, json: async () => ({ detail: "Dialog not found." }) };
    }
    requests.push(args);
    if (args[0] === "/api/v1/dialogs") {
      const status = createStatuses?.[createCalls] ?? createStatus;
      createCalls += 1;
      return { status, json: async () => ({ dialog_id: createdId }) };
    }
    return submitResponse.promise;
  });
  const model = createChat(new AgentApi(), new AuthApi(), url => redirects.push(url));
  mounted = mount(ChatPage, { target: document.body, props: { model } });
  flushSync();
  await settle();
  const source = FakeEventSource.instances[0];
  if (autoReady) source?.emit("ready", { dialog_id: "dialog-1" });
  await settle();
  const get = selector => document.querySelector(selector);
  const all = selector => Array.from(document.querySelectorAll(selector));
  const form = get("#saiForm");
  const prompt = get("#saiPrompt");
  const send = get(".sai-send");
  const notice = get(".sai-notice");
  const bubbles = () => all("#saiMessages .sai-bubble");
  const chips = all(".sai-chip");
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
    notice,
    logout: get("#saiLogout"),
    get messages() { return get("#saiMessages"); },
    krosh: () => all(".sai-krosh"),
    sidebar: get("#saiSidebar"),
    backdrop: get("#saiBackdrop"),
    toggle: get("#saiHistoryToggle"),
    newStory: get("#saiNewStory"),
    history: get("#saiHistory"),
    historyState: get("#saiHistoryState"),
    historyRetry: get("#saiHistoryRetry"),
    userLogin: get("#saiUserLogin"),
    title: get("#saiTitle"),
    historyItems: () => all("#saiHistory li > :first-child"),
    historyRequests,
    feedbackRequests,
    deleteRequests,
    reportRequests,
    newsRequests,
    newsSeenRequests,
    passwordRequests,
    settingsButton: get("#saiSettingsButton"),
    settings: get("#saiSettings"),
    settingsClose: get("#saiSettingsClose"),
    passwordForm: get("#saiPasswordForm"),
    currentPassword: get("#saiCurrentPassword"),
    newPassword: get("#saiNewPassword"),
    repeatPassword: get("#saiRepeatPassword"),
    passwordSave: get("#saiPasswordSave"),
    passwordStatus: get("#saiPasswordStatus"),
    newsBox: get("#saiNews"),
    adminLink: get("#saiAdminLink"),
    historyRows: () => all("#saiHistory li"),
    feedbackBars: () => all(".sai-feedback"),
    length: get("#saiLength"),
    lengthButton: get("#saiLengthButton"),
    lengthPanel: get("#saiLengthPanel"),
    lengthValue: get("#saiLengthValue"),
    lengthCurrent: get("#saiLengthCurrent"),
    lengthDots: get("#saiLengthDots"),
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
    audioRequests,
    audioGetRequests,
    audioDownloadRequests,
    objectUrls,
    revokedUrls,
    voiceButton: get("#saiVoiceButton"),
    voiceValue: get("#saiVoiceValue"),
    voiceMenu: get("#saiVoiceMenu"),
    storage,
  };
}

test("dialog creation retries and recovers without a page reload", async () => {
  const ui = await setup(deferred(), { createStatuses: [503, 201] });
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.timers.size, 1);
  assert.match(ui.notice.textContent, /попробуем ещё раз/);

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
  fire(ui.window, "beforeunload");
  assert.equal(ui.timers.size, 0);
  assert.equal(await ui.runNextTimer(), false);
  assert.equal(ui.requests.length, 1);
});

test("failed dialog creation leaves the form disabled", async () => {
  const ui = await setup(deferred(), { createStatus: 503 });
  assert.equal(ui.source, undefined);
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.prompt.disabled, true);
  assert.match(ui.notice.textContent, /Не удалось подключиться/);
});

test("form waits for ready and reconnects on the same EventSource", async () => {
  const ui = await setup(deferred(), { autoReady: false });
  assert.equal(ui.send.disabled, true);
  ui.source.emit("ready");
  assert.equal(ui.send.disabled, false);
  ui.source.fail();
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.notice.textContent, "Соединение прервалось. Пробуем снова…");
  ui.source.emit("ready");
  assert.equal(ui.send.disabled, false);
  assert.equal(FakeEventSource.instances.length, 1);
  fire(ui.window, "beforeunload");
  assert.equal(ui.source.closed, true);
});

test("preset, autosize, and Enter submission remain available", async () => {
  const ui = await setup(deferred());
  assert.equal(ui.prompt.style.height, "");
  const measure = ui.form.querySelector(".sai-composer-measure");
  Object.defineProperty(measure, "scrollHeight", { get: () => measure.value ? 54 : 30 });
  await fire(ui.chips[0], "click");
  assert.match(ui.prompt.value, /Кроша и Ёжика/);
  assert.equal(ui.prompt.style.height, "30px");
  fire(ui.prompt, "keydown", { key: "Enter", shiftKey: true });
  assert.equal(ui.requests.length, 1);
  fire(ui.prompt, "keydown", { key: "Enter", shiftKey: false });
  assert.equal(ui.requests.length, 2);
  assert.equal(ui.send.disabled, true);
});

test("invalid SSE JSON is reported without displaying payload as HTML", async () => {
  const ui = await setup(deferred());
  ui.source.emitRaw("message_delta", "<script>invalid</script>");
  assert.equal(ui.notice.textContent, "некорректное событие от сервера");
  assert.equal(ui.bubbles().length, 0);
});

test("accepted request keeps the form locked until message_end", async () => {
  const response = deferred();
  const ui = await setup(response);
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  assert.equal(ui.send.disabled, true);
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.bubbles()[0].textContent, "История");
  await fire(ui.form, "submit");
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
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  ui.source.emit("message_start");
  ui.source.emit("message_error", { message: "Agent request failed." });
  assert.equal(ui.bubbles().length, 0);
  response.resolve({ status: 202 });
  await submission;
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История", "Ошибка ответа"]);
  assert.equal(ui.notice.textContent, "Agent request failed.");
  assert.equal(ui.send.disabled, false);
});

test("fast SSE deltas stay behind the user message and use one assistant bubble", async () => {
  const response = deferred();
  const ui = await setup(response);
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
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
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  ui.source.fail();
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.notice.textContent, "Соединение прервалось. Пробуем снова…");
});

test("failed submission preserves the draft and does not show it in chat", async () => {
  const response = deferred();
  const ui = await setup(response);
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
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
  assert.match(ui.notice.textContent, /попробуем ещё раз/);
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
  input(ui.prompt, "История");
  await fire(ui.form, "submit");

  const submissions = ui.requests.filter(([path]) => path.endsWith("/messages"));
  assert.equal(submissions.length, 2);
  assert.deepEqual(ui.bubbles().map(bubble => bubble.textContent), ["История"]);
  assert.deepEqual(ui.redirects, []);
});

test("an expired session on submission redirects without showing the message", async () => {
  const ui = await setup({ promise: Promise.resolve({ status: 401 }) }, { refreshStatuses: [401] });
  input(ui.prompt, "История");
  await fire(ui.form, "submit");

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
  assert.match(ui.notice.textContent, /обновите страницу/);

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
  await fire(ui.logout, "click");
  await settle();

  assert.deepEqual(ui.authRequests.slice(1), ["/api/v1/auth/logout"]);
  assert.equal(ui.source.closed, true);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("logout locks the button and ignores repeated clicks", async () => {
  const response = deferred();
  const ui = await setup(deferred(), { logoutResponse: response.promise });
  fire(ui.logout, "click");
  fire(ui.logout, "click");
  assert.equal(ui.logout.disabled, true);
  response.resolve({ status: 204 });
  await settle();

  assert.deepEqual(ui.authRequests.slice(1), ["/api/v1/auth/logout"]);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("logout cancels a pending dialog retry", async () => {
  const ui = await setup(deferred(), { createStatus: 503 });
  assert.equal(ui.timers.size, 1);
  await fire(ui.logout, "click");
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
    await fire(ui.logout, "click");
    await settle();

    assert.deepEqual(ui.redirects, []);
    assert.equal(ui.logout.disabled, false);
    assert.equal(ui.notice.textContent, "Не удалось выйти. Попробуйте ещё раз");
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

  fire(ui.historyItems()[0], "click");
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
  input(ui.prompt, "Что дальше?");
  const submission = fire(ui.form, "submit");
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.requests.at(-1)[0], "/api/v1/dialogs/d-2/messages");
});

test("a missing story keeps the current dialog and reloads the list", async () => {
  const ui = await setup(deferred(), { dialogs: SAVED });

  fire(ui.historyItems()[1], "click");
  await settle();

  assert.equal(ui.notice.textContent, "история не найдена");
  assert.notEqual(ui.source.closed, true);
  assert.equal(FakeEventSource.instances.length, 1);
  assert.equal(ui.send.disabled, false);
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs", "/api/v1/dialogs/d-1/messages", "/api/v1/dialogs"]);
});

test("stories cannot be switched while the agent answers", async () => {
  const response = deferred();
  const ui = await setup(response, { dialogs: SAVED, transcripts: { "d-2": transcript("Ракета", []) } });
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  assert.equal(ui.newStory.disabled, true);
  assert.equal(ui.historyItems()[0].disabled, true);
  response.resolve({ status: 202 });
  await submission;

  fire(ui.historyItems()[0], "click");
  fire(ui.newStory, "click");
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
  input(ui.prompt, "Крош строит ракету");
  const submission = fire(ui.form, "submit");
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
  fire(ui.historyItems()[0], "click");
  await settle();
  FakeEventSource.instances.at(-1).emit("ready");

  fire(ui.newStory, "click");
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

  fire(ui.historyRetry, "click");
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
  fire(ui.toggle, "click");
  assert.equal(ui.sidebar.classList.contains("is-open"), true);
  assert.equal(ui.backdrop.hidden, false);
  assert.equal(ui.toggle.getAttribute("aria-expanded"), "true");

  fire(ui.backdrop, "click");
  assert.equal(ui.sidebar.classList.contains("is-open"), false);
  assert.equal(ui.backdrop.hidden, true);
  assert.equal(ui.toggle.getAttribute("aria-expanded"), "false");

  fire(ui.toggle, "click");
  fire(ui.historyItems()[0], "click");
  await settle();
  assert.equal(ui.sidebar.classList.contains("is-open"), false);
});

test("a guest never requests the story list", async () => {
  const ui = await setup(deferred(), { meStatuses: [401], refreshStatuses: [401] });
  assert.deepEqual(ui.historyRequests, []);
  assert.equal(ui.newStory.disabled, true);
});

test("the chosen story length is sent with every next request", async () => {
  const responses = [{ status: 202 }, { status: 202 }, { status: 202 }];
  const ui = await setup({ get promise() { return Promise.resolve(responses.shift()); } });
  const bodies = () => ui.requests
    .filter(([path]) => path.endsWith("/messages"))
    .map(([, init]) => JSON.parse(init.body));

  input(ui.prompt, "Первая");
  await fire(ui.form, "submit");
  ui.source.emit("message_end");
  await settle();

  ui.length.value = "1";
  fire(ui.length, "input");
  input(ui.prompt, "Вторая");
  await fire(ui.form, "submit");
  ui.source.emit("message_end");
  await settle();

  fire(ui.newStory, "click");
  await settle();
  FakeEventSource.instances.at(-1).emit("ready");
  input(ui.prompt, "Третья");
  await fire(ui.form, "submit");

  assert.deepEqual(bodies(), [
    { request: "Первая" },
    { request: "Вторая", reading_minutes: 5 },
    { request: "Третья", reading_minutes: 5 },
  ]);
  assert.equal(ui.length.value, "1");
});

test("length selection unlocks when ready and prepares the next request during generation", async () => {
  const response = deferred();
  const ui = await setup(response, { autoReady: false });
  assert.equal(ui.lengthButton.disabled, true);
  assert.equal(ui.length.disabled, true);
  ui.source.emit("ready");
  assert.equal(ui.lengthButton.disabled, false);

  fire(ui.lengthButton, "click");
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  assert.equal(ui.lengthButton.disabled, false);
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.lengthPanel.hidden, true);
  assert.equal(ui.lengthButton.getAttribute("aria-expanded"), "false");
  response.resolve({ status: 202 });
  await submission;
  assert.equal(ui.lengthButton.disabled, false);
  ui.source.emit("message_end");
  assert.equal(ui.lengthButton.disabled, false);
});

test("every slider step sends its minutes and any length sends none", async () => {
  const responses = Array.from({ length: 4 }, () => ({ status: 202 }));
  const ui = await setup({ get promise() { return Promise.resolve(responses.shift()); } });
  const bodies = () => ui.requests
    .filter(([path]) => path.endsWith("/messages"))
    .map(([, init]) => JSON.parse(init.body));

  for (const value of ["0", "1", "2", "3"]) {
    ui.length.value = value;
    fire(ui.length, "input");
    input(ui.prompt, `Шаг ${value}`);
    await fire(ui.form, "submit");
    ui.source.emit("message_end");
    await settle();
  }

  assert.deepEqual(bodies(), [
    { request: "Шаг 0", reading_minutes: 2 },
    { request: "Шаг 1", reading_minutes: 5 },
    { request: "Шаг 2", reading_minutes: 10 },
    { request: "Шаг 3" },
  ]);
});

async function answered(options = {}) {
  const response = deferred();
  const ui = await setup(response, options);
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  response.resolve({ status: 202 });
  await submission;
  return ui;
}

function buttons(bar) {
  return Object.fromEntries(
    Array.from(bar.querySelectorAll(".sai-face"))
      .map(button => [button.dataset.value, button]),
  );
}

function part(bar, className) {
  if (bar.classList.contains(className)) return bar;
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
    assert.equal(image.dataset.score, score);
    assert.ok(image.src);
    assert.equal(tip.className, "sai-face-tip");
    assert.equal(face.getAttribute("aria-pressed"), "false");
  }
  assert.equal(buttons(bar)["2"].children[1].textContent, "Скорее не понравилось");
  assert.equal(part(bar, "sai-feedback-say").textContent, "");
  assert.equal(ui.messages.lastElementChild, bar);
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

  await fire(faces["4"], "click");
  assert.deepEqual(pressed(bar), ["4"]);
  assert.ok(faces["4"].classList.contains("is-selected"));
  assert.ok(bar.classList.contains("is-rated"));
  assert.equal(say.textContent, "Копатыч доволен");

  await fire(faces["5"], "click");
  assert.deepEqual(pressed(bar), ["5"]);
  assert.ok(!faces["4"].classList.contains("is-selected"));
  assert.equal(say.textContent, "Крош в восторге!");

  await fire(faces["5"], "click");
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
  await fire(faces["3"], "click");

  await fire(faces["1"], "click");

  assert.deepEqual(pressed(bar), ["3"]);
  assert.equal(part(bar, "sai-feedback-say").textContent, "Лосяш задумался");
  assert.equal(ui.notice.textContent, "Не удалось сохранить оценку");
  assert.equal(faces["1"].disabled, false);
});

test("a 401 on rating refreshes the session and retries once", async () => {
  const ui = await rated({ feedbackStatuses: [401, 204], refreshStatuses: [200] });
  const [bar] = ui.feedbackBars();

  await fire(buttons(bar)["2"], "click");

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

  fire(ui.historyItems()[0], "click");
  await settle();

  const bars = ui.feedbackBars();
  assert.equal(bars.length, 2);
  assert.deepEqual(pressed(bars[0]), ["1"]);
  assert.equal(part(bars[0], "sai-feedback-say").textContent, "Ёжик грустит");
  assert.deepEqual(pressed(bars[1]), []);
  await fire(buttons(bars[0])["1"], "click");
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

test("the delete confirmation is cancelled by its button or escape", async () => {
  const ui = await savedStories();

  fire(ui.historyRows()[0].children[TRASH], "click");
  let parts = confirmParts(ui.historyRows()[0]);
  assert.equal(parts.text.textContent, "Удалить историю?");
  assert.equal(parts.remove.textContent, "Удалить");
  assert.equal(parts.cancel.textContent, "Отмена");
  await settle();
  assert.equal(ui.document.activeElement, parts.cancel);

  fire(parts.cancel, "click");
  assert.equal(ui.historyItems()[0].textContent, "Ракета");
  await settle();
  assert.equal(ui.document.activeElement, ui.historyRows()[0].children[TRASH]);

  fire(ui.historyRows()[1].children[TRASH], "click");
  fire(ui.historyRows()[0].children[TRASH], "click");
  assert.equal(ui.historyItems()[1].textContent, "Без названия", "only one confirmation at a time");
  fire(ui.document, "keydown", { key: "Escape" });
  assert.equal(ui.historyItems()[0].textContent, "Ракета");
  await settle();
  assert.equal(ui.document.activeElement, ui.historyRows()[0].children[TRASH]);
  assert.deepEqual(ui.deleteRequests, []);
});

test("deleting another story keeps the open one", async () => {
  const ui = await savedStories();
  const created = ui.requests.length;

  fire(ui.historyRows()[0].children[TRASH], "click");
  await fire(confirmParts(ui.historyRows()[0]).remove, "click");
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
  fire(ui.historyItems()[0], "click");
  await settle();
  FakeEventSource.instances.at(-1).emit("ready");
  assert.equal(ui.title.textContent, "Ракета");
  const created = ui.requests.length;

  fire(ui.historyRows()[0].children[TRASH], "click");
  await fire(confirmParts(ui.historyRows()[0]).remove, "click");
  await settle();

  assert.equal(ui.requests.length, created + 1);
  assert.equal(ui.requests.at(-1)[0], "/api/v1/dialogs");
  assert.equal(ui.title.textContent, "Новая история");
  assert.equal(ui.krosh().length, 1);
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
});

test("a failed delete keeps the story and says so", async () => {
  const ui = await savedStories({ deleteStatuses: [503] });

  fire(ui.historyRows()[0].children[TRASH], "click");
  await fire(confirmParts(ui.historyRows()[0]).remove, "click");
  await settle();

  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Ракета", "Без названия"]);
  assert.equal(ui.notice.textContent, "Не удалось удалить историю");
});

test("a story already deleted elsewhere is simply removed", async () => {
  const ui = await savedStories({ deleteStatuses: [404] });

  fire(ui.historyRows()[0].children[TRASH], "click");
  await fire(confirmParts(ui.historyRows()[0]).remove, "click");
  await settle();

  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
  assert.notEqual(ui.notice.textContent, "Не удалось удалить историю");
});

test("a 401 on delete refreshes the session and retries once", async () => {
  const ui = await savedStories({ deleteStatuses: [401, 204], refreshStatuses: [200] });

  fire(ui.historyRows()[0].children[TRASH], "click");
  await fire(confirmParts(ui.historyRows()[0]).remove, "click");
  await settle();

  assert.equal(ui.deleteRequests.length, 2);
  assert.deepEqual(ui.historyItems().map(item => item.textContent), ["Без названия"]);
  assert.deepEqual(ui.redirects, []);
});

test("delete buttons are locked while the agent answers", async () => {
  const response = deferred();
  const ui = await setup(response, { dialogs: SAVED });
  await settle();
  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  response.resolve({ status: 202 });
  await submission;

  assert.ok(ui.historyRows().every(row => row.children[TRASH].disabled));
  ui.source.emit("message_end", { message_id: 1 });
  await settle();
  assert.ok(ui.historyRows().every(row => !row.children[TRASH].disabled));
});


function copyButton(bubble) {
  return bubble.parentElement.querySelector(".sai-copy");
}

test("copy puts the exact text to the clipboard and says so for a moment", async () => {
  const ui = await answered();
  ui.source.emit("message_delta", { delta: "Однажды Крош\nнашёл карту" });
  ui.source.emit("message_end");
  const [, answer] = ui.bubbles();
  const button = copyButton(answer);

  await fire(button, "click");

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

    await fire(button, "click");

    assert.deepEqual(ui.execCopies, [{ command: "copy", text: "История", selected: true }]);
    assert.equal(ui.body.querySelector(".sai-copy-buffer"), null);
    assert.equal(button.textContent, "Скопировано");
  });
}

test("a failed copy is reported near the composer", async () => {
  const ui = await answered({ clipboard: "none", execCommandResult: false });
  const button = copyButton(ui.bubbles()[0]);

  await fire(button, "click");

  assert.equal(ui.notice.textContent, "Не удалось скопировать");
  assert.equal(button.textContent, "Копировать");
  assert.equal(ui.body.querySelector(".sai-copy-buffer"), null);
});


function find(root, className) {
  return root.querySelector("." + className) ?? undefined;
}

function findAll(root, className) {
  return Array.from(root.querySelectorAll("." + className));
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
  await fire(report(bar).flag, "click");
  return { ui, bar };
}

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

  fire(reasons[1], "click");
  assert.deepEqual(reasons.map(reason => reason.getAttribute("aria-pressed")), ["false", "true", "false", "false"]);
  assert.equal(send.disabled, false);
  fire(reasons[3], "click");
  assert.deepEqual(reasons.map(reason => reason.getAttribute("aria-pressed")), ["false", "false", "false", "true"]);
});

for (const status of [201, 409]) {
  test(`a sent report (${status}) marks the answer as reported`, async () => {
    const { ui, bar } = await reportOpen({ reportStatuses: [status] });
    const { reasons, comment, send } = report(bar);
    fire(reasons[0], "click");
    input(comment, "  Испугался  ");

    await fire(send, "click");

    assert.deepEqual(ui.reportRequests.map(([path, init]) => [path, init.method, init.body]), [
      ["/api/v1/dialogs/dialog-1/messages/42/report", "POST", JSON.stringify({ reason: "scary", comment: "Испугался" })],
    ]);
    const { flag, panel } = report(bar);
    assert.equal(panel, undefined);
    assert.equal(flag.textContent, "Жалоба отправлена");
    assert.equal(flag.disabled, true);
    assert.ok(flag.classList.contains("is-sent"));
    assert.equal(ui.notice.textContent, "Спасибо! Взрослые посмотрят");
  });
}

test("a failed report keeps the panel with the choice", async () => {
  const { ui, bar } = await reportOpen({ reportStatuses: [503] });
  const { reasons, comment, send } = report(bar);
  fire(reasons[2], "click");
  input(comment, "Неправда");

  await fire(send, "click");

  const after = report(bar);
  assert.equal(after.panel, report(bar).panel);
  assert.ok(after.panel);
  assert.equal(after.reasons[2].getAttribute("aria-pressed"), "true");
  assert.equal(after.comment.value, "Неправда");
  assert.equal(after.send.disabled, false);
  assert.equal(after.flag.disabled, false);
  assert.equal(ui.notice.textContent, "Не удалось отправить жалобу");
});

test("a 401 on report refreshes the session and retries once", async () => {
  const { ui, bar } = await reportOpen({ reportStatuses: [401, 201], refreshStatuses: [200] });
  fire(report(bar).reasons[1], "click");

  await fire(report(bar).send, "click");

  assert.equal(ui.reportRequests.length, 2);
  assert.equal(report(bar).flag.textContent, "Жалоба отправлена");
  assert.deepEqual(ui.redirects, []);
});

test("only one report panel is open at a time", async () => {
  const ui = await rated();
  input(ui.prompt, "Ещё");
  fire(ui.form, "submit");
  await settle();
  ui.source.emit("message_start");
  ui.source.emit("message_end", { message_id: 44 });
  await settle();
  const [first, second] = ui.feedbackBars();

  await fire(report(first).flag, "click");
  await fire(report(second).flag, "click");

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
  fire(ui.historyItems()[0], "click");
  await settle();

  const [reported, fresh] = ui.feedbackBars().map(bar => report(bar).flag);
  assert.equal(reported.textContent, "Жалоба отправлена");
  assert.equal(reported.disabled, true);
  assert.equal(fresh.textContent, "Пожаловаться");
  await fire(fresh, "click");
  fire(report(ui.feedbackBars()[1]).reasons[0], "click");
  await fire(report(ui.feedbackBars()[1]).send, "click");
  assert.equal(ui.reportRequests[0][0], "/api/v1/dialogs/d-2/messages/14/report");
});


function newsParts(box) {
  const say = find(box, "sai-news-say");
  const actions = find(box, "sai-news-actions");
  return {
    face: find(box, "sai-news-face"),
    say: say?.textContent,
    buttons: actions ? Array.from(actions.children) : [],
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

  fire(buttons[0], "click");
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
  fire(newsParts(several.newsBox).buttons[0], "click");
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

  fire(newsParts(ui.newsBox).buttons[1], "click");
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
  assert.notEqual(failed.notice.textContent, "Не удалось загрузить новости");
  assert.equal(failed.notice.textContent, "");

  const unsaved = await setup(deferred(), {
    news: [{ report_id: 3, dialog_id: "d-2", dialog_title: "Ракета" }],
    newsSeenStatuses: [503],
  });
  fire(newsParts(unsaved.newsBox).buttons[0], "click");
  await settle();
  assert.equal(unsaved.newsBox.hidden, true);
  assert.equal(unsaved.notice.textContent, "");

  fire(unsaved.newStory, "click");
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

  fire(reasons[3], "click");
  assert.equal(send.disabled, true);
  assert.equal(comment.getAttribute("aria-required"), "true");
  assert.equal(comment.placeholder, "Расскажи, что не так (обязательно)");
  input(comment, "   ");
  fire(comment, "input");
  assert.equal(send.disabled, true);
  input(comment, "Скучно");
  fire(comment, "input");
  assert.equal(send.disabled, false);

  input(comment, "");
  fire(comment, "input");
  fire(reasons[0], "click");
  assert.equal(send.disabled, false);
  assert.equal(comment.getAttribute("aria-required"), "false");
  assert.equal(comment.placeholder, "Расскажи, что не так (необязательно)");

  fire(reasons[3], "click");
  input(comment, "Скучно");
  fire(comment, "input");
  await fire(send, "click");
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
    () => fire(ui.settingsClose, "click"),
    () => fire(ui.document, "keydown", { key: "Escape" }),
    () => fire(ui.settings, "click", { target: ui.settings }),
  ]) {
    fire(ui.settingsButton, "click");
    assert.equal(ui.settings.hidden, false);
    assert.equal(ui.settingsButton.getAttribute("aria-expanded"), "true");
    await settle();
  assert.equal(ui.document.activeElement, ui.currentPassword);
    fillPassword(ui);
    await close();
    assert.equal(ui.settings.hidden, true);
    assert.equal(ui.settingsButton.getAttribute("aria-expanded"), "false");
    await settle();
  assert.equal(ui.document.activeElement, ui.settingsButton);
    assert.deepEqual(
      [ui.currentPassword.value, ui.newPassword.value, ui.repeatPassword.value],
      ["", "", ""],
    );
  }
  assert.deepEqual(ui.passwordRequests, []);
});

test("the password form checks its fields before sending anything", async () => {
  const ui = await setup(deferred());
  fire(ui.settingsButton, "click");
  const cases = [
    [["", "radish456", "radish456"], "Пароль должен быть от 8 до 128 символов"],
    [["carrot123", "short", "short"], "Пароль должен быть от 8 до 128 символов"],
    [["carrot123", "x".repeat(129), "x".repeat(129)], "Пароль должен быть от 8 до 128 символов"],
    [["carrot123", "radish456", "radish457"], "Пароли не совпадают"],
    [["carrot123", "carrot123", "carrot123"], "Новый пароль совпадает с текущим"],
  ];

  for (const [[current, next, repeat], message] of cases) {
    fillPassword(ui, current, next, repeat);
    await fire(ui.passwordForm, "submit");
    assert.equal(ui.passwordStatus.textContent, message);
    assert.equal(ui.passwordStatus.dataset.state, "error");
  }
  assert.deepEqual(ui.passwordRequests, []);
});

test("a changed password clears the fields and says other devices sign in again", async () => {
  const ui = await setup(deferred());
  fire(ui.settingsButton, "click");
  fillPassword(ui);

  await fire(ui.passwordForm, "submit");
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
  fire(ui.settingsButton, "click");
  fillPassword(ui);

  await fire(ui.passwordForm, "submit");
  await settle();

  assert.equal(ui.passwordStatus.textContent, "Неверный текущий пароль");
  assert.equal(ui.currentPassword.value, "");
  assert.equal(ui.newPassword.value, "radish456");
  await settle();
  assert.equal(ui.document.activeElement, ui.currentPassword);
});

test("every other password answer gets its own message", async () => {
  const cases = [
    [{ status: 422, body: { error: "same_password" } }, "Новый пароль совпадает с текущим"],
    [{ status: 422, body: { error: "invalid_fields" } }, "Пароль должен быть от 8 до 128 символов"],
    [{ status: 429, body: { error: "too_many_attempts" } }, "Слишком много попыток. Попробуйте позже"],
    [{ status: 503, body: { error: "unavailable" } }, "Не удалось сменить пароль. Попробуйте ещё раз"],
    [{ status: 500 }, "Не удалось сменить пароль. Попробуйте ещё раз"],
    [new TypeError("Failed to fetch"), "Не удалось сменить пароль. Попробуйте ещё раз"],
  ];

  for (const [answer, message] of cases) {
    const ui = await setup(deferred(), { passwordResponses: [answer] });
    fire(ui.settingsButton, "click");
    fillPassword(ui);
    await fire(ui.passwordForm, "submit");
    await settle();
    assert.equal(ui.passwordStatus.textContent, message);
    assert.equal(ui.passwordStatus.dataset.state, "error");
  }
});

test("the settings window is locked while the password is saved", async () => {
  const answer = deferred();
  const ui = await setup(deferred(), { passwordResponses: [answer.promise] });
  fire(ui.settingsButton, "click");
  fillPassword(ui);

  const pending = fire(ui.passwordForm, "submit");
  await settle();
  const controls = [
    ui.currentPassword, ui.newPassword, ui.repeatPassword, ui.passwordSave, ui.settingsClose,
  ];
  assert.ok(controls.every(control => control.disabled));
  await fire(ui.passwordForm, "submit");
  fire(ui.document, "keydown", { key: "Escape" });
  fire(ui.settings, "click", { target: ui.settings });
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
  fire(ui.settingsButton, "click");
  fillPassword(ui);

  await fire(ui.passwordForm, "submit");
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
  fire(ui.settingsButton, "click");
  fillPassword(ui);

  await fire(ui.passwordForm, "submit");
  await settle();

  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.passwordRequests.length, 1);
});

test("settings keep the answer streaming and the dialog connected", async () => {
  const submitted = deferred();
  const ui = await setup(submitted);
  input(ui.prompt, "Расскажи историю");
  const sending = fire(ui.form, "submit");
  submitted.resolve({ status: 202 });
  await sending;
  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: "Жил-был" });

  fire(ui.settingsButton, "click");
  fillPassword(ui);
  await fire(ui.passwordForm, "submit");
  await settle();
  fire(ui.settingsClose, "click");
  ui.source.emit("message_delta", { delta: " Крош" });

  assert.equal(FakeEventSource.instances.length, 1);
  assert.notEqual(ui.source.closed, true);
  assert.equal(ui.send.disabled, true, "the answer is still being written");
  assert.equal(ui.bubbles().at(-1).textContent, "Жил-был Крош");
});

test("passwords never reach browser storage", async () => {
  const ui = await setup(deferred());
  const writes = vi.spyOn(Storage.prototype, "setItem");
  fire(ui.settingsButton, "click");
  fillPassword(ui);
  await fire(ui.passwordForm, "submit");
  assert.equal(writes.mock.calls.length, 0);
});

test("a finished answer is voiced and the action becomes download", async () => {
  const ui = await rated();
  const [bar] = ui.feedbackBars();
  const voice = part(bar, "sai-voice-line");
  const action = voice.querySelector(".sai-voice-button");
  const refresh = voice.querySelector(".sai-voice-refresh");
  const state = voice.querySelector(".sai-voice-state");
  const player = voice.querySelector(".sai-player");
  const audio = player.querySelector("audio");

  assert.equal(action.textContent, "Озвучить");
  assert.equal(refresh.hidden, true);
  assert.equal(player.hidden, true);

  await fire(action, "click");
  await settle();

  assert.equal(ui.audioRequests.length, 1);
  assert.equal(ui.audioRequests[0][0], "/api/v1/dialogs/dialog-1/messages/42/audio");
  assert.equal(ui.audioRequests[0][1].method, "POST");
  assert.deepEqual(JSON.parse(ui.audioRequests[0][1].body), { voice: "aidar" });
  assert.equal(action.textContent, "Готовим озвучку…");
  assert.equal(state.textContent, "Готовим озвучку…");
  assert.equal(ui.timers.size, 1);

  await ui.runNextTimer();
  assert.equal(ui.audioGetRequests.length, 1);
  assert.equal(
    ui.audioGetRequests[0][0],
    "/api/v1/dialogs/dialog-1/messages/42/audio?voice=aidar",
  );
  assert.equal(action.textContent, "Скачать");
  assert.equal(player.hidden, false);
  assert.match(audio.src, /^blob:test-/);
  assert.equal(ui.objectUrls.length, 1);
  assert.equal(refresh.hidden, false);
});

test("an already voiced saved answer shows download without a new POST", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: null, audio_voices: ["aidar"] },
      ]),
    },
  });
  fire(ui.historyItems()[0], "click");
  await settle();

  const [bar] = ui.feedbackBars();
  const voice = part(bar, "sai-voice-line");
  const action = voice.querySelector(".sai-voice-button");
  const refresh = voice.querySelector(".sai-voice-refresh");
  const player = voice.querySelector(".sai-player");
  const audio = player.querySelector("audio");
  assert.equal(action.textContent, "Скачать");
  assert.equal(refresh.hidden, false);
  assert.equal(player.hidden, false);
  assert.equal(
    audio.getAttribute("src"),
    "/api/v1/dialogs/d-2/messages/12/audio?voice=aidar",
  );
  assert.equal(ui.audioRequests.length, 0);

  await fire(action, "click");
  await settle();

  assert.equal(ui.audioDownloadRequests.length, 1);
  assert.equal(
    ui.audioDownloadRequests[0][0],
    "/api/v1/dialogs/d-2/messages/12/audio?voice=aidar&download=1",
  );
  assert.equal(ui.objectUrls.length, 1);
  assert.equal(ui.revokedUrls.length, 0);
  await ui.runNextTimer();
  assert.equal(ui.revokedUrls.length, 1);
});

test("a failed voiceover leaves a safe message and the original action", async () => {
  const ui = await rated({ audioStatuses: [503] });
  const [bar] = ui.feedbackBars();
  const action = bar.querySelector(".sai-voice-button");
  const state = bar.querySelector(".sai-voice-state");

  await fire(action, "click");
  await settle();

  assert.equal(action.textContent, "Озвучить");
  assert.equal(state.textContent, "Озвучка недоступна");
  assert.equal(ui.audioGetRequests.length, 0);
});

test("switching stories stops the current player", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 12, role: "assistant", content: "Однажды…", created_at: "x", feedback: null, audio_voices: ["aidar"] },
      ]),
      "d-1": transcript("Без названия", []),
    },
  });
  fire(ui.historyItems()[0], "click");
  await settle();
  const player = ui.feedbackBars()[0].querySelector(".sai-player");
  const audio = player.querySelector("audio");
  assert.equal(player.hidden, false);

  fire(ui.historyItems()[1], "click");
  await settle();

  assert.equal(audio.paused, true);
  assert.ok(HTMLMediaElement.prototype.load.mock.contexts.includes(audio));
});

test("the voice picker stores the selected voice", async () => {
  const ui = await setup(deferred());
  assert.equal(ui.voiceMenu.hidden, true);

  fire(ui.voiceButton, "click");
  assert.equal(ui.voiceMenu.hidden, false);
  assert.equal(ui.voiceButton.getAttribute("aria-expanded"), "true");
  const options = Array.from(ui.voiceMenu.children);
  assert.deepEqual(options.map(option => [option.dataset.voice, option.textContent.trim()]), [
    ["aidar", "Айдар"],
    ["xenia", "Ксения"],
  ]);
  assert.equal(options[0].getAttribute("aria-selected"), "true");

  fire(options[1], "click");
  assert.equal(ui.storage.getItem("smeshariki.voice"), "xenia");
  assert.equal(ui.voiceMenu.hidden, true);
});

test.each([
  ["aidar", "aidar", "Айдар"],
  ["xenia", "xenia", "Ксения"],
  ["baya", "aidar", "Айдар"],
  ["kseniya", "aidar", "Айдар"],
  ["eugene", "aidar", "Айдар"],
  ["unknown", "aidar", "Айдар"],
])("loading the chat resolves the stored voice %s to %s", async (storedVoice, expectedId, label) => {
  const ui = await setup(deferred(), { storedVoice });
  assert.equal(ui.voiceValue.textContent, label);
  assert.equal(ui.voiceButton.getAttribute("aria-label"), `Выбрать голос рассказчика, сейчас ${label}`);
  assert.equal(ui.storage.getItem("smeshariki.voice"), expectedId);
  await fire(ui.voiceButton, "click");
  assert.equal(ui.voiceMenu.querySelector('[aria-selected="true"]').dataset.voice, expectedId);
});

test("the chosen voice is sent with a new voiceover request", async () => {
  const response = deferred();
  const ui = await setup(response);
  fire(ui.voiceButton, "click");
  fire(ui.voiceMenu.querySelector('[data-voice="xenia"]'), "click");

  input(ui.prompt, "История");
  const submission = fire(ui.form, "submit");
  response.resolve({ status: 202 });
  await submission;
  ui.source.emit("message_start");
  ui.source.emit("message_end", { message_id: 42 });
  await settle();

  const [bar] = ui.feedbackBars();
  const [action] = part(bar, "sai-voice-line").children;
  await fire(action, "click");
  await settle();

  assert.deepEqual(JSON.parse(ui.audioRequests[0][1].body), { voice: "xenia" });
});

test("a failed history read leaves a pending dialog creation retry active", async () => {
  const history = deferred();
  const ui = await setup(deferred(), {
    createStatuses: [503, 201], dialogs: SAVED, transcripts: { "d-2": history.promise },
  });
  fire(ui.historyItems()[0], "click");
  assert.equal(await ui.runNextTimer(), true);
  history.resolve({ status: 503 });
  await settle();
  assert.equal(await ui.runNextTimer(), true);
  FakeEventSource.instances.at(-1).emit("ready");
  assert.equal(ui.send.disabled, false);
});

test("a reconnect keeps history navigation locked until the transcript arrives", async () => {
  const history = deferred();
  const ui = await setup(deferred(), { dialogs: SAVED, transcripts: { "d-2": history.promise } });
  fire(ui.historyItems()[0], "click");
  ui.source.readyState = 2;
  ui.source.fail();
  await settle();
  const replacement = FakeEventSource.instances.at(-1);
  replacement.emit("ready");
  assert.equal(ui.historyItems()[1].disabled, true);
  history.resolve(transcript("Ракета", []));
  await settle();
  assert.equal(replacement.closed, true);
  assert.equal(FakeEventSource.instances.at(-1).url, "/api/v1/dialogs/d-2/events");
});

test("a late voiceover leaves the selected voice playing and available for download", async () => {
  const ui = await setup(deferred(), {
    dialogs: SAVED,
    transcripts: {
      "d-2": transcript("Ракета", [
        { id: 12, role: "assistant", content: "Однажды…", feedback: null, audio_voices: ["baya", "xenia"] },
      ]),
    },
  });
  await fire(ui.historyItems()[0], "click");
  FakeEventSource.instances.at(-1).emit("ready");
  const bar = ui.feedbackBars()[0];
  const action = bar.querySelector(".sai-voice-button");
  const audio = bar.querySelector("audio");
  const toggle = bar.querySelector(".sai-player-toggle");
  await fire(action, "click");
  assert.equal(ui.timers.size, 1);
  await fire(ui.voiceButton, "click");
  await fire(ui.voiceMenu.querySelector('[data-voice="xenia"]'), "click");
  await fire(audio, "play");
  assert.equal(toggle.getAttribute("aria-label"), "Поставить на паузу");
  assert.equal(action.textContent, "Скачать");
  assert.equal(action.disabled, false);
  const selectedUrl = audio.src;
  assert.match(selectedUrl, /voice=xenia$/);
  HTMLMediaElement.prototype.pause.mockClear();
  HTMLMediaElement.prototype.load.mockClear();

  await fire(action, "click");
  assert.match(ui.audioDownloadRequests[0][0], /voice=xenia&download=1$/);
  assert.equal(await ui.runNextTimer(), true);
  assert.match(ui.audioGetRequests[0][0], /voice=aidar$/);
  assert.equal(audio.src, selectedUrl);
  assert.equal(toggle.getAttribute("aria-label"), "Поставить на паузу");
  assert.equal(HTMLMediaElement.prototype.pause.mock.calls.length, 0);
  assert.equal(HTMLMediaElement.prototype.load.mock.calls.length, 0);

  await fire(ui.voiceButton, "click");
  await fire(ui.voiceMenu.querySelector('[data-voice="aidar"]'), "click");
  assert.equal(action.textContent, "Скачать");
  assert.match(audio.src, /^blob:test-/);
});

test.each(["click", "Enter"])("%s starts a fresh focused draft immediately and blocks duplicate sends", async method => {
  const response = deferred();
  const ui = await setup(response);
  assert.equal(ui.prompt.placeholder, "Идея для сказки");
  assert.equal(ui.length.value, "3");
  assert.equal(ui.length.getAttribute("aria-valuetext"), "Любая");

  input(ui.prompt, "Первая история");
  const target = method === "click" ? ui.send : ui.prompt;
  target.focus();
  const posting = method === "click" ? fire(target, "click") : fire(target, "keydown", { key: "Enter" });
  assert.equal(ui.prompt.value, "");
  assert.equal(document.activeElement, ui.prompt);
  assert.equal(ui.prompt.disabled, false);
  assert.equal(ui.send.disabled, true);
  input(ui.prompt, "Следующая идея");
  await fire(ui.prompt, "keydown", { key: "Enter" });
  ui.lengthButton.focus();
  response.resolve({ status: 202 });
  await posting;
  await settle();
  assert.equal(document.activeElement, ui.lengthButton);
  assert.equal(ui.prompt.value, "Следующая идея");
  assert.equal(ui.bubbles()[0].textContent, "Первая история");

  input(ui.prompt, "Ещё одна идея");
  await fire(ui.form, "submit");
  assert.equal(ui.requests.filter(([path]) => path.endsWith("/messages")).length, 1);
  ui.source.emit("message_end");
  assert.equal(document.activeElement, ui.lengthButton);
  assert.equal(ui.prompt.value, "Ещё одна идея");
  assert.equal(ui.send.disabled, false);
  await fire(ui.prompt, "keydown", { key: "Enter" });
  assert.deepEqual(JSON.parse(ui.requests.at(-1)[1].body), { request: "Ещё одна идея" });
  assert.equal(ui.prompt.value, "");
});

test.each(["Следующая идея", ""])("a failed POST keeps the edited next draft %j", async nextDraft => {
  const response = deferred();
  const ui = await setup(response);
  input(ui.prompt, "Первая история");
  const posting = fire(ui.send, "click");
  input(ui.prompt, "Новая идея");
  input(ui.prompt, nextDraft);
  response.resolve({ status: 503 });
  await posting;
  assert.equal(ui.prompt.value, nextDraft);
  assert.equal(ui.send.disabled, false);
});

test("IME confirmation and Shift+Enter allow native editing without submitting", async () => {
  const ui = await setup(deferred());
  input(ui.prompt, "История");
  for (const options of [{ isComposing: true }, { keyCode: 229 }, { shiftKey: true }]) {
    const key = new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true, ...options });
    ui.prompt.dispatchEvent(key);
    assert.equal(key.defaultPrevented, false);
  }
  assert.equal(ui.requests.filter(([path]) => path.endsWith("/messages")).length, 0);
});

const savedId = "eee57d4a-6420-4dc1-b713-623941784987";
const freshId = "aeee032b-69cc-46f5-bc5a-6ed47f99bc6a";
const sessionKey = "smeshariki.dialog.user-1";
const savedPair = [
  { id: 21, role: "user", content: "История до F5", feedback: null },
  { id: 22, role: "assistant", content: "Полный ответ", feedback: 4 },
];
const savedPath = `/api/v1/dialogs/${savedId}/messages`;

test("F5 restores the created draft and later the selected saved story in the same tab", async () => {
  const first = await setup(deferred(), { createdId: freshId });
  assert.equal(sessionStorage.getItem(sessionKey), freshId);
  const dialogs = [{ ...SAVED[0], dialog_id: savedId }];
  const transcripts = { [freshId]: transcript(null, []), [savedId]: transcript("Архив", savedPair) };
  const draft = await setup(deferred(), { preserveSession: true, dialogs, transcripts });
  assert.equal(first.source.closed, true);
  assert.equal(draft.requests.length, 0);
  assert.match(draft.source.url, new RegExp(freshId));
  assert.equal(draft.krosh().length, 1);
  await fire(draft.historyItems()[0], "click");
  assert.equal(sessionStorage.getItem(sessionKey), savedId);
  const restored = await setup(deferred(), { preserveSession: true, transcripts });
  assert.equal(restored.requests.length, 0);
  assert.deepEqual(restored.historyRequests, ["/api/v1/dialogs", savedPath]);
  assert.deepEqual(restored.bubbles().map(b => b.textContent), savedPair.map(m => m.content));
  assert.equal(restored.send.disabled, false);
  assert.equal(sessionStorage.length, 1);
  assert.equal(sessionStorage.getItem(sessionKey), savedId);
});

test("F5 never requests another user's selection or a malformed id", async () => {
  const initSession = () => {
    sessionStorage.setItem("smeshariki.dialog.previous-user", savedId);
    sessionStorage.setItem(sessionKey, "not-a-uuid");
  };
  const ui = await setup(deferred(), { initSession, createdId: freshId });
  assert.deepEqual(ui.historyRequests, ["/api/v1/dialogs"]);
  assert.equal(ui.requests.length, 1);
  assert.equal(sessionStorage.getItem(sessionKey), freshId);
});

test("restoring or opening a dialog positions its rendered history once per visit", async () => {
  const reading = deferred();
  const selection = deferred();
  let selectedReply = selection.promise;
  const ui = await setup(deferred(), { initSession: () => sessionStorage.setItem(sessionKey, savedId),
    dialogs: [{ ...SAVED[0], dialog_id: savedId }, { ...SAVED[1], dialog_id: freshId }],
    transcripts: { [savedId]: reading.promise, [freshId]: () => selectedReply } });
  // jsdom has no layout. Only rendered rows contribute to the simulated height.
  vi.spyOn(HTMLDivElement.prototype, "scrollHeight", "get").mockImplementation(function () {
    return this.querySelectorAll(".sai-row").length * 800;
  });
  reading.resolve(transcript("Архив", savedPair));
  await settle();
  assert.equal(ui.messages.scrollTop, 1600);

  ui.messages.scrollTop = 128;
  ui.source.emit("message_delta", { delta: "Продолжение" });
  ui.source.emit("message_end", { message_id: 22 });
  await settle();
  ui.source.emit("ready");
  await settle();
  assert.equal(ui.messages.scrollTop, 128);

  const originalLog = ui.messages;
  await fire(ui.historyItems()[1], "click");
  assert.equal(ui.messages, originalLog);
  assert.equal(ui.messages.scrollTop, 128);
  selection.resolve({ status: 503 });
  await settle();
  assert.equal(ui.messages, originalLog);
  assert.equal(ui.messages.scrollTop, 128);

  selectedReply = transcript("Другая история", savedPair);
  await fire(ui.historyItems()[1], "click");
  assert.notEqual(ui.messages, originalLog);
  assert.equal(ui.messages.scrollTop, 1600);
  FakeEventSource.instances.at(-1).emit("ready");
  await settle();
  ui.messages.scrollTop = 256;
  await fire(ui.historyItems()[1], "click");
  assert.equal(ui.messages.scrollTop, 256);
  await fire(ui.historyItems()[0], "click");
  assert.equal(ui.messages.scrollTop, 1600);
});

test("F5 handles a missing or foreign selection even when SSE fails before ready", async () => {
  const ui = await setup(deferred(), { autoReady: false, createdId: freshId,
    initSession: () => sessionStorage.setItem(sessionKey, savedId) });
  ui.source.fail();
  await settle();
  assert.equal(ui.source.closed, true);
  assert.equal(ui.historyRequests.filter(p => p === savedPath).length, 1);
  assert.equal(ui.requests.length, 1);
  assert.equal(sessionStorage.getItem(sessionKey), freshId);
  assert.equal(ui.timers.size, 0);
});

test("a temporarily unavailable transcript retries the same selection and sends no messages", async () => {
  let unavailable = true;
  const ui = await setup(deferred(), { initSession: () => sessionStorage.setItem(sessionKey, savedId),
    transcripts: { [savedId]: () => unavailable ? { status: 503 } : transcript("Архив", savedPair) } });
  assert.equal(sessionStorage.getItem(sessionKey), savedId);
  assert.equal(ui.send.disabled, true);
  unavailable = false;
  await ui.runNextTimer();
  FakeEventSource.instances.at(-1).emit("ready");
  await settle();
  assert.equal(ui.send.disabled, false);
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.historyRequests.filter(p => p === savedPath).length, 2);
});

test("F5 in the middle of a run loads both committed messages after the final SSE event", async () => {
  let committed = false;
  const ui = await setup(deferred(), { initSession: () => sessionStorage.setItem(sessionKey, savedId),
    transcripts: { [savedId]: () => transcript(committed ? "Архив" : null, committed ? savedPair : []) } });
  assert.deepEqual(ui.bubbles(), []);
  Object.defineProperty(ui.messages, "scrollHeight", { value: 2400 });
  ui.source.emit("message_delta", { delta: "пропущено начало" });
  assert.equal(ui.send.disabled, true);
  assert.deepEqual(ui.bubbles(), []);
  committed = true;
  ui.source.emit("message_end", { message_id: 22 });
  await settle();
  assert.deepEqual(ui.bubbles().map(b => b.textContent), savedPair.map(m => m.content));
  assert.equal(ui.messages.scrollTop, 0);
  assert.equal(ui.send.disabled, false);
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.historyRequests.filter(p => p === savedPath).length, 2);
});

test("F5 coalesces an end observed while a transcript already contains that commit", async () => {
  const reading = deferred();
  const ui = await setup(deferred(), { initSession: () => sessionStorage.setItem(sessionKey, savedId),
    transcripts: { [savedId]: reading.promise } });
  assert.equal(ui.send.disabled, true);
  ui.source.emit("message_end", { message_id: 22 });
  reading.resolve(transcript("Архив", savedPair));
  await settle();
  assert.deepEqual(ui.bubbles().map(b => b.textContent), savedPair.map(m => m.content));
  assert.equal(ui.historyRequests.filter(p => p === savedPath).length, 1);
});

test("explicit logout forgets the open dialog only after success", async () => {
  const failed = await setup(deferred(), { createdId: freshId, logoutResponse: Promise.resolve({ status: 503 }) });
  await fire(failed.logout, "click");
  assert.equal(sessionStorage.getItem(sessionKey), freshId);
  const ui = await setup(deferred(), { preserveSession: true, transcripts: { [freshId]: transcript(null, []) } });
  await fire(ui.logout, "click");
  assert.equal(sessionStorage.getItem(sessionKey), null);
});

test("blocked sessionStorage still allows normal chat", async () => {
  const ui = await setup(deferred(), { createdId: freshId, initSession: () => {
    vi.stubGlobal("sessionStorage", {
      getItem() { throw new Error("unavailable"); },
      setItem() { throw new Error("unavailable"); },
      removeItem() { throw new Error("unavailable"); },
    });
  } });
  assert.equal(ui.requests.length, 1);
  assert.equal(ui.send.disabled, false);
});

test("waiting begins on submit, survives start and blank chunks, then gives way to the streamed answer", async () => {
  const response = deferred();
  const ui = await setup(response);
  const waiting = () => ui.messages.querySelector("[data-story-waiting]");
  const announcement = ui.document.querySelector(".sai-sr-only[role=status]");
  const interval = vi.spyOn(window, "setInterval").mockReturnValue(42);
  const clear = vi.spyOn(window, "clearInterval");
  const random = vi.spyOn(Math, "random").mockReturnValue(0.99);
  assert.equal(ui.document.querySelector(".sai-chat-head [role=status]"), null);
  assert.equal(ui.notice.textContent, "");
  assert.equal(waiting(), null);
  input(ui.prompt, "Куда отправимся?");
  const submission = fire(ui.form, "submit");
  const first = waiting();
  assert.ok(first);
  assert.equal(first.getAttribute("aria-hidden"), "true");
  assert.equal(announcement.textContent, "Смешарики сочиняют историю…");
  const phrase = () => first.querySelector(".sai-wait-phrase").textContent;
  assert.ok(["Ищем карту Кроша…", "Поливаем грядки…"].includes(phrase()));
  const [nextPhrase] = interval.mock.calls.find(([, delay]) => delay === 3000);
  random.mockReturnValue(0);
  nextPhrase();
  flushSync();
  assert.equal(phrase(), "Красим скамейку…");
  nextPhrase();
  flushSync();
  assert.equal(phrase(), "Раскладываем фантики…");
  assert.equal(announcement.textContent, "Смешарики сочиняют историю…");
  assert.equal(ui.bubbles().length, 0);
  response.resolve({ status: 202 });
  await submission;
  ui.source.emit("message_start");
  ui.source.emit("message_delta", { delta: " " });
  assert.equal(waiting(), first);
  assert.deepEqual(ui.bubbles().map(b => b.textContent), ["Куда отправимся?"]);
  assert.equal(ui.messages.getAttribute("aria-busy"), "true");
  ui.source.emit("message_delta", { delta: "Привет" });
  assert.equal(waiting(), null);
  assert.ok(clear.mock.calls.some(([id]) => id === 42));
  assert.equal(announcement.textContent, "");
  assert.equal(ui.bubbles().at(-1).textContent, " Привет");
  ui.source.emit("message_end", { message_id: 7 });
  assert.equal(ui.messages.getAttribute("aria-busy"), "false");
});

test("streaming and completion preserve a reader's scroll position", async () => {
  const ui = await answered();
  const log = ui.messages;
  Object.defineProperty(log, "scrollHeight", { value: 2400, configurable: true });
  log.scrollTop = 128;
  ui.source.emit("message_start");
  assert.equal(log.scrollTop, 128);
  ui.source.emit("message_delta", { delta: "Однажды…" });
  assert.equal(log.scrollTop, 128);
  log.scrollTop = 300;
  ui.source.emit("message_delta", { delta: " Крош поехал в гости." });
  assert.equal(log.scrollTop, 300);
  ui.source.emit("message_end", { message_id: 42 });
  await settle();
  assert.equal(log.scrollTop, 300);
});

test.each(["message_error", "message_end", "close", "reject"])("waiting clears on %s, including without a first delta", async ending => {
  const response = deferred();
  const ui = await setup(response);
  const interval = vi.spyOn(window, "setInterval").mockReturnValue(73);
  const clear = vi.spyOn(window, "clearInterval");
  input(ui.prompt, "Ещё одна история");
  const submission = fire(ui.form, "submit");
  assert.ok(ui.messages.querySelector("[data-story-waiting]"));
  response.resolve({ status: ending === "reject" ? 503 : 202 });
  await submission;
  if (ending === "close") await fire(window, "beforeunload");
  else if (ending !== "reject") ui.source.emit(ending);
  assert.equal(ui.messages.querySelector("[data-story-waiting]"), null);
  assert.equal(interval.mock.calls.length, 1);
  assert.ok(clear.mock.calls.some(([id]) => id === 73));
});

test("reduced motion picks a different static phrase for consecutive quick requests", async () => {
  const ui = await setup({ promise: Promise.resolve({ status: 202 }) });
  const change = vi.fn();
  vi.stubGlobal("matchMedia", () => ({ matches: true, addEventListener: change, removeEventListener: vi.fn() }));
  const interval = vi.spyOn(window, "setInterval");
  vi.spyOn(Math, "random").mockReturnValue(0.99);
  const phrase = () => ui.messages.querySelector(".sai-wait-phrase").textContent;
  input(ui.prompt, "История");
  await fire(ui.form, "submit");
  const first = phrase();
  ui.source.emit("message_end");
  input(ui.prompt, "Продолжение");
  await fire(ui.form, "submit");
  assert.deepEqual(new Set([first, phrase()]), new Set(["Ищем карту Кроша…", "Поливаем грядки…"]));
  assert.equal(interval.mock.calls.length, 0);
  assert.equal(change.mock.calls[0][0], "change");
});

test("F5 after 202 before the first delta holds send, allows typing, and never resubmits", async () => {
  const post = deferred();
  const first = await setup(post, { createdId: savedId });
  input(first.prompt, "Новый запрос");
  void fire(first.form, "submit");
  post.resolve({ status: 202 });
  await settle();
  let committed = false;
  const ui = await setup(deferred(), { preserveSession: true, transcripts: {
    [savedId]: () => transcript(null, committed ? savedPair : []),
  } });
  assert.equal(ui.prompt.disabled, false);
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.messages.getAttribute("aria-busy"), "true");
  input(ui.prompt, "Следующая идея");
  await fire(ui.form, "submit");
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.prompt.value, "Следующая идея");
  assert.ok(!JSON.stringify(sessionStorage).includes("Новый запрос"));
  committed = true;
  ui.source.emit("message_end", { message_id: 22 });
  await settle();
  assert.equal(ui.send.disabled, false);
  assert.equal(ui.timers.size, 0);
  assert.equal(sessionStorage.length, 1);
  assert.deepEqual(ui.bubbles().map(b => b.textContent), savedPair.map(m => m.content));
});

test("a run that committed before F5 subscribed is recognized on the first snapshot", async () => {
  const post = deferred();
  const first = await setup(post, { createdId: savedId });
  input(first.prompt, "Новый запрос");
  void fire(first.form, "submit");
  post.resolve({ status: 202 });
  await settle();
  const ui = await setup(deferred(), { preserveSession: true, transcripts: { [savedId]: transcript(null, savedPair) } });
  assert.deepEqual(ui.bubbles().map(b => b.textContent), savedPair.map(m => m.content));
  assert.equal(ui.send.disabled, false);
  assert.equal(ui.timers.size, 0);
  assert.equal(ui.requests.length, 0);
  assert.equal(sessionStorage.length, 1);
});

test("an unchanged previous answer keeps F5 waiting; a lost terminal error eventually releases send", async () => {
  const post = deferred();
  const transcripts = { [savedId]: transcript("Архив", savedPair) };
  const first = await setup(post, { initSession: () => sessionStorage.setItem(sessionKey, savedId), transcripts });
  input(first.prompt, "Ещё история");
  void fire(first.form, "submit");
  post.resolve({ status: 202 });
  await settle();
  const ui = await setup(deferred(), { preserveSession: true, transcripts });
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.prompt.disabled, false);
  assert.ok(ui.timerDelays.some(delay => delay > 0 && delay <= 120000));
  await ui.runNextTimer();
  assert.equal(ui.send.disabled, false);
  assert.equal(ui.requests.length, 0);
  assert.equal(ui.timers.size, 0);
  assert.deepEqual(ui.bubbles().map(b => b.textContent), savedPair.map(m => m.content));
});

test("the composer switches rows only when text needs more than the compact column", async () => {
  const ui = await setup(deferred());
  const measure = ui.form.querySelector(".sai-composer-measure");
  let available = 128;
  Object.defineProperty(measure, "clientHeight", { value: 34 });
  Object.defineProperty(measure, "scrollHeight", { get: () => measure.value.length * 8 > available ? 54 : 34 });
  const expanded = () => ui.form.classList.contains("is-expanded");

  assert.equal(expanded(), false);
  input(ui.prompt, "Крош");
  assert.equal(expanded(), false);
  input(ui.prompt, "Крош идёт искать поляну");
  assert.equal(expanded(), true);
  available = 300;
  await fire(window, "resize");
  assert.equal(expanded(), false);
  available = 128;
  await fire(window, "resize");
  assert.equal(expanded(), true);
  input(ui.prompt, "Крош");
  assert.equal(expanded(), false);
  input(ui.prompt, "Крош\n");
  assert.equal(expanded(), true);
  input(ui.prompt, "");
  assert.equal(expanded(), false);
});

test("a failed multiline draft stays expanded and a successful retry collapses it", async () => {
  const statuses = [503, 202];
  const ui = await setup({ get promise() { return Promise.resolve({ status: statuses.shift() }); } });
  const text = "Крош и Ёжик\nстроят ракету";
  input(ui.prompt, text);
  await fire(ui.form, "submit");
  assert.equal(ui.form.classList.contains("is-expanded"), true);
  assert.equal(ui.prompt.value, text);
  await fire(ui.form, "submit");
  assert.equal(ui.form.classList.contains("is-expanded"), false);
  assert.equal(ui.prompt.value, "");
});

test("a late delta postpones the F5 silence deadline, then a terminal error clears the marker", async () => {
  const now = Date.now();
  const ui = await setup(deferred(), { initSession: () => {
    sessionStorage.setItem(sessionKey, savedId);
    sessionStorage.setItem("smeshariki.turn.user-1", JSON.stringify({
      dialogId: savedId, lastAnswer: null, expiresAt: now + 1000,
    }));
  }, transcripts: { [savedId]: transcript(null, []) } });
  assert.equal(ui.send.disabled, true);
  ui.source.emit("message_delta", { delta: "…" });
  await ui.runNextTimer();
  assert.equal(ui.send.disabled, true);
  assert.equal(ui.timers.size, 1);
  ui.source.emit("message_error", { message: "Ответ прерван" });
  assert.equal(ui.timers.size, 0);
  assert.equal(ui.send.disabled, false);
  assert.equal(sessionStorage.length, 1);
});

test("deleting the open selection clears its UUID even if the replacement draft is unavailable", async () => {
  const dialogs = [{ ...SAVED[0], dialog_id: savedId }];
  const ui = await setup(deferred(), { initSession: () => sessionStorage.setItem(sessionKey, savedId),
    createStatus: 503, dialogs, transcripts: { [savedId]: transcript(null, []) } });
  await fire(document.querySelector(".sai-history-delete"), "click");
  await fire(document.querySelector(".sai-history-confirm-delete"), "click");
  assert.equal(ui.deleteRequests.length, 1);
  assert.equal(sessionStorage.getItem(sessionKey), null);
  assert.equal(ui.requests.length, 1);
});
