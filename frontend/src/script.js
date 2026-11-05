import { AgentApi } from "./agent-api.js";
import { AuthApi } from "./auth-api.js";
import { LOGIN_PATH, SESSION, checkSession, refreshSession } from "./auth-session.js";
import { mountPasswordSettings } from "./password-settings.js";

const form = document.querySelector("#saiForm");
const prompt = document.querySelector("#saiPrompt");
const messages = document.querySelector("#saiMessages");
const send = document.querySelector(".sai-send");
const status = document.querySelector("#saiStatus");
const statusText = document.querySelector("#saiStatusText");
const logoutButton = document.querySelector("#saiLogout");
const sidebar = document.querySelector("#saiSidebar");
const backdrop = document.querySelector("#saiBackdrop");
const historyToggle = document.querySelector("#saiHistoryToggle");
const newStoryButton = document.querySelector("#saiNewStory");
const historyList = document.querySelector("#saiHistory");
const historyState = document.querySelector("#saiHistoryState");
const historyRetry = document.querySelector("#saiHistoryRetry");
const userLogin = document.querySelector("#saiUserLogin");
const title = document.querySelector("#saiTitle");
const kroshTemplate = document.querySelector("#saiKroshTemplate");
const facesTemplate = document.querySelector("#saiFacesTemplate");
const lengthPicker = document.querySelector("#saiLength");
const lengthButton = document.querySelector("#saiLengthButton");
const lengthPanel = document.querySelector("#saiLengthPanel");
const lengthValue = document.querySelector("#saiLengthValue");
const lengthCurrent = document.querySelector("#saiLengthCurrent");
const lengthDots = document.querySelector("#saiLengthDots");
const newsBox = document.querySelector("#saiNews");
const adminLink = document.querySelector("#saiAdminLink");
const chips = [...document.querySelectorAll(".sai-chip")];

const NEW_STORY_TITLE = "Новая история";
// Score, its caption and what the Smeshariki face says once chosen.
const RATINGS = [
  [1, "Совсем не понравилось", "Ёжик грустит"],
  [2, "Скорее не понравилось", "Нюша недовольна"],
  [3, "Так себе", "Лосяш задумался"],
  [4, "Понравилось", "Копатыч доволен"],
  [5, "Очень понравилось!", "Крош в восторге!"],
];
// Why an answer is reported: the value sent to the backend and its label.
const REPORT_REASONS = [
  ["scary", "Страшно"],
  ["rude", "Грубо или обидно"],
  ["wrong", "Неправильно или непонятно"],
  ["other", "Другое"],
];
const REPORT_COMMENT_MAX_LENGTH = 500;
const REVIEWED_LABEL = "Взрослые посмотрели — спасибо!";
const UNTITLED = "Без названия";
const COPY_LABEL = "Копировать";
// Slider steps of the story length: minutes sent to the agent and the label.
const LENGTH_STEPS = [
  [null, "Любая"],
  [2, "2 мин"],
  [5, "5 мин"],
  [10, "10 мин"],
];

const presets = {
  "Про дружбу": "Придумай историю про Кроша и Ёжика, которые поссорились из-за игры, но общее дело помогло им снова стать друзьями.",
  "Приключение": "Крош, Ёжик и Нюша находят старую карту и отправляются искать таинственное место. Придумай, что ждёт их в пути.",
  "Перед сном": "Расскажи короткую, спокойную и уютную историю перед сном про Бараша, который искал потерянную рифму.",
  "В космосе": "Крош и Ёжик построили ракету вместе с Пином и отправились к далёкой звезде. Придумай их космическое приключение.",
  "Про чувства": "Нюша расстроилась из-за неудачи, а друзья помогли ей понять свои чувства и снова поверить в себя. Расскажи эту историю.",
  "Поучительная": "Придумай весёлую историю, в которой Крош совершает ошибку, исправляет её и понимает, почему важно говорить правду.",
};

