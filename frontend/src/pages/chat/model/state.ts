import type { AgentApi } from "../../../entities/dialog";
import type { ChatMessage } from "../../../widgets/chat-transcript";

type Dialogs = Awaited<ReturnType<AgentApi["listDialogs"]>>;
type News = Awaited<ReturnType<AgentApi["getReportNews"]>>;
type StatusKind = "connecting" | "processing" | "ready" | "error";

export interface ChatState {
  voice: string;
  user: { login: string; role: string } | null;
  loggingOut: boolean;
  dialogId: string | null;
  title: string;
  messages: ChatMessage[];
  greeting: boolean;
  ready: boolean;
  submitting: boolean;
  processing: boolean;
  switching: boolean;
  status: { text: string; kind: StatusKind };
  dialogs: Dialogs;
  history: "loading" | "loaded" | "failed";
  deletingId: string | null;
  news: News;
}

export const initialState: ChatState = {
  voice: "aidar", user: null, loggingOut: false, dialogId: null, title: "Новая история",
  messages: [], greeting: false, ready: false, submitting: false, processing: false,
  switching: false, status: { text: "подключение…", kind: "connecting" },
  dialogs: [], history: "loading", deletingId: null, news: [],
};

export function busy(state: ChatState) {
  return state.processing || state.submitting || state.switching || state.deletingId !== null;
}

type Action =
  | { type: "session"; user: NonNullable<ChatState["user"]> }
  | { type: "voice"; voice: string }
  | { type: "logout"; pending: boolean }
  | { type: "status"; text: string; kind: StatusKind }
  | { type: "list"; dialogs: Dialogs }
  | { type: "history"; value: ChatState["history"] }
  | { type: "news"; news: News }
  | { type: "deleting"; id: string | null }
  | { type: "removed"; id: string }
  | { type: "switch"; pending: boolean }
  | { type: "story"; id: string | null; title: string | null; messages: ChatMessage[] }
  | { type: "connected"; id: string }
  | { type: "ready" | "disconnected" | "submitting" | "rejected" | "answer-start" }
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
    case "status": return { ...s, status: { text: a.text, kind: a.kind } };
    case "list": return { ...s, dialogs: a.dialogs, history: "loaded" };
    case "history": return { ...s, history: a.value };
    case "news": return { ...s, news: a.news };
    case "deleting": return { ...s, deletingId: a.id };
    case "removed": return { ...s, deletingId: null, dialogs: s.dialogs.filter(d => d.dialogId !== a.id) };
    case "switch": return { ...s, switching: a.pending };
    case "story": return {
      ...s, dialogId: a.id, title: a.title ?? "Новая история", messages: a.messages,
      greeting: a.messages.length === 0, ready: false, processing: false, submitting: false,
    };
    case "connected": return { ...s, dialogId: a.id, switching: false, status: { text: "подключение к потоку…", kind: "connecting" } };
    case "ready": return { ...s, ready: true, status: s.processing
      ? { text: "агент отвечает…", kind: "processing" } : { text: "готов к идеям", kind: "ready" } };
    case "disconnected": return { ...s, ready: false, status: { text: "переподключение…", kind: "connecting" } };
    case "submitting": return { ...s, submitting: true, status: { text: "отправка…", kind: "processing" } };
    case "rejected": return { ...s, submitting: false, status: { text: "не удалось отправить сообщение", kind: "error" } };
    case "accepted": return {
      ...s, submitting: false, processing: true, greeting: false,
      messages: [...s.messages, { role: "user", content: a.text, complete: true }],
      status: s.ready ? { text: "агент отвечает…", kind: "processing" } : s.status,
    };
    case "answer-start": return { ...s, processing: true, greeting: false, messages: answer(s.messages, m => m),
      status: { text: "агент отвечает…", kind: "processing" } };
    case "delta": return { ...s, processing: true, greeting: false, messages: answer(s.messages, m => ({ ...m, content: m.content + a.text })) };
    case "answer-end": {
      const last = s.messages.at(-1);
      const messages = last?.role === "assistant" && !last.complete && !last.error
        ? answer(s.messages, m => ({ ...m, complete: true, id: a.id })) : s.messages;
      return { ...s, processing: false, messages, status: { text: "готов к идеям", kind: "ready" } };
    }
    case "answer-error": return { ...s, processing: false, greeting: false,
      messages: answer(s.messages, m => ({ ...m, error: true, content: (m.content ? m.content + "\n" : "") + "Ошибка ответа" })),
      status: { text: a.text, kind: "error" } };
  }
}
