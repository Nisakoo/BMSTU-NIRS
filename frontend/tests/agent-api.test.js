import assert from "node:assert/strict";
import test from "node:test";

import { AgentApi, AgentApiError } from "../src/agent-api.js";

function response(status, body) {
  return {
    status,
    ok: status >= 200 && status < 300,
    async json() {
      return body;
    },
  };
}

class FakeEventSource {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.listeners = new Map();
    this.onerror = null;
    this.closed = false;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type, data) {
    for (const listener of this.listeners.get(type) || []) {
      listener({ data });
    }
  }

  fail() {
    this.onerror?.();
  }

  close() {
    this.closed = true;
  }
}

test("createDialog posts to the dialog collection and returns dialog_id", async () => {
  const calls = [];
  const api = new AgentApi({
    fetchImpl: async (...args) => {
      calls.push(args);
      return response(201, { dialog_id: "dialog-1" });
    },
    EventSourceImpl: FakeEventSource,
  });

  assert.equal(await api.createDialog(), "dialog-1");
  assert.deepEqual(calls, [["/api/v1/dialogs", { method: "POST" }]]);
});

test("createDialog calls a receiver-sensitive fetch with the global receiver", async () => {
  const api = new AgentApi({
    fetchImpl: async function () {
      assert.equal(this, globalThis);
      return response(201, { dialog_id: "dialog-1" });
    },
    EventSourceImpl: FakeEventSource,
  });

  assert.equal(await api.createDialog(), "dialog-1");
});

test("createDialog rejects unsafe or unsuccessful responses", async () => {
  const missingId = new AgentApi({
    fetchImpl: async () => response(201, {}),
    EventSourceImpl: FakeEventSource,
  });
  const unavailable = new AgentApi({
    fetchImpl: async () => response(503, { detail: "private detail" }),
    EventSourceImpl: FakeEventSource,
  });

  await assert.rejects(
    missingId.createDialog(),
    error => error instanceof AgentApiError && error.code === "invalid_dialog",
  );
  await assert.rejects(
    unavailable.createDialog(),
    error => error instanceof AgentApiError && error.code === "create_failed",
  );
});

test("submitMessage sends the exact dialog request contract", async () => {
  const calls = [];
  const api = new AgentApi({
    fetchImpl: async (...args) => {
      calls.push(args);
      return response(202);
    },
    EventSourceImpl: FakeEventSource,
  });

  await api.submitMessage("dialog/with spaces", "Привет, агент!");

  assert.deepEqual(calls, [[
    "/api/v1/dialogs/dialog%2Fwith%20spaces/messages",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request: "Привет, агент!" }),
    },
  ]]);
});

test("submitMessage calls a receiver-sensitive fetch with the global receiver", async () => {
  const api = new AgentApi({
    fetchImpl: async function () {
      assert.equal(this, globalThis);
      return response(202);
    },
    EventSourceImpl: FakeEventSource,
  });

  await api.submitMessage("dialog-1", "Привет");
});

test("submitMessage rejects a status other than 202", async () => {
  const api = new AgentApi({
    fetchImpl: async () => response(422),
    EventSourceImpl: FakeEventSource,
  });

  await assert.rejects(
    api.submitMessage("dialog-1", "request"),
    error => error instanceof AgentApiError && error.code === "submit_failed",
  );
});

test("a 401 from dialog requests is reported as unauthorized", async () => {
  const api = new AgentApi({
    fetchImpl: async () => response(401, { error: "unauthorized" }),
    EventSourceImpl: FakeEventSource,
  });

  for (const request of [() => api.createDialog(), () => api.submitMessage("dialog-1", "Привет")]) {
    await assert.rejects(
      request(),
      error => error instanceof AgentApiError && error.code === "unauthorized",
    );
  }
});

