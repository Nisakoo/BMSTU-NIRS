import type { AgentApi, DialogEventType } from "../../../entities/dialog";
import { type AuthApi, LOGIN_PATH, SESSION, checkSession, errorCode, refreshSession, type PasswordChange } from "../../../entities/session";
import { createStore } from "../../../shared/lib/store";
import type { MessageActions } from "../../../widgets/chat-transcript";
import { readVoice, saveVoice } from "./options";
import { selectedDialog, rememberDialog, pendingTurn, clearTurn, writeTurn, PENDING_WINDOW_MS, type PendingTurn } from "./selection";
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

  // The stream has no replay or running-task flag. On reload, subscribe first,
  // then read the committed transcript while listening for newer commits.
  interface Recovery {
    id: string;
    reading: boolean;
    revision: number;
    lastEnd?: number;
    loaded: boolean;
    pending: PendingTurn | null;
  }
  let recovery: Recovery | null = null;
  let localTurn: PendingTurn | null = null;
  let recoveryDeadline: number | undefined;

  function finishTurn() {
    window.clearTimeout(recoveryDeadline);
    const user = getState().user;
    if (user) clearTurn(user.id);
    if (recovery) recovery.pending = null;
    localTurn = null;
  }

  function remember(id: string | null) {
    const user = getState().user;
    if (user) {
      finishTurn();
      rememberDialog(user.id, id);
    }
  }

  function stopStream() {
    window.clearTimeout(recoveryDeadline);
    recovery = null;
    localTurn = null;
    generation++;
    connection?.close();
    connection = null;
    buffer = [];
    reopened = false;
  }

  function destroy() {
    if (disposed) return;
    const user = getState().user;
    // A locally submitted request is still known to be outstanding on unload.
    // Repeated reloads of a recovered request keep its previous deadline.
    if (localTurn) localTurn.expiresAt = Date.now() + PENDING_WINDOW_MS;
    const pending = localTurn ?? recovery?.pending;
    if (user && pending) writeTurn(user.id, pending);
    disposed = true;
    dispatch({ type: "closed" });
    window.clearTimeout(retryTimer);
    stopStream();
  }

  function login() {
    if (disposed) return;
    remember(null);
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

  function notify(text: string, kind: "info" | "error" = "info") {
    if (!disposed) dispatch({ type: "notice", text, kind });
  }

  async function withSession<T>(operation: () => Promise<T>): Promise<T> {
    try {
      return await operation();
    } catch (error) {
      if (errorCode(error) !== "unauthorized" || disposed) throw error;
    }
    const result = await refreshSession(auth);
    if (result.status === SESSION.ANONYMOUS) login();
    if (result.status === SESSION.USER && result.user.id !== getState().user?.id) login();
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

  function watchDeadline(current: Recovery, expiresAt: number) {
    recoveryDeadline = window.setTimeout(() => {
      if (recovery !== current || !current.pending) return;
      // Recent stream activity extends the silence window. Only one timer is armed.
      if (current.pending.expiresAt > expiresAt && current.pending.expiresAt > Date.now()) {
        watchDeadline(current, current.pending.expiresAt);
        return;
      }
      finishTurn();
      dispatch({ type: "remote-run", active: false });
      void snapshot(current);
    }, Math.max(0, expiresAt - Date.now()));
  }

  async function restore(id: string) {
    const user = getState().user;
    if (disposed || !user) return;
    stopStream();
    const pending = pendingTurn(user.id, id);
    const current = { id, reading: false, revision: 0, loaded: false, pending };
    recovery = current;
    if (pending) {
      dispatch({ type: "remote-run", active: true });
      watchDeadline(current, pending.expiresAt);
    }
    dispatch({ type: "hydrate", pending: true });
    connect(id);
  }

  async function snapshot(current: Recovery) {
    if (current.reading || current !== recovery) return;
    current.reading = true;
    dispatch({ type: "hydrate", pending: true });
    try {
      let revision: number;
      let story: Awaited<ReturnType<AgentApi["getMessages"]>>;
      do {
        revision = current.revision;
        story = await withSession(() => api.getMessages(current.id));
        if (current !== recovery) return;
        // A commit observed during the GET is often already in its response.
        if (current.lastEnd && story.messages.some(m => m.id === current.lastEnd)) break;
      } while (current.revision !== revision);

      if (current.pending) {
        const last = story.messages.filter(m => m.role === "assistant").at(-1);
        if (last && last.id !== current.pending.lastAnswer) {
          finishTurn();
          dispatch({ type: "remote-run", active: false });
        }
      }
      current.loaded = true;
      dispatch({ type: "snapshot", title: story.title, messages: story.messages.map(m => ({ ...m, complete: true })) });
      dispatch({ type: "hydrate", pending: false });
    } catch (error) {
      if (current !== recovery) return;
      stopStream();
      dispatch({ type: "disconnected" });
      dispatch({ type: "hydrate", pending: false });
      dispatch({ type: "remote-run", active: false });
      if (errorCode(error) === "not_found") {
        remember(null);
        if (busy(getState())) retry(create);
        else await create();
      } else {
        notify("Не удалось загрузить историю. Скоро попробуем ещё раз", "error");
        retry(() => restore(current.id));
      }
    } finally {
      current.reading = false;
    }
  }

  function receive(type: DialogEventType, payload: unknown) {
    if (type === "ready") {
      reopened = false;
      dispatch({ type: "ready" });
      if (recovery && !localTurn) {
        // A run might have ended while this stream was disconnected.
        dispatch({ type: "remote-run", active: recovery.pending !== null });
        recovery.revision++;
        recovery.lastEnd = undefined;
        void snapshot(recovery);
      }
      return;
    }
    if (getState().submitting) {
      buffer.push([type, payload]);
      return;
    }
    const data = payload && typeof payload === "object" ? payload : {};
    if (recovery && !localTurn) {
      if (type === "message_start" || type === "message_delta") {
        if (recovery.pending) recovery.pending.expiresAt = Date.now() + PENDING_WINDOW_MS;
        dispatch({ type: "remote-run", active: true });
        return;
      }
      if (type === "message_end") {
        finishTurn();
        dispatch({ type: "remote-run", active: false });
        recovery.revision++;
        recovery.lastEnd = "message_id" in data && typeof data.message_id === "number" ? data.message_id : undefined;
        void snapshot(recovery);
        void list();
        return;
      }
    }
    switch (type) {
      case "message_start": dispatch({ type: "answer-start" }); break;
      case "message_delta":
        if ("delta" in data && typeof data.delta === "string") dispatch({ type: "delta", text: data.delta });
        else notify("некорректное событие от сервера", "error");
        break;
      case "message_end":
        finishTurn();
        dispatch({ type: "answer-end", id: "message_id" in data && typeof data.message_id === "number" && Number.isInteger(data.message_id) ? data.message_id : undefined });
        void list();
        break;
      case "message_error":
        finishTurn();
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
    if (session.status !== SESSION.USER) return;
    if (session.user.id !== getState().user?.id) return login();
    if (!stream.isClosed()) return;
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
        // EventSource hides HTTP errors, including the 404 of an expired draft.
        if (recovery && !recovery.loaded) void snapshot(recovery);
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
    try {
      const id = await withSession(() => api.createDialog());
      if (!disposed) {
        remember(id);
        connect(id);
      }
    } catch {
      if (disposed) return;
      dispatch({ type: "switch", pending: false });
      notify("Не удалось подключиться. Скоро попробуем ещё раз", "error");
      retry(create);
    }
  }

  async function open(id: string) {
    if (disposed || busy(getState()) || getState().dialogId === id) return;
    dispatch({ type: "switch", pending: true });
    try {
      const story = await withSession(() => api.getMessages(id));
      if (disposed) return;
      window.clearTimeout(retryTimer);
      stopStream();
      dispatch({ type: "story", id, title: story.title, messages: story.messages.map(m => ({ ...m, complete: true })) });
      remember(id);
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
    if (getState().dialogId === id) {
      remember(null);
      await create();
    }
  }

  async function submit(draft: string, readingMinutes: number | null) {
    const request = draft.trim();
    const s = getState();
    const id = s.dialogId;
    if (!request || !id || !s.ready || busy(s) || disposed) return false;
    const lastAnswer = s.messages.filter(m => m.role === "assistant" && m.id !== undefined).at(-1)?.id ?? null;
    localTurn = { dialogId: id, lastAnswer, expiresAt: Date.now() + PENDING_WINDOW_MS };
    if (s.user) writeTurn(s.user.id, localTurn);
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
      localTurn = null;
      if (!disposed) {
        finishTurn();
        dispatch({ type: "rejected" });
      }
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
    const session = await checkSession(auth);
    if (disposed) return;
    if (session.status === SESSION.ANONYMOUS) return login();
    if (session.status === SESSION.UNAVAILABLE) {
      notify("Не удалось подключиться. Скоро попробуем ещё раз", "error");
      return retry(start);
    }
    dispatch({ type: "session", user: session.user });
    void list();
    const saved = selectedDialog(session.user.id);
    if (saved) await restore(saved);
    else await create();
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
