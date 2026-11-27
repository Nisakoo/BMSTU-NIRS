import type { DialogSummary, DialogMessage, DialogEventType, ReportNewsItem } from "./model";

const EVENT_SOURCE_CLOSED = 2;

const EVENT_TYPES: DialogEventType[] = [
  "ready",
  "message_start",
  "message_delta",
  "message_end",
  "message_error",
];

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value);
}

function isScore(value: unknown): value is number {
  return isInteger(value) && value >= 1 && value <= 5;
}

function isTitle(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isReport(value: unknown): value is DialogMessage["report"] | undefined {
  return value === undefined || value === null || value === "sent" || value === "reviewed";
}

function isVoiceList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(voice => typeof voice === "string");
}

export function audioUrl(dialogId: string, messageId: number | string, voice: string | null = null) {
  const base = `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages/${encodeURIComponent(messageId)}/audio`;
  return voice === null ? base : `${base}?voice=${encodeURIComponent(voice)}`;
}

export class AgentApiError extends Error {
  readonly code: string;

  constructor(code: string) {
    super(code);
    this.name = "AgentApiError";
    this.code = code;
  }
}

export class AgentApi {
  private readonly fetchImpl: typeof fetch;
  private readonly EventSourceImpl: typeof EventSource;

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

  async createDialog(): Promise<string> {
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

    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new AgentApiError("invalid_dialog");
    }
    if (!isObject(body) || typeof body.dialog_id !== "string" || !body.dialog_id) {
      throw new AgentApiError("invalid_dialog");
    }
    return body.dialog_id;
  }

  async submitMessage(dialogId: string, request: string, { readingMinutes = null }: { readingMinutes?: number | null } = {}) {
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

  async listDialogs(): Promise<DialogSummary[]> {
    const body = await this.#readJson("/api/v1/dialogs", { notFound: false });
    if (!isObject(body) || !Array.isArray(body.dialogs)) throw new AgentApiError("invalid_response");
    return body.dialogs.map((item: unknown) => {
      if (!isObject(item) || typeof item.dialog_id !== "string" || !item.dialog_id
        || !isTitle(item.title) || typeof item.updated_at !== "string") {
        throw new AgentApiError("invalid_response");
      }
      return { dialogId: item.dialog_id, title: item.title, updatedAt: item.updated_at };
    });
  }

  async getMessages(dialogId: string): Promise<{ title: string | null; messages: DialogMessage[] }> {
    const body = await this.#readJson(
      `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages`,
      { notFound: true },
    );
    if (!isObject(body) || !isTitle(body.title) || !Array.isArray(body.messages)) {
      throw new AgentApiError("invalid_response");
    }
    return {
      title: body.title,
      messages: body.messages.map((item: unknown) => {
        if (!isObject(item) || !isInteger(item.id) || (item.role !== "user" && item.role !== "assistant")
          || typeof item.content !== "string"
          || !(item.feedback === null || isScore(item.feedback))
          || !(item.reported === undefined || typeof item.reported === "boolean")
          || !isReport(item.report)
          || !(item.audio_voices === undefined || isVoiceList(item.audio_voices))) {
          throw new AgentApiError("invalid_response");
        }
        return {
          id: item.id,
          role: item.role,
          content: item.content,
          feedback: item.feedback,
          report: item.report ?? (item.reported === true ? "sent" : null),
          audioVoices: item.audio_voices ?? [],
        };
      }),
    };
  }

  async deleteDialog(dialogId: string) {
    let response;
    try {
      response = await this.fetchImpl(`/api/v1/dialogs/${encodeURIComponent(dialogId)}`, { method: "DELETE" });
    } catch {
      throw new AgentApiError("delete_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status === 404) throw new AgentApiError("not_found");
    if (response.status !== 204) throw new AgentApiError("delete_failed");
  }

  async setFeedback(dialogId: string, messageId: number, score: number) {
    await this.#sendFeedback(dialogId, messageId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score }),
    });
  }

  async clearFeedback(dialogId: string, messageId: number) {
    await this.#sendFeedback(dialogId, messageId, { method: "DELETE" });
  }

  async getReportNews(): Promise<ReportNewsItem[]> {
    const body = await this.#readJson("/api/v1/reports/news", { notFound: false });
    if (!isObject(body) || !Array.isArray(body.news)) throw new AgentApiError("invalid_response");
    return body.news.map((item: unknown) => {
      if (!isObject(item) || !isInteger(item.report_id)
        || !(item.dialog_id === null || typeof item.dialog_id === "string")
        || !isTitle(item.dialog_title)) {
        throw new AgentApiError("invalid_response");
      }
      return { reportId: item.report_id, dialogId: item.dialog_id, dialogTitle: item.dialog_title };
    });
  }

  async startAudio(dialogId: string, messageId: number | string, voice: string | null = null) {
    const init = voice === null
      ? { method: "POST" }
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ voice }),
        };
    let response;
    try {
      response = await this.fetchImpl(audioUrl(dialogId, messageId), init);
    } catch {
      throw new AgentApiError("audio_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status === 404) throw new AgentApiError("not_found");
    if (response.status === 422) throw new AgentApiError("invalid_voice");
    if (response.status === 503) throw new AgentApiError("audio_unavailable");
    if (response.status !== 200 && response.status !== 202) {
      throw new AgentApiError("audio_failed");
    }
    let body: unknown;
    try {
      body = await response.json();
    } catch {
      throw new AgentApiError("invalid_response");
    }
    if (!isObject(body) || (body.status !== "pending" && body.status !== "ready")) {
      throw new AgentApiError("invalid_response");
    }
    return body.status;
  }

  async getAudio(dialogId: string, messageId: number | string, voice: string | null = null): Promise<{ status: "pending" } | { status: "ready"; blob: Blob }> {
    let response;
    try {
      response = await this.fetchImpl(audioUrl(dialogId, messageId, voice));
    } catch {
      throw new AgentApiError("audio_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status === 404) throw new AgentApiError("not_found");
    if (response.status === 422) throw new AgentApiError("invalid_voice");
    if (response.status === 503) throw new AgentApiError("audio_unavailable");
    if (response.status === 202) return { status: "pending" };
    if (response.status !== 200 || typeof response.blob !== "function") {
      throw new AgentApiError("audio_failed");
    }
    try {
      return { status: "ready", blob: await response.blob() };
    } catch {
      throw new AgentApiError("invalid_response");
    }
  }

  async downloadAudio(dialogId: string, messageId: number | string, voice: string | null = null) {
    const url = audioUrl(dialogId, messageId, voice);
    const separator = voice === null ? "?" : "&";
    let response;
    try {
      response = await this.fetchImpl(`${url}${separator}download=1`);
    } catch {
      throw new AgentApiError("audio_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status === 404) throw new AgentApiError("not_found");
    if (response.status === 422) throw new AgentApiError("invalid_voice");
    if (response.status === 503) throw new AgentApiError("audio_unavailable");
    if (response.status !== 200 || typeof response.blob !== "function") {
      throw new AgentApiError("audio_failed");
    }
    try {
      return await response.blob();
    } catch {
      throw new AgentApiError("invalid_response");
    }
  }

  async markReportNewsSeen(reportIds: number[]) {
    let response;
    try {
      response = await this.fetchImpl("/api/v1/reports/news/seen", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ report_ids: reportIds }),
      });
    } catch {
      throw new AgentApiError("news_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status !== 204) throw new AgentApiError("news_failed");
  }

  // An answer reported before (409) is just as reported: the first report stays.
  async reportMessage(dialogId: string, messageId: number, reason: string, comment: string) {
    const body = comment ? { reason, comment } : { reason };
    let response;
    try {
      response = await this.fetchImpl(
        `/api/v1/dialogs/${encodeURIComponent(dialogId)}/messages/${encodeURIComponent(messageId)}/report`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
      );
    } catch {
      throw new AgentApiError("report_failed");
    }
    if (response.status === 401) throw new AgentApiError("unauthorized");
    if (response.status === 404) throw new AgentApiError("not_found");
    if (response.status !== 201 && response.status !== 409) throw new AgentApiError("report_failed");
  }

  async #sendFeedback(dialogId: string, messageId: number, init: RequestInit) {
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

  async #readJson(url: string, { notFound }: { notFound: boolean }): Promise<unknown> {
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
    dialogId: string,
    { onEvent, onInvalidEvent, onConnectionError }: {
      onEvent?: (type: DialogEventType, data: unknown) => void;
      onInvalidEvent?: (type: DialogEventType) => void;
      onConnectionError?: () => void;
    } = {},
  ) {
    const source = new this.EventSourceImpl(
      `/api/v1/dialogs/${encodeURIComponent(dialogId)}/events`,
    );

    for (const type of EVENT_TYPES) {
      source.addEventListener(type, (event: MessageEvent<string>) => {
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
