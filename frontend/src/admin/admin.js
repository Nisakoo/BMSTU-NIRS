import { AuthApi } from "../auth-api.js";
import { CHAT_PATH, LOGIN_PATH, SESSION, checkSession } from "../auth-session.js";
import { AdminApi } from "./admin-api.js";
import { getDashboardData } from "./demo-data.js";

const INTEGER_FORMATTER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const DECIMAL_FORMATTER = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

// User figures come from the backend; agent figures stay demonstrational until
// dialogs and agent runs are persisted.
const METRICS = Object.freeze([
  { key: "usersTotal", label: "Всего пользователей", hint: "зарегистрировано", icon: "◎", tone: "blue" },
  { key: "activeUsers", label: "Активные пользователи", hint: "входили за период", icon: "↗", tone: "green" },
  { key: "dialogs", label: "Диалоги", hint: "запущено с агентом", icon: "⌁", tone: "violet", demo: true },
  { key: "messages", label: "Сообщения", hint: "пользовательских и AI", icon: "✦", tone: "pink", demo: true },
]);

const DEMO_LABEL = "демо-данные";
const DEMO_TITLE = "Статистика агента пока не сохраняется";
const STATS_ERROR = "Не удалось загрузить статистику. Попробуйте обновить страницу";
const DEMO_ERROR = "Не удалось загрузить демонстрационные данные. Попробуйте выбрать другой период.";

const ROLE_LABELS = Object.freeze({
  admin: "администратор",
  user: "пользователь",
});

const TIME_FORMATTER = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" });
const DATE_FORMATTER = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" });
const DATE_YEAR_FORMATTER = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  year: "numeric",
});

const STATUS_LABELS = Object.freeze({
  active: "Активен",
  new: "Новый",
  inactive: "Неактивен",
});

const DEFAULT_ADMIN_SECTION = "#overview";

function formatInteger(value) {
  return INTEGER_FORMATTER.format(value).replaceAll("\u00a0", " ");
}

function formatDecimal(value) {
  return DECIMAL_FORMATTER.format(value);
}

function createElement(documentRef, tagName, className, text) {
  const element = documentRef.createElement(tagName);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function startOfDay(date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

export function formatActivity(timestamp, now = new Date()) {
  const date = new Date(timestamp);
  const time = TIME_FORMATTER.format(date);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days === 0) return `сегодня, ${time}`;
  if (days === 1) return `вчера, ${time}`;
  const formatter = date.getFullYear() === now.getFullYear() ? DATE_FORMATTER : DATE_YEAR_FORMATTER;
  return `${formatter.format(date)}, ${time}`;
}

function demoBadge(documentRef) {
  const badge = createElement(documentRef, "span", "adm-agent-demo", DEMO_LABEL);
  badge.setAttribute("title", DEMO_TITLE);
  return badge;
}

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase();
}

function renderMetrics(documentRef, container, stats, demo) {
  const cards = METRICS.map(metric => {
    const card = createElement(documentRef, "article", `adm-metric adm-metric-${metric.tone}`);
    card.dataset.metric = metric.key;
    card.dataset.source = metric.demo ? "demo" : "backend";

    const head = createElement(documentRef, "div", "adm-metric-head");
    head.append(
      createElement(documentRef, "span", "adm-metric-label", metric.label),
      createElement(documentRef, "span", "adm-metric-icon", metric.icon),
    );

    const value = createElement(
      documentRef,
      "strong",
      "adm-metric-value",
      formatInteger(metric.demo ? demo.metrics[metric.key] : stats[metric.key]),
    );
    const hint = createElement(documentRef, "span", "adm-metric-hint", metric.hint);
    card.append(head, value, hint);
    if (metric.demo) card.append(demoBadge(documentRef));
    return card;
  });
  container.replaceChildren(...cards);
}

function renderActivity(documentRef, container, description, data) {
  const maximum = Math.max(...data.activity.map(point => point.value), 1);
  const columns = data.activity.map(point => {
    const column = createElement(documentRef, "div", "adm-chart-column");
    const value = createElement(documentRef, "span", "adm-chart-value", formatInteger(point.value));
    const track = createElement(documentRef, "span", "adm-chart-track");
    const bar = createElement(documentRef, "span", "adm-chart-bar");
    bar.style.height = `${Math.max(12, Math.round((point.value / maximum) * 100))}%`;
    track.append(bar);
    const label = createElement(documentRef, "span", "adm-chart-label", point.label);
    column.setAttribute("aria-label", `${point.label}: ${formatInteger(point.value)}`);
    column.append(value, track, label);
    return column;
  });

  container.replaceChildren(...columns);
  description.textContent = `Активность за ${data.periodLabel}: ${data.activity
    .map(point => `${point.label}: ${formatInteger(point.value)}`)
    .join(", ")}.`;
}