test("an event connection reports whether the browser closed it", () => {
  FakeEventSource.instances = [];
  const api = new AgentApi({ fetchImpl: async () => response(201), EventSourceImpl: FakeEventSource });
  const connection = api.connectEvents("dialog-1");
  const [source] = FakeEventSource.instances;

  source.readyState = 0;
  assert.equal(connection.isClosed(), false);
  source.readyState = 2;
  assert.equal(connection.isClosed(), true);
});

test("connectEvents parses and dispatches every named SSE event", () => {
  FakeEventSource.instances = [];
  const received = [];
  const api = new AgentApi({
    fetchImpl: async () => response(500),
    EventSourceImpl: FakeEventSource,
  });

  const connection = api.connectEvents("dialog-1", {
    onEvent: (type, data) => received.push([type, data]),
    onInvalidEvent: type => received.push(["invalid", type]),
    onConnectionError: () => received.push(["connection_error", {}]),
  });
  const source = FakeEventSource.instances[0];

  assert.equal(source.url, "/api/v1/dialogs/dialog-1/events");
  source.emit("ready", '{"dialog_id":"dialog-1"}');
  source.emit("message_start", "{}");
  source.emit("message_delta", '{"delta":"Привет"}');
  source.emit("message_end", "{}");
  source.emit("message_error", '{"code":"provider_error","message":"Ошибка"}');
  source.emit("message_delta", "not json");
  source.fail();

  assert.deepEqual(received, [
    ["ready", { dialog_id: "dialog-1" }],
    ["message_start", {}],
    ["message_delta", { delta: "Привет" }],
    ["message_end", {}],
    ["message_error", { code: "provider_error", message: "Ошибка" }],
    ["invalid", "message_delta"],
    ["connection_error", {}],
  ]);

  connection.close();
  assert.equal(source.closed, true);
});

function apiWith(handler) {
  const calls = [];
  const api = new AgentApi({
    fetchImpl: async (...args) => {
      calls.push(args);
      return handler(...args);
    },
    EventSourceImpl: FakeEventSource,
  });
  return { api, calls };
}

async function rejectsWith(promise, code) {
  await assert.rejects(promise, error => error instanceof AgentApiError && error.code === code);
}

test("listDialogs reads the dialog collection into summaries", async () => {
  const { api, calls } = apiWith(() => response(200, {
    dialogs: [
      { dialog_id: "d-2", title: "Ракета", created_at: "2026-10-17T10:00:00Z", updated_at: "2026-10-17T11:00:00Z" },
      { dialog_id: "d-1", title: null, created_at: "2026-10-16T10:00:00Z", updated_at: "2026-10-16T10:00:00Z" },
    ],
  }));

  assert.deepEqual(await api.listDialogs(), [
    { dialogId: "d-2", title: "Ракета", updatedAt: "2026-10-17T11:00:00Z" },
    { dialogId: "d-1", title: null, updatedAt: "2026-10-16T10:00:00Z" },
  ]);
  assert.deepEqual(calls, [["/api/v1/dialogs"]]);
});

test("getMessages reads an encoded dialog history", async () => {
  const { api, calls } = apiWith(() => response(200, {
    dialog_id: "a/b",
    title: "Ракета",
    messages: [
      { id: 1, role: "user", content: "Крош", created_at: "2026-10-17T10:00:00Z", feedback: null, reported: false, report: null },
      { id: 2, role: "assistant", content: "Однажды…", created_at: "2026-10-17T10:00:01Z", feedback: 5, reported: true, report: "sent" },
      { id: 3, role: "assistant", content: "Потом…", created_at: "2026-10-17T10:00:02Z", feedback: null, reported: true, report: "reviewed" },
      { id: 4, role: "assistant", content: "Ещё…", created_at: "2026-10-17T10:00:03Z", feedback: null },
    ],
  }));

  assert.deepEqual(await api.getMessages("a/b"), {
    title: "Ракета",
    messages: [
      { id: 1, role: "user", content: "Крош", feedback: null, report: null },
      { id: 2, role: "assistant", content: "Однажды…", feedback: 5, report: "sent" },
      { id: 3, role: "assistant", content: "Потом…", feedback: null, report: "reviewed" },
      { id: 4, role: "assistant", content: "Ещё…", feedback: null, report: null },
    ],
  });
  assert.deepEqual(calls, [["/api/v1/dialogs/a%2Fb/messages"]]);
});

