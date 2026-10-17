import { AgentApi } from "./agent-api.js";
import { AuthApi } from "./auth-api.js";
import { LOGIN_PATH, SESSION, checkSession, refreshSession } from "./auth-session.js";

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
const UNTITLED = "Без названия";

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
let krosh = null;

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
  row.append(bubble);
  messages.append(row);
  messages.scrollTop = messages.scrollHeight;
  return bubble;
}

// Five Smeshariki faces under one saved answer; the state changes at once and rolls back on error.
function addFeedback(messageId, initial) {
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
  bar.append(say);
  paint();
  messages.append(bar);
  messages.scrollTop = messages.scrollHeight;
}

// An empty story is greeted by Krosh; he leaves once the conversation starts.
function showStory(storyTitle, items) {
  title.textContent = storyTitle ?? NEW_STORY_TITLE;
  krosh = null;
  messages.replaceChildren();
  if (items.length === 0) {
    krosh = kroshTemplate.content.firstElementChild.cloneNode(true);
    messages.append(krosh);
    return;
  }
  for (const item of items) {
    addMessage(item.content, item.role);
    if (item.role === "assistant") addFeedback(item.id, item.feedback);
  }
}

function dismissKrosh() {
  krosh?.remove();
  krosh = null;
}

function renderHistory() {
  historyButtons = [];
  const items = dialogs.map(item => {
    const entry = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "sai-history-item";
    button.textContent = item.title ?? UNTITLED;
    button.title = item.title ?? UNTITLED;
    if (item.dialogId === dialogId) button.setAttribute("aria-current", "true");
    button.disabled = busy();
    button.addEventListener("click", () => void openDialog(item.dialogId));
    historyButtons.push(button);
    entry.append(button);
    return entry;
  });
  historyList.replaceChildren(...items);

  if (historyFailed) historyState.textContent = "Не удалось загрузить истории";
  else if (!historyLoaded) historyState.textContent = "Загрузка…";
  else historyState.textContent = dialogs.length ? "" : "Здесь появятся ваши истории";
  historyRetry.hidden = !historyFailed;

  const current = dialogs.find(item => item.dialogId === dialogId);
  if (current?.title) title.textContent = current.title;
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
  void loadDialogs();
  await createDialog();
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
  const readingMinutes = lengthPicker.value ? Number(lengthPicker.value) : null;

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

newStoryButton.addEventListener("click", () => {
  if (unloading || busy() || !signedIn) return;
  closePanel();
  void createDialog();
});
historyRetry.addEventListener("click", () => void loadDialogs());
historyToggle.addEventListener("click", openPanel);
backdrop.addEventListener("click", closePanel);

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