const api = new AgentApi();
const auth = new AuthApi();
let dialogId = null;
let connection = null;
let ready = false;
let processing = false;
let submitting = false;
// Creating a dialog or loading a saved one: the current dialog must not change.
let switching = false;
let currentAssistant = null;
let pendingEvents = [];
let retryTimer = null;
let unloading = false;
let sessionCheck = null;
let reopenedSinceReady = false;
let loggingOut = false;
let signedIn = false;
let dialogs = [];
let historyLoaded = false;
let historyFailed = false;
let historyRequest = 0;
let historyButtons = [];
// A story waiting for "Удалить?" and the one being deleted right now.
let confirmingId = null;
let deletingId = null;
let deleteButtons = new Map();
let krosh = null;
// The open report panel; only one at a time.
let reportPanel = null;
// Message bubbles and their rows: a finished answer gets its copy button there.
const rows = new WeakMap();

function autosize() {
  prompt.style.height = "auto";
  prompt.style.height = `${Math.min(prompt.scrollHeight, 132)}px`;
}

function setStatus(text, state = "ready") {
  statusText.textContent = text;
  status.dataset.state = state;
}

function busy() {
  return processing || submitting || switching;
}

function updateForm() {
  const locked = busy();
  const disabled = !ready || locked;
  prompt.disabled = disabled;
  send.disabled = disabled;
  lengthPicker.disabled = disabled;
  lengthButton.disabled = disabled;
  if (disabled) closeLength();
  for (const chip of chips) chip.disabled = disabled;
  newStoryButton.disabled = locked || !signedIn;
  for (const button of historyButtons) button.disabled = locked;
}

function addMessage(text, role = "assistant") {
  const row = document.createElement("div");
  row.className = `sai-row${role === "user" ? " user" : ""}`;
  if (role !== "user") {
    const icon = document.createElement("div");
    icon.className = "sai-msg-icon";
    icon.textContent = "⭐";
    row.append(icon);
  }
  const bubble = document.createElement("div");
  bubble.className = "sai-bubble";
  bubble.textContent = text;
  // The user's own message can be copied at once, an answer once it is finished.
  if (role === "user") row.append(copyButton(bubble));
  row.append(bubble);
  rows.set(bubble, row);
  messages.append(row);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

function addCopy(bubble) {
  rows.get(bubble)?.append(copyButton(bubble));
}

// The text is read on click, so a streamed answer is copied in full.
function copyButton(bubble) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "sai-copy";
  button.textContent = COPY_LABEL;
  button.setAttribute("aria-label", "Скопировать сообщение");
  let timer = null;
  button.addEventListener("click", async () => {
    if (!(await copyText(bubble.textContent))) {
      setStatus("Не удалось скопировать", "error");
      return;
    }
    button.textContent = "Скопировано";
    button.classList.add("is-done");
    if (timer !== null) window.clearTimeout(timer);
    timer = window.setTimeout(() => {
      timer = null;
      button.textContent = COPY_LABEL;
      button.classList.remove("is-done");
    }, 1500);
  });
  return button;
}

// The Clipboard API needs a secure context; plain HTTP by IP falls back to execCommand.
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return copyThroughTextarea(text);
  }
}

function copyThroughTextarea(text) {
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.className = "sai-copy-buffer";
  document.body.append(area);
  try {
    area.select();
    return document.execCommand("copy");
  } catch {
    return false;
  } finally {
    area.remove();
  }
}