test("history requests map statuses to error codes", async () => {
  const cases = [[401, "unauthorized"], [404, "not_found"], [503, "load_failed"], [500, "load_failed"]];
  for (const [status, code] of cases) {
    const { api } = apiWith(() => response(status, { detail: "private" }));
    await rejectsWith(api.listDialogs(), status === 404 ? "load_failed" : code);
    await rejectsWith(api.getMessages("d-1"), code);
  }
  const offline = apiWith(() => { throw new TypeError("offline"); }).api;
  await rejectsWith(offline.listDialogs(), "load_failed");
  await rejectsWith(offline.getMessages("d-1"), "load_failed");
});

test("history requests reject malformed bodies", async () => {
  const bodies = [
    null,
    { dialogs: "nope" },
    { dialogs: [{ dialog_id: "", title: null, updated_at: "x" }] },
    { dialogs: [{ dialog_id: "d", title: 5, updated_at: "x" }] },
  ];
  for (const body of bodies) {
    await rejectsWith(apiWith(() => response(200, body)).api.listDialogs(), "invalid_response");
  }
  const transcripts = [
    null,
    { title: null, messages: "nope" },
    { title: null, messages: [{ id: 1, role: "tool", content: "x", feedback: null }] },
    { title: null, messages: [{ id: 1, role: "user", content: 5, feedback: null }] },
    { title: null, messages: [{ id: "1", role: "user", content: "x", feedback: null }] },
    { title: null, messages: [{ id: 1.5, role: "user", content: "x", feedback: null }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: "like" }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: 0 }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: 6 }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: 2.5 }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: true }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: null, reported: "yes" }] },
    { title: null, messages: [{ id: 1, role: "assistant", content: "x", feedback: null, report: "dismissed" }] },
    { title: 7, messages: [] },
  ];
  for (const body of transcripts) {
    await rejectsWith(apiWith(() => response(200, body)).api.getMessages("d"), "invalid_response");
  }
  const broken = apiWith(() => ({ status: 200, async json() { throw new SyntaxError("bad"); } })).api;
  await rejectsWith(broken.listDialogs(), "invalid_response");
});

test("submitMessage adds the reading time only when it is chosen", async () => {
  const { api, calls } = apiWith(() => response(202));

  await api.submitMessage("d-1", "Крош", { readingMinutes: 5 });
  await api.submitMessage("d-1", "Крош", { readingMinutes: null });
  await api.submitMessage("d-1", "Крош");

  assert.deepEqual(calls.map(([, init]) => JSON.parse(init.body)), [
    { request: "Крош", reading_minutes: 5 },
    { request: "Крош" },
    { request: "Крош" },
  ]);
});

test("feedback is put or deleted for an encoded answer", async () => {
  const { api, calls } = apiWith(() => response(204));

  await api.setFeedback("a/b", 7, 5);
  await api.setFeedback("a/b", 7, 1);
  await api.clearFeedback("a/b", 7);

  assert.deepEqual(calls, [
    ["/api/v1/dialogs/a%2Fb/messages/7/feedback", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score: 5 }),
    }],
    ["/api/v1/dialogs/a%2Fb/messages/7/feedback", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score: 1 }),
    }],
    ["/api/v1/dialogs/a%2Fb/messages/7/feedback", { method: "DELETE" }],
  ]);
});

test("feedback requests map statuses to error codes", async () => {
  for (const [status, code] of [[401, "unauthorized"], [404, "not_found"], [503, "feedback_failed"], [200, "feedback_failed"]]) {
    const { api } = apiWith(() => response(status));
    await rejectsWith(api.setFeedback("d", 1, 3), code);
    await rejectsWith(api.clearFeedback("d", 1), code);
  }
  const offline = apiWith(() => { throw new TypeError("offline"); }).api;
  await rejectsWith(offline.setFeedback("d", 1, 3), "feedback_failed");
});

