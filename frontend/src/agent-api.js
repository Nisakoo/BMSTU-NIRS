const EVENT_SOURCE_CLOSED = 2;

const EVENT_TYPES = [
  "ready",
  "message_start",
  "message_delta",
  "message_end",
  "message_error",
];

const MESSAGE_ROLES = new Set(["user", "assistant"]);
const MIN_SCORE = 1;
const MAX_SCORE = 5;

function isScore(value) {
  return Number.isInteger(value) && value >= MIN_SCORE && value <= MAX_SCORE;
}

function isTitle(value) {
  return value === null || typeof value === "string";
}

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
    this.fetchImpl = fetchImpl.bind(globalThis);
    this.EventSourceImpl = EventSourceImpl;
  }

  async createDialog() {
    let response;
    try {
      response = await this.fetchImpl("/api/v1/dialogs", { method: "POST" });
    } catch {
      throw new AgentApiError("create_failed");
    }
    if (response.status === 401) {
      throw new AgentApiError("unauthorized");
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

  async submitMessage(dialogId, request, { readingMinutes = null } = {}) {
    const body = readingMinutes === null
      ? { request }
      : { request, reading_minutes: readingMinutes };
    let response;
    try {
      response = await this.fetchImpl(
        `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
    } catch {
      throw new AgentApiError("submit_failed");
    }
    if (response.status === 401) {
      throw new AgentApiError("unauthorized");
    }
    if (response.status !== 202) {
      throw new AgentApiError("submit_failed");
    }
  }

  async listDialogs() {
    const body = await this.#readJson("/api/v1/dialogs", { notFound: false });
    if (!Array.isArray(body?.dialogs)) throw new AgentApiError("invalid_response");
    return body.dialogs.map(item => {
      if (typeof item?.dialog_id !== "string" || !item.dialog_id
        || !isTitle(item.title) || typeof item.updated_at !== "string") {
        throw new AgentApiError("invalid_response");
      }
      return { dialogId: item.dialog_id, title: item.title, updatedAt: item.updated_at };
    });
  }

  async getMessages(dialogId) {
    const body = await this.#readJson(
      `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages`,
      { notFound: true },
    );
    if (!isTitle(body?.title) || !Array.isArray(body.messages)) {
      throw new AgentApiError("invalid_response");
    }
    return {
      title: body.title,
      messages: body.messages.map(item => {
        if (!Number.isInteger(item?.id) || !MESSAGE_ROLES.has(item.role)
          || typeof item.content !== "string"
          || !(item.feedback === null || isScore(item.feedback))) {
          throw new AgentApiError("invalid_response");
        }
        return { id: item.id, role: item.role, content: item.content, feedback: item.feedback };
      }),
    };
  }

  async setFeedback(dialogId, messageId, score) {
    await this.#sendFeedback(dialogId, messageId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score }),
    });
  }

  async clearFeedback(dialogId, messageId) {
    await this.#sendFeedback(dialogId, messageId, { method: "DELETE" });
  }

  async #sendFeedback(dialogId, messageId, init) {
    let response;
    try {
      response = await this.fetchImpl(
        `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages/${encodeURIComponent(messageId)}/feedback`,
        init,
      );
    } catch {
      throw new AgentApiError("feedback_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status === 404) throw new AgentApiError("not_found");
    if (response.status !== 204) throw new AgentApiError("feedback_failed");
  }

  async #readJson(url, { notFound }) {
    let response;
    try {
      response = await this.fetchImpl(url);
    } catch {
      throw new AgentApiError("load_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (notFound && response.status === 404) throw new AgentApiError("not_found");
    if (response.status !== 200) throw new AgentApiError("load_failed");
    try {
      return await response.json();
    } catch {
      throw new AgentApiError("invalid_response");
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
      // A closed source will not reconnect by itself, e.g. after a 401.
      isClosed() {
        return source.readyState === EVENT_SOURCE_CLOSED;
      },
    };
  }
}
