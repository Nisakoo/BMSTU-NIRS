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