function renderQuality(documentRef, container, data) {
  const success = createElement(documentRef, "div", "adm-quality-item");
  success.append(
    createElement(documentRef, "span", "adm-quality-label", "Успешные ответы"),
    createElement(documentRef, "strong", "adm-quality-value", `${formatDecimal(data.metrics.successRate)}%`),
    createElement(documentRef, "span", "adm-quality-note", "без ошибок агента"),
  );

  const latency = createElement(documentRef, "div", "adm-quality-item");
  latency.append(
    createElement(documentRef, "span", "adm-quality-label", "Среднее время"),
    createElement(documentRef, "strong", "adm-quality-value", `${formatDecimal(data.metrics.averageResponseSeconds)} с`),
    createElement(documentRef, "span", "adm-quality-note", "до полного ответа"),
  );

  const meter = createElement(documentRef, "div", "adm-quality-meter");
  const fill = createElement(documentRef, "span", "adm-quality-meter-fill");
  fill.style.width = `${data.metrics.successRate}%`;
  meter.setAttribute("aria-label", `Успешные ответы: ${formatDecimal(data.metrics.successRate)}%`);
  meter.append(fill);

  container.replaceChildren(success, latency, meter);
}

function renderUsers(documentRef, container, stats, now) {
  if (stats.recentUsers.length === 0) {
    const empty = createElement(documentRef, "p", "adm-users-empty", "Пользователей пока нет");
    empty.setAttribute("role", "listitem");
    container.replaceChildren(empty);
    return;
  }

  const rows = stats.recentUsers.map(user => {
    const row = createElement(documentRef, "article", "adm-user-row");
    row.setAttribute("role", "listitem");

    const identity = createElement(documentRef, "div", "adm-user-identity");
    const avatar = createElement(documentRef, "span", "adm-user-avatar", initials(user.login));
    const details = createElement(documentRef, "span", "adm-user-details");
    details.append(
      createElement(documentRef, "strong", "", user.login),
      createElement(documentRef, "small", "", ROLE_LABELS[user.role]),
    );
    identity.append(avatar, details);

    const activity = createElement(
      documentRef,
      "span",
      "adm-user-cell",
      user.lastActiveAt ? formatActivity(user.lastActiveAt, now) : "ещё не входил",
    );
    activity.dataset.label = "Активность";
    // Dialogs are not linked to users yet.
    const dialogs = createElement(documentRef, "span", "adm-user-cell", "—");
    dialogs.dataset.label = "Диалоги";
    dialogs.setAttribute("title", "Диалоги пока не связаны с пользователями");
    const status = createElement(
      documentRef,
      "span",
      `adm-user-status adm-user-status-${user.status}`,
      STATUS_LABELS[user.status],
    );
    status.dataset.label = "Статус";

    row.append(identity, activity, dialogs, status);
    return row;
  });
  container.replaceChildren(...rows);
}

function clearDynamicContent(elements) {
  elements.metrics.replaceChildren();
  elements.activity.replaceChildren();
  elements.quality.replaceChildren();
  elements.users.replaceChildren();
  elements.chartDescription.textContent = "";
}

export function mountAdminNavigation(
  documentRef,
  windowRef = typeof window === "undefined" ? null : window,
) {
  const links = [...documentRef.querySelectorAll("[data-admin-nav]")];
  if (links.length === 0) return false;

  const supportedSections = new Set(links.map(link => link.getAttribute("href")));
  const fallbackSection = supportedSections.has(DEFAULT_ADMIN_SECTION)
    ? DEFAULT_ADMIN_SECTION
    : links[0].getAttribute("href");

  const activate = hash => {
    const activeSection = supportedSections.has(hash) ? hash : fallbackSection;
    for (const link of links) {
      if (link.getAttribute("href") === activeSection) {
        link.setAttribute("aria-current", "location");
      } else {
        link.removeAttribute("aria-current");
      }
    }
  };

  for (const link of links) {
    link.addEventListener("click", () => activate(link.getAttribute("href")));
  }
  windowRef?.addEventListener("hashchange", () => activate(windowRef.location.hash));

  activate(windowRef?.location?.hash ?? "");
  return true;
}