// Five Smeshariki faces under one saved answer; the state changes at once and rolls back on error.
function addFeedback(messageId, initial, report = null) {
  const ratedDialogId = dialogId;
  let value = initial;
  let pending = false;
  const bar = document.createElement("div");
  bar.className = "sai-feedback";
  const question = document.createElement("span");
  question.className = "sai-feedback-q";
  question.textContent = "Как тебе история?";
  bar.append(question);
  const say = document.createElement("span");
  say.className = "sai-feedback-say";
  const ratingButtons = new Map();

  const paint = () => {
    for (const [rating, button] of ratingButtons) {
      const selected = rating === value;
      button.setAttribute("aria-pressed", selected ? "true" : "false");
      if (selected) button.classList.add("is-selected");
      else button.classList.remove("is-selected");
      button.disabled = pending;
    }
    if (value === null) bar.classList.remove("is-rated");
    else bar.classList.add("is-rated");
    say.textContent = RATINGS.find(([rating]) => rating === value)?.[2] ?? "";
  };

  for (const [rating, label] of RATINGS) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sai-face";
    button.dataset.value = String(rating);
    button.setAttribute("aria-label", `Оценка ${rating} из 5: ${label}`);
    const tip = document.createElement("span");
    tip.className = "sai-face-tip";
    tip.textContent = label;
    button.append(facesTemplate.content.querySelector(`[data-score="${rating}"]`).cloneNode(true), tip);
    button.addEventListener("click", async () => {
      if (pending) return;
      const previous = value;
      const next = value === rating ? null : rating;
      value = next;
      pending = true;
      paint();
      try {
        await withSession(() => (next === null
          ? api.clearFeedback(ratedDialogId, messageId)
          : api.setFeedback(ratedDialogId, messageId, next)));
      } catch {
        if (unloading) return;
        value = previous;
        setStatus("Не удалось сохранить оценку", "error");
      } finally {
        pending = false;
        if (!unloading) paint();
      }
    });
    ratingButtons.set(rating, button);
    bar.append(button);
  }
  // The report flag has a line of its own, so the phrase of any length
  // next to the faces never moves it.
  const line = document.createElement("div");
  line.className = "sai-report-line";
  bar.append(say, line);
  addReport(bar, line, messageId, report);
  paint();
  messages.append(bar);
  messages.scrollTop = messages.scrollHeight;
}

// "Пожаловаться" under an answer; a sent report cannot be taken back. Whether
// it was dismissed is never shown: a reviewed report just thanks the user.
function addReport(bar, line, messageId, report) {
  const reportedDialogId = dialogId;
  const flag = document.createElement("button");
  flag.type = "button";
  flag.className = "sai-report";
  flag.setAttribute("aria-expanded", "false");
  const markSent = () => {
    flag.textContent = "Жалоба отправлена";
    flag.setAttribute("aria-label", "Жалоба отправлена");
    flag.disabled = true;
    flag.classList.add("is-sent");
  };
  if (report === "reviewed") {
    flag.textContent = REVIEWED_LABEL;
    flag.setAttribute("aria-label", REVIEWED_LABEL);
    flag.disabled = true;
    flag.classList.add("is-reviewed");
  } else if (report === "sent") markSent();
  else {
    flag.textContent = "Пожаловаться";
    flag.setAttribute("aria-label", "Пожаловаться на историю");
  }
  flag.addEventListener("click", () => {
    if (flag.disabled) return;
    const wasOpen = reportPanel?.flag === flag;
    closeReport();
    if (!wasOpen) openReport(bar, flag, reportedDialogId, messageId, markSent);
  });
  line.append(flag);
}

