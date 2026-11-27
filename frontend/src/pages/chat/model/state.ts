import type { User } from "../../../entities/session";
import type { AgentApi } from "../../../entities/dialog";
import type { ChatMessage } from "../../../widgets/chat-transcript";

type Dialogs = Awaited<ReturnType<AgentApi["listDialogs"]>>;
type News = Awaited<ReturnType<AgentApi["getReportNews"]>>;
type NoticeKind = "info" | "error";

export interface ChatState {
  voice: string;
  user: User | null;
  loggingOut: boolean;
  dialogId: string | null;
  title: string;
  messages: ChatMessage[];
  greeting: boolean;
  ready: boolean;
  submitting: boolean;
  processing: boolean;
  switching: boolean;
  hydrating: boolean;
  notice: { text: string; kind: NoticeKind } | null;
  dialogs: Dialogs;
  history: "loading" | "loaded" | "failed";
  deletingId: string | null;
  news: News;
}

export const initialState: ChatState = {
  voice: "aidar", user: null, loggingOut: false, dialogId: null, title: "Новая история",
  messages: [], greeting: false, ready: false, submitting: false, processing: false,
  hydrating: false, switching: false, notice: null,
  dialogs: [], history: "loading", deletingId: null, news: [],
};

export function busy(state: ChatState) {
  return state.hydrating || state.processing || state.submitting || state.switching || state.deletingId !== null;
}

type Action =
  | { type: "session"; user: NonNullable<ChatState["user"]> }
  | { type: "voice"; voice: string }
  | { type: "logout"; pending: boolean }
  | { type: "notice"; text: string; kind: NoticeKind }
  | { type: "list"; dialogs: Dialogs }
  | { type: "history"; value: ChatState["history"] }
  | { type: "news"; news: News }
  | { type: "deleting"; id: string | null }
  | { type: "removed"; id: string }
  | { type: "switch"; pending: boolean }
  | { type: "story"; id: string | null; title: string | null; messages: ChatMessage[] }
  | { type: "hydrate"; pending: boolean }
  | { type: "remote-run"; active: boolean }
  | { type: "snapshot"; title: string | null; messages: ChatMessage[] }
  | { type: "connected"; id: string }
  | { type: "ready" | "disconnected" | "submitting" | "rejected" | "answer-start" | "closed" }
  | { type: "accepted" | "delta" | "answer-error"; text: string }
  | { type: "answer-end"; id?: number };

function answer(messages: ChatMessage[], update: (message: ChatMessage) => ChatMessage) {
  const last = messages.at(-1);
  if (last?.role === "assistant" && !last.complete && !last.error) {
    return [...messages.slice(0, -1), update(last)];
  }
  return [...messages, update({ role: "assistant", complete: false, content: "" })];
}

export function reduceChat(s: ChatState, a: Action): ChatState {
  switch (a.type) {
    case "session": return { ...s, user: a.user };
    case "voice": return { ...s, voice: a.voice };
    case "logout": return { ...s, loggingOut: a.pending };
    case "notice": return { ...s, notice: { text: a.text, kind: a.kind } };
    case "closed": return { ...s, ready: false, processing: false, submitting: false, notice: null };
    case "list": return { ...s, dialogs: a.dialogs, history: "loaded" };
    case "history": return { ...s, history: a.value };
    case "news": return { ...s, news: a.news };
    case "deleting": return { ...s, deletingId: a.id };
    case "removed": return { ...s, deletingId: null, dialogs: s.dialogs.filter(d => d.dialogId !== a.id) };
    case "switch": return { ...s, switching: a.pending };
    case "hydrate": return { ...s, hydrating: a.pending };
    case "remote-run": return { ...s, processing: a.active };
    case "snapshot": return {
      ...s, title: a.title ?? "Новая история", messages: a.messages, greeting: a.messages.length === 0,
    };
    case "story": return {
      ...s, dialogId: a.id, title: a.title ?? "Новая история", messages: a.messages,
      greeting: a.messages.length === 0, hydrating: false, ready: false, processing: false, submitting: false,
    };
    case "connected": return { ...s, dialogId: a.id, switching: false, notice: null };
    case "ready": return { ...s, ready: true, notice: null };
    case "disconnected": return { ...s, ready: false, notice: { text: "Соединение прервалось. Пробуем снова…", kind: "info" } };
    case "submitting": return { ...s, submitting: true, notice: null };
    case "rejected": return { ...s, submitting: false, notice: { text: "Не удалось отправить сообщение. Попробуйте ещё раз", kind: "error" } };
    case "accepted": return {
      ...s, submitting: false, processing: true, greeting: false,
      messages: [...s.messages, { role: "user", content: a.text, complete: true }],
      notice: s.ready ? null : s.notice,
    };
    case "answer-start": return { ...s, processing: true, greeting: false, messages: answer(s.messages, m => m) };
    case "delta": return { ...s, processing: true, greeting: false, messages: answer(s.messages, m => ({ ...m, content: m.content + a.text })) };
    case "answer-end": {
      const last = s.messages.at(-1);
      const messages = last?.role === "assistant" && !last.complete && !last.error
        ? answer(s.messages, m => ({ ...m, complete: true, id: a.id })) : s.messages;
      return { ...s, processing: false, messages };
    }
    case "answer-error": return { ...s, processing: false, greeting: false,
      messages: answer(s.messages, m => ({ ...m, error: true, content: (m.content ? m.content + "\n" : "") + "Ошибка ответа" })),
      notice: { text: a.text, kind: "error" } };
  }
}
