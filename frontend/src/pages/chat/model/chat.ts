import type { AgentApi, DialogEventType } from "../../../entities/dialog";
import { type AuthApi, LOGIN_PATH, SESSION, checkSession, errorCode, refreshSession, type PasswordChange } from "../../../entities/session";
import { createStore } from "../../../shared/lib/store";
import type { MessageActions } from "../../../widgets/chat-transcript";
import { readVoice, saveVoice } from "./options";
import { busy, initialState, reduceChat } from "./state";

export function createChat(api: AgentApi, auth: AuthApi, navigate: (url: string) => void) {
  const store = createStore({ ...initialState, voice: readVoice() }, reduceChat);
  const { dispatch, getState } = store;
  let disposed = false;
  let connection: ReturnType<AgentApi["connectEvents"]> | null = null;
  let generation = 0;
  let historyRequest = 0;
  let reopened = false;
  let checking: ReturnType<AgentApi["connectEvents"]> | null = null;
  let retryTimer: number | undefined;
  let buffer: [DialogEventType, unknown][] = [];

  function stopStream() {
    generation++;
    connection?.close();
    connection = null;
    buffer = [];
    reopened = false;
  }

  function destroy() {
    disposed = true;
    window.clearTimeout(retryTimer);
    stopStream();
  }

  function login() {
    if (disposed) return;
    destroy();
    navigate(LOGIN_PATH);
  }

  function retry(action: () => Promise<void>) {
    window.clearTimeout(retryTimer);
    retryTimer = window.setTimeout(() => {
      if (disposed) return;
      // A history operation can still be in flight when a creation retry is due.
      if (busy(getState())) retry(action);
      else void action();
    }, 3000);
  }

  function notify(text: string, kind: "ready" | "error" | "connecting" = "ready") {
    if (!disposed) dispatch({ type: "status", text, kind });
  }

  async function withSession<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (errorCode(error) !== "unauthorized" || disposed) throw error;
    }
    const result = await refreshSession(auth);
    if (result.status === SESSION.ANONYMOUS) login();
    if (result.status !== SESSION.USER || disposed) throw new Error("session unavailable");
    try {
      return await operation();
    } catch (error) {
      if (errorCode(error) === "unauthorized") login();
      throw error;
    }
  }

  async function list() {
    const request = ++historyRequest;
    if (getState().history === "failed") dispatch({ type: "history", value: "loading" });
    try {
      const dialogs = await withSession(() => api.listDialogs());
      if (!disposed && request === historyRequest) dispatch({ type: "list", dialogs });
    } catch {
      if (!disposed && request === historyRequest) dispatch({ type: "history", value: "failed" });
    }
  }

  function receive(type: DialogEventType, payload: unknown) {
    if (type === "ready") {
      reopened = false;
      dispatch({ type: "ready" });
      return;
    }
    if (getState().submitting) {
      buffer.push([type, payload]);
      return;
    }
    const data = payload && typeof payload === "object" ? payload : {};
    switch (type) {
      case "message_start": dispatch({ type: "answer-start" }); break;
      case "message_delta":
        if ("delta" in data && typeof data.delta === "string") dispatch({ type: "delta", text: data.delta });
        else notify("некорректное событие от сервера", "error");
        break;
      case "message_end":
        dispatch({ type: "answer-end", id: "message_id" in data && typeof data.message_id === "number" && Number.isInteger(data.message_id) ? data.message_id : undefined });
        void list();
        break;
      case "message_error":
        dispatch({ type: "answer-error", text: "message" in data && typeof data.message === "string" ? data.message : "ошибка агента" });
        break;
    }
  }

  async function checkConnection(id: string) {
    const stream = connection;
    if (!stream || checking === stream || disposed) return;
    checking = stream;
    const session = await checkSession(auth);
    if (checking === stream) checking = null;
    if (disposed || connection !== stream) return;
    if (session.status === SESSION.ANONYMOUS) return login();
    if (session.status !== SESSION.USER || !stream.isClosed()) return;
    if (reopened) return notify("соединение потеряно; обновите страницу", "error");
    reopened = true;
    connect(id, true);
  }

  function connect(id: string, reconnect = false) {
    const version = ++generation;
    if (!reconnect) dispatch({ type: "connected", id });
    connection = api.connectEvents(id, {
      onEvent: (type, data) => { if (version === generation) receive(type, data); },
      onInvalidEvent: () => { if (version === generation) notify("некорректное событие от сервера", "error"); },
      onConnectionError: () => {
        if (version !== generation) return;
        dispatch({ type: "disconnected" });
        void checkConnection(id);
      },
    });
  }

  async function create() {
    if (disposed || !getState().user || busy(getState())) return;
    window.clearTimeout(retryTimer);
    stopStream();
    dispatch({ type: "story", id: null, title: null, messages: [] });
    dispatch({ type: "switch", pending: true });
    notify("создание диалога…", "connecting");
    try {
      const id = await withSession(() => api.createDialog());
      if (!disposed) connect(id);
    } catch {
      if (disposed) return;
      dispatch({ type: "switch", pending: false });
      notify("backend недоступен; повторная попытка…", "error");
      retry(create);
    }
  }

  async function open(id: string) {
    if (disposed || busy(getState()) || getState().dialogId === id) return;
    dispatch({ type: "switch", pending: true });
    notify("загрузка истории…", "connecting");
    try {
      const story = await withSession(() => api.getMessages(id));
      if (disposed) return;
      window.clearTimeout(retryTimer);
      stopStream();
      dispatch({ type: "story", id, title: story.title, messages: story.messages.map(m => ({ ...m, complete: true })) });
      connect(id);
    } catch (error) {
      if (disposed) return;
      dispatch({ type: "switch", pending: false });
      const missing = errorCode(error) === "not_found";
      notify(missing ? "история не найдена" : "не удалось открыть историю", "error");
      if (missing) void list();
    }
  }

  async function remove(id: string) {
    if (disposed || busy(getState())) return;
    dispatch({ type: "deleting", id });
    try {
      await withSession(() => api.deleteDialog(id));
    } catch (error) {
      if (disposed) return;
      if (errorCode(error) !== "not_found") {
        dispatch({ type: "deleting", id: null });
        return notify("Не удалось удалить историю", "error");
      }
    }
    if (disposed) return;
    ++historyRequest;
    dispatch({ type: "removed", id });
    if (getState().dialogId === id) await create();
  }

  async function submit(draft: string, readingMinutes: number | null) {
    const request = draft.trim();
    const s = getState();
    const id = s.dialogId;
    if (!request || !id || !s.ready || busy(s) || disposed) return false;
    dispatch({ type: "submitting" });
    buffer = [];
    try {
      await withSession(() => api.submitMessage(id, request, { readingMinutes }));
      if (disposed) return false;
      dispatch({ type: "accepted", text: request });
      const queued = buffer;
      buffer = [];
      for (const [type, data] of queued) receive(type, data);
      return true;
    } catch {
      buffer = [];
      if (!disposed) dispatch({ type: "rejected" });
      return false;
    }
  }

  async function readNews() {
    try {
      const news = await withSession(() => api.getReportNews());
      if (!disposed) dispatch({ type: "news", news });
    } catch { /* A later visit fetches unacknowledged notices again. */ }
  }

  function dismissNews() {
    const ids = getState().news.map(item => item.reportId);
    dispatch({ type: "news", news: [] });
    void withSession(() => api.markReportNewsSeen(ids)).catch(() => {});
  }

  async function start() {
    notify("проверка входа…", "connecting");
    const session = await checkSession(auth);
    if (disposed) return;
    if (session.status === SESSION.ANONYMOUS) return login();
    if (session.status === SESSION.UNAVAILABLE) {
      notify("backend недоступен; повторная попытка…", "error");
      return retry(start);
    }
    dispatch({ type: "session", user: session.user });
    void list();
    await create();
    if (!disposed) void readNews();
  }

  async function logout() {
    if (getState().loggingOut) return;
    dispatch({ type: "logout", pending: true });
    try {
      await auth.logout();
      login();
    } catch {
      dispatch({ type: "logout", pending: false });
      notify("Не удалось выйти. Попробуйте ещё раз", "error");
    }
  }

  function actions(id: string): MessageActions {
    return {
      rate: (msg, score) => withSession(() => score === null ? api.clearFeedback(id, msg) : api.setFeedback(id, msg, score)),
      report: (msg, reason, comment) => withSession(() => api.reportMessage(id, msg, reason, comment)),
      startAudio: (msg, voice) => withSession(() => api.startAudio(id, msg, voice)),
      getAudio: (msg, voice) => withSession(() => api.getAudio(id, msg, voice)),
      downloadAudio: (msg, voice) => withSession(() => api.downloadAudio(id, msg, voice)),
      notify: (text, kind) => { if (getState().dialogId === id) notify(text, kind); },
    };
  }

  function chooseVoice(voice: string) {
    dispatch({ type: "voice", voice });
    saveVoice(voice);
  }

  return { store, chooseVoice, start, destroy, list, open, create, remove, submit, logout, dismissNews, actions,
    isUnloading: () => disposed,
    changePassword: (values: PasswordChange) => withSession(() => auth.changePassword(values)) };
}