function openReport(bar, flag, reportedDialogId, messageId, markSent) {
  let reason = null;
  let sending = false;
  const panel = document.createElement("div");
  panel.className = "sai-report-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Что не так с историей?");
  const heading = document.createElement("div");
  heading.className = "sai-report-title";
  heading.textContent = "Что не так с историей?";
  const choices = document.createElement("div");
  choices.className = "sai-report-reasons";
  const comment = document.createElement("textarea");
  comment.className = "sai-report-comment";
  comment.maxLength = REPORT_COMMENT_MAX_LENGTH;
  comment.rows = 2;
  comment.setAttribute("aria-label", "Комментарий к жалобе");
  const actions = document.createElement("div");
  actions.className = "sai-report-actions";
  const sendButton = historyButton("sai-report-send", "Отправить");
  const cancel = historyButton("sai-report-cancel", "Отмена");
  const entry = { flag, close: () => panel.remove() };

  const reasonButtons = REPORT_REASONS.map(([value, label]) => {
    const button = historyButton("sai-report-reason", label);
    button.dataset.reason = value;
    button.addEventListener("click", () => {
      if (sending) return;
      reason = value;
      paint();
    });
    return button;
  });
  const paint = () => {
    // Only "Другое" does not say by itself what is wrong with the story.
    const needsComment = reason === "other";
    comment.setAttribute("aria-required", needsComment ? "true" : "false");
    comment.placeholder = `Расскажи, что не так (${needsComment ? "обязательно" : "необязательно"})`;
    for (const button of reasonButtons) {
      const selected = button.dataset.reason === reason;
      button.setAttribute("aria-pressed", selected ? "true" : "false");
      if (selected) button.classList.add("is-selected");
      else button.classList.remove("is-selected");
      button.disabled = sending;
    }
    comment.disabled = sending;
    sendButton.disabled = sending || reason === null || (needsComment && !comment.value.trim());
    cancel.disabled = sending;
  };

  comment.addEventListener("input", () => paint());
  sendButton.addEventListener("click", async () => {
    if (sendButton.disabled) return;
    sending = true;
    paint();
    try {
      await withSession(() => api.reportMessage(reportedDialogId, messageId, reason, comment.value.trim()));
    } catch {
      if (unloading) return;
      sending = false;
      paint();
      setStatus("Не удалось отправить жалобу", "error");
      return;
    }
    if (unloading) return;
    if (reportPanel === entry) closeReport();
    else entry.close();
    markSent();
    setStatus("Спасибо! Взрослые посмотрят");
  });
  cancel.addEventListener("click", () => closeReport({ focusFlag: true }));

  choices.append(...reasonButtons);
  actions.append(sendButton, cancel);
  panel.append(heading, choices, comment, actions);
  paint();
  bar.append(panel);
  flag.setAttribute("aria-expanded", "true");
  reportPanel = entry;
  reasonButtons[0].focus();
}

function closeReport({ focusFlag = false } = {}) {
  if (reportPanel === null) return false;
  const { flag, close } = reportPanel;
  reportPanel = null;
  close();
  flag.setAttribute("aria-expanded", "false");
  if (focusFlag) flag.focus();
  return true;
}

// An empty story is greeted by Krosh; he leaves once the conversation starts.
function showStory(storyTitle, items) {
  title.textContent = storyTitle ?? NEW_STORY_TITLE;
  title.title = title.textContent;
  krosh = null;
  reportPanel = null;
  messages.replaceChildren();
  if (items.length === 0) {
    krosh = kroshTemplate.content.firstElementChild.cloneNode(true);
    messages.append(krosh);
    return;
  }
  for (const item of items) {
    const bubble = addMessage(item.content, item.role);
    if (item.role !== "assistant") continue;
    addCopy(bubble);
    addFeedback(item.id, item.feedback, item.report);
  }
}

// Krosh tells, once per page, that adults have looked at the user's reports.
async function showNews() {
  let news;
  try {
    news = await withSession(() => api.getReportNews());
  } catch {
    return;
  }
  if (unloading || news.length === 0) return;
  const ids = news.map(item => item.reportId);
  const [single] = news;
  const story = news.length === 1 && single.dialogTitle !== null && single.dialogId !== null
    ? `на историю «${single.dialogTitle}»`
    : "на одну историю";
  const say = document.createElement("p");
  say.className = "sai-news-say";
  say.textContent = news.length > 1
    ? `Взрослые посмотрели твои жалобы (${news.length}). Спасибо, что рассказал!`
    : `Взрослые посмотрели твою жалобу ${story}. Спасибо, что рассказал!`;
  const face = facesTemplate.content.querySelector('[data-score="5"]').cloneNode(true);
  face.className = "sai-news-face";
  const actions = document.createElement("div");
  actions.className = "sai-news-actions";

  const close = () => {
    newsBox.hidden = true;
    newsBox.replaceChildren();
    // A failure just brings the news back next time.
    withSession(() => api.markReportNewsSeen(ids)).catch(() => {});
  };
  const ok = historyButton("sai-news-ok", "Хорошо");
  ok.addEventListener("click", close);
  actions.append(ok);
  if (news.length === 1 && single.dialogId !== null) {
    const open = historyButton("sai-news-open", "Открыть историю");
    open.addEventListener("click", () => {
      close();
      void openDialog(single.dialogId);
    });
    actions.append(open);
  }
  newsBox.setAttribute("role", "status");
  newsBox.replaceChildren(face, say, actions);
  newsBox.hidden = false;
}

