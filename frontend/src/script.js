import { AgentApi } from "./agent-api.js";

const form = document.querySelector("#saiForm");
const prompt = document.querySelector("#saiPrompt");
const messages = document.querySelector("#saiMessages");
const send = document.querySelector(".sai-send");
const status = document.querySelector("#saiStatus");
const statusText = document.querySelector("#saiStatusText");
const hint = document.querySelector(".sai-hint");
const chips = [...document.querySelectorAll(".sai-chip")];

const presets = {
  "Про дружбу": "Придумай историю про Кроша и Ёжика, которые поссорились из-за игры, но общее дело помогло им снова стать друзьями.",
  "Приключение": "Крош, Ёжик и Нюша находят старую карту и отправляются искать таинственное место. Придумай, что ждёт их в пути.",
  "Перед сном": "Расскажи короткую, спокойную и уютную историю перед сном про Бараша, который искал потерянную рифму.",
  "В космосе": "Крош и Ёжик построили ракету вместе с Пином и отправились к далёкой звезде. Придумай их космическое приключение.",
  "Про чувства": "Нюша расстроилась из-за неудачи, а друзья помогли ей понять свои чувства и снова поверить в себя. Расскажи эту историю.",
  "Поучительная": "Придумай весёлую историю, в которой Крош совершает ошибку, исправляет её и понимает, почему важно говорить правду.",
};

const api = new AgentApi();
let dialogId = null;
let connection = null;
let ready = false;
let processing = false;
let submitting = false;
let currentAssistant = null;
let pendingEvents = [];
let retryTimer = null;
let unloading = false;

function autosize() {
  prompt.style.height = "auto";
  prompt.style.height = `${Math.min(prompt.scrollHeight, 132)}px`;
}

function setStatus(text, state = "ready") {
  statusText.textContent = text;
  status.dataset.state = state;
}

function updateForm() {
  const disabled = !ready || processing || submitting;
  prompt.disabled = disabled;
  send.disabled = disabled;
  for (const chip of chips) chip.disabled = disabled;
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
    currentAssistant = null;
    setStatus("готов к идеям");
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
}

async function createDialog() {
  if (unloading) return;
  ready = false;
  processing = false;
  submitting = false;
  currentAssistant = null;
  pendingEvents = [];
  dialogId = null;
  connection?.close();
  connection = null;
  setStatus("создание диалога…", "connecting");
  updateForm();

  try {
    const createdDialogId = await api.createDialog();
    if (unloading) return;
    dialogId = createdDialogId;
    setStatus("подключение к потоку…", "connecting");
    connection = api.connectEvents(dialogId, {
      onEvent: applyAgentEvent,
      onInvalidEvent: markInvalidEvent,
      onConnectionError: handleConnectionError,
    });
  } catch {
    if (unloading) return;
    dialogId = null;
    setStatus("backend недоступен; повторная попытка…", "error");
    updateForm();
    if (retryTimer === null) {
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        void createDialog();
      }, 3000);
    }
  }
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
  if (!request || !dialogId || !ready || processing || submitting) return;

  submitting = true;
  pendingEvents = [];
  setStatus("отправка…", "processing");
  updateForm();

  try {
    await api.submitMessage(dialogId, request);
    addMessage(request, "user");
    prompt.value = "";
    autosize();
    resetChips();
    hint?.classList.add("is-hidden");

    submitting = false;
    processing = true;
    setStatus(ready ? "агент отвечает…" : "переподключение…", ready ? "processing" : "connecting");
    const buffered = pendingEvents;
    pendingEvents = [];
    for (const [type, data] of buffered) applyAgentEvent(type, data);
  } catch {
    submitting = false;
    pendingEvents = [];
    setStatus("не удалось отправить сообщение", "error");
  }
  updateForm();
});

window.addEventListener("beforeunload", () => {
  unloading = true;
  if (retryTimer !== null) window.clearTimeout(retryTimer);
  connection?.close();
});
createDialog();