export async function mountDashboard(
  documentRef,
  {
    loadStats,
    onAuthError = () => {},
    getData = getDashboardData,
    initialPeriod = "30",
    now = () => new Date(),
  } = {},
) {
  const elements = {
    content: documentRef.querySelector("#adminContent"),
    error: documentRef.querySelector("#adminError"),
    periodLabel: documentRef.querySelector("#adminPeriodLabel"),
    comparison: documentRef.querySelector("#adminComparison"),
    metrics: documentRef.querySelector("#adminMetrics"),
    activity: documentRef.querySelector("#adminActivity"),
    chartDescription: documentRef.querySelector("#adminChartDescription"),
    quality: documentRef.querySelector("#adminQuality"),
    users: documentRef.querySelector("#adminUsers"),
  };
  const periodButtons = [...documentRef.querySelectorAll("[data-period]")];

  if (typeof loadStats !== "function" || Object.values(elements).some(element => !element)) {
    return false;
  }

  let busy = false;
  const setBusy = value => {
    busy = value;
    for (const button of periodButtons) button.disabled = value;
  };

  const showError = message => {
    clearDynamicContent(elements);
    elements.content.hidden = true;
    elements.error.hidden = false;
    elements.error.textContent = message;
    return false;
  };

  const render = async period => {
    const demo = getData(period);
    if (!demo) return showError(DEMO_ERROR);

    setBusy(true);
    let stats;
    try {
      stats = await loadStats(period);
    } catch (error) {
      setBusy(false);
      if (error?.code === "unauthorized" || error?.code === "forbidden") {
        onAuthError(error.code);
        return false;
      }
      return showError(STATS_ERROR);
    }
    setBusy(false);

    elements.error.hidden = true;
    elements.error.textContent = "";
    elements.content.hidden = false;
    elements.periodLabel.textContent = demo.periodLabel;
    elements.comparison.textContent = `Новых пользователей: ${formatInteger(stats.newUsers)}`;
    for (const button of periodButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.period === demo.period));
    }
    renderMetrics(documentRef, elements.metrics, stats, demo);
    renderActivity(documentRef, elements.activity, elements.chartDescription, demo);
    renderQuality(documentRef, elements.quality, demo);
    renderUsers(documentRef, elements.users, stats, now());
    return true;
  };

  for (const button of periodButtons) {
    button.addEventListener("click", () => {
      if (!busy) void render(button.dataset.period);
    });
  }

  return render(initialPeriod);
}

function mountLogout(documentRef, { api, redirect }) {
  const button = documentRef.querySelector("#adminLogout");
  const error = documentRef.querySelector("#adminLogoutError");
  if (!button) return;
  let pending = false;

  // Cookies are cleared by the backend only on success, so a failed logout stays.
  button.addEventListener("click", async () => {
    if (pending) return;
    pending = true;
    button.disabled = true;
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
    try {
      await api.logout();
    } catch {
      pending = false;
      button.disabled = false;
      if (error) {
        error.hidden = false;
        error.textContent = "Не удалось выйти. Попробуйте ещё раз";
      }
      return;
    }
    redirect(LOGIN_PATH);
  });
}

// Hides demo data from non-administrators; a future admin API must still
// check the role on the backend.
export async function mountAdminPage(
  documentRef,
  { api, adminApi, redirect, windowRef, ...dashboardOptions },
) {
  const session = await checkSession(api);
  if (session.status === SESSION.ANONYMOUS) {
    redirect(LOGIN_PATH);
    return false;
  }
  if (session.status === SESSION.UNAVAILABLE) {
    const content = documentRef.querySelector("#adminContent");
    const error = documentRef.querySelector("#adminError");
    if (content) content.hidden = true;
    if (error) {
      error.hidden = false;
      error.textContent = "Сервис временно недоступен. Обновите страницу позже.";
    }
    return false;
  }
  if (session.user.role !== "admin") {
    redirect(CHAT_PATH);
    return false;
  }
  mountLogout(documentRef, { api, redirect });
  mountAdminNavigation(documentRef, windowRef);
  return mountDashboard(documentRef, {
    loadStats: period => adminApi.stats(period),
    onAuthError: code => redirect(code === "forbidden" ? CHAT_PATH : LOGIN_PATH),
    ...dashboardOptions,
  });
}

if (typeof document !== "undefined") {
  void mountAdminPage(document, {
    api: new AuthApi(),
    adminApi: new AdminApi(),
    redirect: url => window.location.replace(url),
    windowRef: window,
  });
}