function dismissKrosh() {
  krosh?.remove();
  krosh = null;
}

function historyButton(className, text) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  if (text) button.textContent = text;
  return button;
}

// "Удалить историю?" in place of the story's row.
function confirmRow(entry, item) {
  entry.className = "sai-history-row is-confirming";
  const text = document.createElement("span");
  text.className = "sai-history-confirm-text";
  text.textContent = "Удалить историю?";
  const remove = historyButton("sai-history-confirm-delete", "Удалить");
  const cancel = historyButton("sai-history-confirm-cancel", "Отмена");
  remove.disabled = cancel.disabled = busy() || deletingId !== null;
  remove.addEventListener("click", () => deleteStory(item.dialogId));
  cancel.addEventListener("click", cancelDelete);
  historyButtons.push(remove, cancel);
  entry.append(text, remove, cancel);
  return cancel;
}

function storyRow(entry, item) {
  const label = item.title ?? UNTITLED;
  entry.className = "sai-history-row";
  const button = historyButton("sai-history-item", label);
  button.title = label;
  if (item.dialogId === dialogId) button.setAttribute("aria-current", "true");
  button.disabled = busy();
  button.addEventListener("click", () => void openDialog(item.dialogId));
  const trash = historyButton("sai-history-delete");
  trash.setAttribute("aria-label", `Удалить историю «${label}»`);
  trash.title = "Удалить историю";
  trash.disabled = busy() || deletingId !== null;
  trash.addEventListener("click", () => askDelete(item.dialogId));
  historyButtons.push(button, trash);
  deleteButtons.set(item.dialogId, trash);
  entry.append(button, trash);
}

function renderHistory() {
  historyButtons = [];
  deleteButtons = new Map();
  let confirmFocus = null;
  const items = dialogs.map(item => {
    const entry = document.createElement("li");
    if (item.dialogId === confirmingId) confirmFocus = confirmRow(entry, item);
    else storyRow(entry, item);
    return entry;
  });
  historyList.replaceChildren(...items);

  if (historyFailed) historyState.textContent = "Не удалось загрузить истории";
  else if (!historyLoaded) historyState.textContent = "Загрузка…";
  else historyState.textContent = dialogs.length ? "" : "Здесь появятся ваши истории";
  historyRetry.hidden = !historyFailed;

  const current = dialogs.find(item => item.dialogId === dialogId);
  if (current?.title) {
    title.textContent = current.title;
    title.title = current.title;
  }
  return confirmFocus;
}

function askDelete(id) {
  if (busy() || deletingId !== null) return;
  confirmingId = id;
  renderHistory()?.focus();
}

function cancelDelete() {
  if (confirmingId === null || deletingId !== null) return;
  const id = confirmingId;
  confirmingId = null;
  renderHistory();
  deleteButtons.get(id)?.focus();
}

// The story is gone for good; deleting the open one starts a new story.
async function deleteStory(id) {
  if (busy() || deletingId !== null) return;
  deletingId = id;
  renderHistory();
  try {
    await withSession(() => api.deleteDialog(id));
  } catch (error) {
    if (unloading) return;
    if (error?.code !== "not_found") {
      deletingId = null;
      confirmingId = null;
      renderHistory();
      setStatus("Не удалось удалить историю", "error");
      return;
    }
  }
  deletingId = null;
  confirmingId = null;
  dialogs = dialogs.filter(item => item.dialogId !== id);
  if (id === dialogId) await createDialog();
  else renderHistory();
}

