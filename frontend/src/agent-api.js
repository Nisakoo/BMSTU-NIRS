const EVENT_TYPES = [
  "ready",
  "message_start",
  "message_delta",
  "message_end",
  "message_error",
];

export class AgentApiError extends Error {
  constructor(code) {
    super(code);
    this.name = "AgentApiError";
    this.code = code;
  }
}

export class AgentApi {
  constructor({
    fetchImpl = globalThis.fetch,
    EventSourceImpl = globalThis.EventSource,
  } = {}) {
    if (typeof fetchImpl !== "function") {
      throw new TypeError("fetchImpl must be a function");
    }
    if (typeof EventSourceImpl !== "function") {
      throw new TypeError("EventSourceImpl must be a constructor");
    }
    this.fetchImpl = fetchImpl;
    this.EventSourceImpl = EventSourceImpl;
  }

  async createDialog() {
    let response;
    try {
      response = await this.fetchImpl("/api/v1/dialogs", { method: "POST" });
    } catch {
      throw new AgentApiError("create_failed");
    }
    if (response.status !== 201) {
      throw new AgentApiError("create_failed");
    }

    let body;
    try {
      body = await response.json();
    } catch {
      throw new AgentApiError("invalid_dialog");
    }
    if (typeof body?.dialog_id !== "string" || !body.dialog_id) {
      throw new AgentApiError("invalid_dialog");
    }
    return body.dialog_id;
  }

  async submitMessage(dialogId, request) {
    let response;
    try {
      response = await this.fetchImpl(
        `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ request }),
        },
      );
    } catch {
      throw new AgentApiError("submit_failed");
    }
    if (response.status !== 202) {
      throw new AgentApiError("submit_failed");
    }
  }

  connectEvents(
    dialogId,
    { onEvent, onInvalidEvent, onConnectionError } = {},
  ) {
    const source = new this.EventSourceImpl(
      `/api/v1/dialogs/${encodeURIComponent(dialogId)}/events`,
    );

    for (const type of EVENT_TYPES) {
      source.addEventListener(type, event => {
        let data;
        try {
          data = JSON.parse(event.data);
        } catch {
          onInvalidEvent?.(type);
          return;
        }
        onEvent?.(type, data);
      });
    }
    source.onerror = () => onConnectionError?.();

    return {
      close() {
        source.close();
      },
    };
  }
}