test("a dialog is deleted by its encoded id", async () => {
  const { api, calls } = apiWith(() => response(204));

  await api.deleteDialog("a/b");

  assert.deepEqual(calls, [["/api/v1/dialogs/a%2Fb", { method: "DELETE" }]]);
});

test("deleting a dialog maps statuses to error codes", async () => {
  for (const [status, code] of [[401, "unauthorized"], [404, "not_found"], [503, "delete_failed"], [200, "delete_failed"]]) {
    const { api } = apiWith(() => response(status));
    await rejectsWith(api.deleteDialog("d"), code);
  }
  const offline = apiWith(() => { throw new TypeError("offline"); }).api;
  await rejectsWith(offline.deleteDialog("d"), "delete_failed");
});

test("a report is posted for an encoded answer, with or without a comment", async () => {
  const { api, calls } = apiWith(() => response(201, { report_id: 3 }));

  await api.reportMessage("a/b", 7, "scary", "Страшно");
  await api.reportMessage("a/b", 7, "other", "");

  assert.deepEqual(calls, [
    ["/api/v1/dialogs/a%2Fb/messages/7/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "scary", comment: "Страшно" }),
    }],
    ["/api/v1/dialogs/a%2Fb/messages/7/report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason: "other" }),
    }],
  ]);
});

test("an answer reported before counts as reported", async () => {
  const { api } = apiWith(() => response(409, { detail: "Already reported." }));

  await api.reportMessage("d", 1, "rude", "");
});

test("report requests map statuses to error codes", async () => {
  for (const [status, code] of [[401, "unauthorized"], [404, "not_found"], [422, "report_failed"], [503, "report_failed"], [200, "report_failed"]]) {
    const { api } = apiWith(() => response(status));
    await rejectsWith(api.reportMessage("d", 1, "rude", ""), code);
  }
  const offline = apiWith(() => { throw new TypeError("offline"); }).api;
  await rejectsWith(offline.reportMessage("d", 1, "rude", ""), "report_failed");
});

test("report news are read as story references", async () => {
  const { api, calls } = apiWith(() => response(200, {
    news: [
      { report_id: 3, dialog_id: "d-1", dialog_title: "Ракета" },
      { report_id: 2, dialog_id: null, dialog_title: null },
    ],
  }));

  assert.deepEqual(await api.getReportNews(), [
    { reportId: 3, dialogId: "d-1", dialogTitle: "Ракета" },
    { reportId: 2, dialogId: null, dialogTitle: null },
  ]);
  assert.deepEqual(calls, [["/api/v1/reports/news"]]);
});

test("malformed report news are rejected", async () => {
  for (const body of [
    null,
    { news: "nope" },
    { news: [{ report_id: "3", dialog_id: null, dialog_title: null }] },
    { news: [{ report_id: 3, dialog_id: 5, dialog_title: null }] },
    { news: [{ report_id: 3, dialog_id: null, dialog_title: 7 }] },
  ]) {
    await rejectsWith(apiWith(() => response(200, body)).api.getReportNews(), "invalid_response");
  }
  await rejectsWith(apiWith(() => response(401)).api.getReportNews(), "unauthorized");
  await rejectsWith(apiWith(() => response(503)).api.getReportNews(), "load_failed");
});

test("seen report news are posted by id", async () => {
  const { api, calls } = apiWith(() => response(204));

  await api.markReportNewsSeen([3, 2]);

  assert.deepEqual(calls, [["/api/v1/reports/news/seen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_ids: [3, 2] }),
  }]]);
  for (const [status, code] of [[401, "unauthorized"], [422, "news_failed"], [503, "news_failed"]]) {
    await rejectsWith(apiWith(() => response(status)).api.markReportNewsSeen([1]), code);
  }
  await rejectsWith(apiWith(() => { throw new TypeError("offline"); }).api.markReportNewsSeen([1]), "news_failed");
});