async function loadDialogs() {
  if (unloading) return;
  const request = ++historyRequest;
  historyFailed = false;
  historyRetry.hidden = true;
  try {
    const list = await withSession(() => api.listDialogs());
    if (request !== historyRequest || unloading) return;
    dialogs = list;
    historyLoaded = true;
  } catch {
    if (request !== historyRequest || unloading) return;
    historyFailed = true;
  }
  renderHistory();
}

function openPanel() {
  sidebar.classList.add("is-open");
  backdrop.hidden = false;
  historyToggle.setAttribute("aria-expanded", "true");
}

function closePanel() {
  sidebar.classList.remove("is-open");
  backdrop.hidden = true;
  historyToggle.setAttribute("aria-expanded", "false");
}

function resetChips() {
  for (const chip of chips) {
    chip.classList.remove("is-selected");
    chip.setAttribute("aria-pressed", "false");
  }
}

function markInvalidEvent() {
  setStatus("некорректное событие от сервера", "error");
}

function applyAgentEvent(type, data) {
  if (type === "ready") {
    ready = true;
    reopenedSinceReady = false;
    setStatus(processing ? "агент отвечает…" : "готов к идеям", processing ? "processing" : "ready");
    updateForm();
    if (!processing && !submitting) prompt.focus();
    return;
  }

  if (submitting) {
    pendingEvents.push([type, data]);
    return;
  }

  if (type === "message_start") {
    processing = true;
    currentAssistant ??= addMessage("");
    setStatus("агент отвечает…", "processing");
  } else if (type === "message_delta") {
    if (typeof data?.delta !== "string") {
      markInvalidEvent();
      return;
    }
    processing = true;
    currentAssistant ??= addMessage("");
    currentAssistant.textContent += data.delta;
    messages.scrollTop = messages.scrollHeight;
  } else if (type === "message_end") {
    processing = false;
    if (currentAssistant) addCopy(currentAssistant);
    if (currentAssistant && Number.isInteger(data?.message_id)) {
      addFeedback(data.message_id, null);
    }
    currentAssistant = null;
    setStatus("готов к идеям");
    // The answered dialog is saved now: show it in the list with its title.
    void loadDialogs();
  } else if (type === "message_error") {
    processing = false;
    currentAssistant ??= addMessage("");
    currentAssistant.classList.add("sai-bubble-error");
    currentAssistant.textContent += currentAssistant.textContent
      ? "\nОшибка ответа"
      : "Ошибка ответа";
    currentAssistant = null;
    const message = typeof data?.message === "string"
      ? data.message
      : "ошибка агента";
    setStatus(message, "error");
  }
  updateForm();
}

function handleConnectionError() {
  ready = false;
  setStatus("переподключение…", "connecting");
  updateForm();
  void verifyConnection();
}

const eventHandlers = {
  onEvent: applyAgentEvent,
  onInvalidEvent: markInvalidEvent,
  onConnectionError: handleConnectionError,
};

function clearRetry() {
  if (retryTimer !== null) window.clearTimeout(retryTimer);
  retryTimer = null;
}

function redirectToLogin() {
  unloading = true;
  clearRetry();
  connection?.close();
  window.location.replace(LOGIN_PATH);
}

function scheduleRetry(action) {
  if (retryTimer !== null) return;
  retryTimer = window.setTimeout(() => {
    retryTimer = null;
    void action();
  }, 3000);
}

// Retries an operation once after a 401 if refresh renews the session.
async function withSession(operation) {
  try {
    return await operation();
  } catch (error) {
    if (error?.code !== "unauthorized") throw error;
  }
  const session = await refreshSession(auth);
  if (session.status === SESSION.ANONYMOUS) {
    redirectToLogin();
    throw new Error("session expired");
  }
  if (session.status === SESSION.UNAVAILABLE) throw new Error("auth unavailable");
  try {
    return await operation();
  } catch (error) {
    if (error?.code === "unauthorized") redirectToLogin();
    throw error;
  }
}

