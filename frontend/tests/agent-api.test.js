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
      { id: 1, role: "user", content: "Крош", created_at: "2026-10-17T10:00:00Z", feedback: null },
      { id: 2, role: "assistant", content: "Однажды…", created_at: "2026-10-17T10:00:01Z", feedback: 5 },
    ],
  }));

  assert.deepEqual(await api.getMessages("a/b"), {
    title: "Ракета",
    messages: [
      { id: 1, role: "user", content: "Крош", feedback: null },
      { id: 2, role: "assistant", content: "Однажды…", feedback: 5 },
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