// EventSource hides the HTTP status, so a failed stream is checked separately.
async function verifyConnection() {
  if (sessionCheck || unloading) return;
  const current = connection;
  sessionCheck = checkSession(auth);
  const session = await sessionCheck;
  sessionCheck = null;
  if (unloading || connection !== current || !current) return;
  if (session.status === SESSION.ANONYMOUS) {
    redirectToLogin();
    return;
  }
  if (session.status !== SESSION.USER || !current.isClosed()) return;
  if (reopenedSinceReady) {
    setStatus("соединение потеряно; обновите страницу", "error");
    return;
  }
  reopenedSinceReady = true;
  connection = api.connectEvents(dialogId, eventHandlers);
}

async function start() {
  if (unloading) return;
  setStatus("проверка входа…", "connecting");
  updateForm();
  const session = await checkSession(auth);
  if (unloading) return;
  if (session.status === SESSION.ANONYMOUS) {
    redirectToLogin();
    return;
  }
  if (session.status === SESSION.UNAVAILABLE) {
    setStatus("backend недоступен; повторная попытка…", "error");
    scheduleRetry(start);
    return;
  }
  signedIn = true;
  userLogin.textContent = session.user.login;
  userLogin.title = session.user.login;
  // The way back for an administrator who opened the chat from the panel.
  adminLink.hidden = session.user.role !== "admin";
  void loadDialogs();
  await createDialog();
  void showNews();
}

function leaveDialog() {
  ready = false;
  processing = false;
  submitting = false;
  currentAssistant = null;
  pendingEvents = [];
  connection?.close();
  connection = null;
}

async function createDialog() {
  if (unloading) return;
  clearRetry();
  leaveDialog();
  dialogId = null;
  switching = true;
  showStory(null, []);
  setStatus("создание диалога…", "connecting");
  updateForm();
  renderHistory();

  try {
    const createdDialogId = await withSession(() => api.createDialog());
    if (unloading) return;
    dialogId = createdDialogId;
    reopenedSinceReady = false;
    setStatus("подключение к потоку…", "connecting");
    connection = api.connectEvents(dialogId, eventHandlers);
  } catch {
    if (unloading) return;
    dialogId = null;
    setStatus("backend недоступен; повторная попытка…", "error");
    scheduleRetry(createDialog);
  } finally {
    switching = false;
  }
  if (unloading) return;
  updateForm();
  renderHistory();
}

// The saved history is loaded first, so a failure keeps the current dialog intact.
async function openDialog(id) {
  if (unloading || busy() || id === dialogId) return;
  closePanel();
  switching = true;
  setStatus("загрузка истории…", "connecting");
  updateForm();

  let transcript;
  try {
    transcript = await withSession(() => api.getMessages(id));
  } catch (error) {
    switching = false;
    if (unloading) return;
    const notFound = error?.code === "not_found";
    setStatus(notFound ? "история не найдена" : "не удалось открыть историю", "error");
    updateForm();
    if (notFound) void loadDialogs();
    return;
  }
  if (unloading) return;

  clearRetry();
  leaveDialog();
  dialogId = id;
  switching = false;
  reopenedSinceReady = false;
  showStory(transcript.title, transcript.messages);
  setStatus("подключение к потоку…", "connecting");
  connection = api.connectEvents(dialogId, eventHandlers);
  updateForm();
  renderHistory();
}

chips.forEach(chip => chip.addEventListener("click", () => {
  const promptPart = presets[chip.textContent.trim()];
  if (!promptPart || chip.disabled) return;

  prompt.value = promptPart;
  resetChips();
  chip.classList.add("is-selected");
  chip.setAttribute("aria-pressed", "true");
  autosize();
  prompt.focus();
}));

prompt.addEventListener("input", autosize);
prompt.addEventListener("keydown", event => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    form.requestSubmit();
  }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  const request = prompt.value.trim();
  if (!request || !dialogId || !ready || busy()) return;
  const [readingMinutes] = lengthStep();

  submitting = true;
  pendingEvents = [];
  setStatus("отправка…", "processing");
  updateForm();

  try {
    await withSession(() => api.submitMessage(dialogId, request, { readingMinutes }));
    dismissKrosh();
    addMessage(request, "user");
    prompt.value = "";
    autosize();
    resetChips();

    submitting = false;
    processing = true;
    setStatus(ready ? "агент отвечает…" : "переподключение…", ready ? "processing" : "connecting");
    const buffered = pendingEvents;
    pendingEvents = [];
    for (const [type, data] of buffered) applyAgentEvent(type, data);
  } catch {
    submitting = false;
    pendingEvents = [];
    if (unloading) return;
    setStatus("не удалось отправить сообщение", "error");
  }
  updateForm();
});

function lengthStep() {
  return LENGTH_STEPS[Number(lengthPicker.value)] ?? LENGTH_STEPS[0];
}

function showLength() {
  const [, label] = lengthStep();
  lengthValue.textContent = label;
  lengthCurrent.textContent = `(${label.toLowerCase()})`;
  lengthPicker.setAttribute("aria-valuetext", label);
  lengthButton.setAttribute("aria-label", `Длина истории: ${label}`);
  lengthDots.dataset.step = String(LENGTH_STEPS.indexOf(lengthStep()));
}

function openLength() {
  lengthPanel.hidden = false;
  lengthButton.setAttribute("aria-expanded", "true");
  lengthPicker.focus();
}

function closeLength({ focusButton = false } = {}) {
  if (lengthPanel.hidden) return;
  lengthPanel.hidden = true;
  lengthButton.setAttribute("aria-expanded", "false");
  if (focusButton) lengthButton.focus();
}

lengthButton.addEventListener("click", () => {
  if (lengthPanel.hidden) openLength();
  else closeLength();
});
lengthPicker.addEventListener("input", showLength);
lengthButton.setAttribute("aria-expanded", "false");
showLength();
document.addEventListener("click", event => {
  if (!lengthPanel.hidden && !lengthPanel.contains(event.target) && !lengthButton.contains(event.target)) {
    closeLength();
  }
});
document.addEventListener("keydown", event => {
  if (event.key !== "Escape") return;
  if (passwordSettings.isOpen()) {
    passwordSettings.close();
    return;
  }
  if (closeReport({ focusFlag: true })) return;
  if (!lengthPanel.hidden) closeLength({ focusButton: true });
  else if (confirmingId !== null) cancelDelete();
});

newStoryButton.addEventListener("click", () => {
  if (unloading || busy() || !signedIn) return;
  closePanel();
  void createDialog();
});
historyRetry.addEventListener("click", () => void loadDialogs());
historyToggle.addEventListener("click", openPanel);
backdrop.addEventListener("click", closePanel);

const passwordSettings = mountPasswordSettings({
  button: document.querySelector("#saiSettingsButton"),
  dialog: document.querySelector("#saiSettings"),
  close: document.querySelector("#saiSettingsClose"),
  form: document.querySelector("#saiPasswordForm"),
  currentPassword: document.querySelector("#saiCurrentPassword"),
  newPassword: document.querySelector("#saiNewPassword"),
  repeatPassword: document.querySelector("#saiRepeatPassword"),
  save: document.querySelector("#saiPasswordSave"),
  status: document.querySelector("#saiPasswordStatus"),
  changePassword: passwords => withSession(() => auth.changePassword(passwords)),
  beforeOpen: () => {
    closeLength();
    closeReport();
  },
  isUnloading: () => unloading,
});

// Cookies are cleared by the backend only on success, so a failed logout stays.
logoutButton.addEventListener("click", async () => {
  if (loggingOut) return;
  loggingOut = true;
  logoutButton.disabled = true;
  try {
    await auth.logout();
  } catch {
    loggingOut = false;
    logoutButton.disabled = false;
    setStatus("Не удалось выйти. Попробуйте ещё раз", "error");
    return;
  }
  redirectToLogin();
});

window.addEventListener("beforeunload", () => {
  unloading = true;
  clearRetry();
  connection?.close();
});
void start();
