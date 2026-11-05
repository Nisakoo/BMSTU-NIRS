import { AuthApi, AuthApiError } from "../auth-api.js";
import { CHAT_PATH, LOGIN_PATH, SESSION, checkSession, refreshSession } from "../auth-session.js";
import { mountPasswordSettings } from "../password-settings.js";
import { AdminApi } from "./admin-api.js";

const INTEGER_FORMATTER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const SCORE_FORMATTER = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
// Answer ratings go from 1 to 5.
const SCORES = Object.freeze([1, 2, 3, 4, 5]);

// Every figure comes from the backend; a dialog counts once it has a message.
const METRICS = Object.freeze([
  { key: "usersTotal", label: "Всего пользователей", hint: "зарегистрировано", icon: "◎", tone: "blue" },
  { key: "activeUsers", label: "Активные пользователи", hint: "входили за период", icon: "↗", tone: "green" },
  { key: "dialogs", label: "Диалоги", hint: "историй за период", icon: "⌁", tone: "violet" },
  { key: "messages", label: "Сообщения", hint: "пользовательских и AI", icon: "✦", tone: "pink" },
]);

const PERIOD_LABELS = Object.freeze({ 7: "7 дней", 30: "30 дней", 90: "90 дней" });
const STATS_ERROR = "Не удалось загрузить статистику. Попробуйте обновить страницу";

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

const DEFAULT_ADMIN_SECTION = "#overview";
// Short enough for ten columns on a phone.
const CHART_DATE_FORMATTER = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit" });

const REPORT_REASON_LABELS = Object.freeze({
  scary: "Страшно",
  rude: "Грубо или обидно",
  wrong: "Неправильно или непонятно",
  other: "Другое",
});
const REPORT_STATUS_LABELS = Object.freeze({
  new: "Новая",
  resolved: "Рассмотрена",
  dismissed: "Отклонена",
});
// What the administrator can do with a report in each status.
const REPORT_ACTIONS = Object.freeze({
  new: [["resolved", "Рассмотрено"], ["dismissed", "Отклонить"]],
  resolved: [["new", "Вернуть в новые"]],
  dismissed: [["new", "Вернуть в новые"]],
});

function formatInteger(value) {
  return INTEGER_FORMATTER.format(value).replaceAll("\u00a0", " ");
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

// By the local hour of the browser.
export function greetingFor(date) {
  const hour = date.getHours();
  if (hour >= 5 && hour < 12) return "Доброе утро";
  if (hour >= 12 && hour < 17) return "Добрый день";
  if (hour >= 17 && hour < 23) return "Добрый вечер";
  return "Доброй ночи";
}

export function formatDay(timestamp, now = new Date()) {
  const date = new Date(timestamp);
  const days = Math.round((startOfDay(now) - startOfDay(date)) / 86_400_000);
  if (days === 0) return "сегодня";
  if (days === 1) return "вчера";
  const formatter = date.getFullYear() === now.getFullYear() ? DATE_FORMATTER : DATE_YEAR_FORMATTER;
  return formatter.format(date);
}

export function formatActivity(timestamp, now = new Date()) {
  return `${formatDay(timestamp, now)}, ${TIME_FORMATTER.format(new Date(timestamp))}`;
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

function renderMetrics(documentRef, container, stats) {
  const cards = METRICS.map(metric => {
    const card = createElement(documentRef, "article", `adm-metric adm-metric-${metric.tone}`);
    card.dataset.metric = metric.key;

    const head = createElement(documentRef, "div", "adm-metric-head");
    head.append(
      createElement(documentRef, "span", "adm-metric-label", metric.label),
      createElement(documentRef, "span", "adm-metric-icon", metric.icon),
    );

    const value = createElement(
      documentRef,
      "strong",
      "adm-metric-value",
      formatInteger(stats[metric.key]),
    );
    const hint = createElement(documentRef, "span", "adm-metric-hint", metric.hint);
    card.append(head, value, hint);
    return card;
  });
  container.replaceChildren(...cards);
}

// Stories created in each bucket of the period, labelled by the bucket start.
function renderActivity(documentRef, container, description, stats) {
  const points = stats.activity.map(point => ({
    label: CHART_DATE_FORMATTER.format(new Date(point.start)),
    value: point.dialogs,
  }));
  const maximum = Math.max(...points.map(point => point.value), 1);
  const columns = points.map(point => {
    const column = createElement(documentRef, "div", "adm-chart-column");
    const value = createElement(documentRef, "span", "adm-chart-value", formatInteger(point.value));
    const track = createElement(documentRef, "span", "adm-chart-track");
    // An empty bucket keeps its value and date but draws no bar.
    const bar = createElement(documentRef, "span", point.value === 0 ? "adm-chart-bar adm-chart-bar-empty" : "adm-chart-bar");
    const height = point.value === 0 ? 0 : Math.max(12, Math.round((point.value / maximum) * 100));
    bar.style.height = `${height}%`;
    track.append(bar);
    const label = createElement(documentRef, "span", "adm-chart-label", point.label);
    column.setAttribute("aria-label", `${point.label}: ${formatInteger(point.value)}`);
    column.append(value, track, label);
    return column;
  });

  const periodLabel = PERIOD_LABELS[stats.period];
  if (stats.dialogs === 0) {
    container.replaceChildren(...columns, createElement(documentRef, "p", "adm-chart-empty", "Историй за период нет"));
    description.textContent = `Историй за ${periodLabel} нет.`;
    return;
  }
  container.replaceChildren(...columns);
  description.textContent = `Истории за ${periodLabel}: ${points
    .map(point => `${point.label}: ${formatInteger(point.value)}`)
    .join(", ")}.`;
}

// Ratings of answers created in the period: the average score and how many got each score.
function renderQuality(documentRef, container, feedback) {
  const rated = feedback.ratedAnswers;
  const coverage = `оценено ${formatInteger(rated)} из ${formatInteger(feedback.answersTotal)} ответов`;
  const summary = createElement(documentRef, "div", "adm-quality-summary");

  if (rated === 0) {
    summary.append(createElement(documentRef, "strong", "adm-quality-empty", "Оценок пока нет"));
  } else {
    const average = feedback.counts.reduce((sum, count, index) => sum + count * (index + 1), 0) / rated;
    const value = createElement(documentRef, "div", "adm-quality-score");
    value.append(
      createElement(documentRef, "strong", "adm-quality-average", SCORE_FORMATTER.format(average)),
      createElement(documentRef, "span", "adm-quality-scale", "из 5"),
    );
    summary.append(value);
  }
  summary.append(createElement(documentRef, "span", "adm-quality-note", coverage));

  const rows = SCORES.map((score, index) => {
    const count = feedback.counts[index];
    const row = createElement(documentRef, "div", "adm-quality-row");
    row.setAttribute("aria-label", `Оценка ${score} из 5: ${formatInteger(count)}`);
    const bar = createElement(documentRef, "span", "adm-quality-bar");
    const fill = createElement(documentRef, "span", "adm-quality-bar-fill");
    fill.style.width = `${rated === 0 ? 0 : Math.round((count * 100) / rated)}%`;
    bar.append(fill);
    row.append(
      createElement(documentRef, "span", "adm-quality-row-score", String(score)),
      bar,
      createElement(documentRef, "span", "adm-quality-count", formatInteger(count)),
    );
    return row;
  }).reverse();

  container.replaceChildren(summary, ...rows);
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
    const dialogs = createElement(documentRef, "span", "adm-user-cell", formatInteger(user.dialogs));
    dialogs.dataset.label = "Диалоги";
    const registered = createElement(documentRef, "span", "adm-user-cell", formatDay(user.registeredAt, now));
    registered.dataset.label = "Регистрация";

    row.append(identity, activity, dialogs, registered);
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

// The section whose top passed this share of the window height is the one read.
const NAV_READING_LINE = 0.35;
// How long a clicked section holds when the browser has no scrollend event.
const NAV_HOLD_MS = 1000;

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

  // A chosen section holds until its smooth scroll ends, so passing sections
  // and a page that bottoms out early do not take the highlight away.
  let held = false;
  let holdTimer = null;
  const release = () => {
    held = false;
    if (holdTimer !== null) windowRef?.clearTimeout?.(holdTimer);
    holdTimer = null;
  };
  const choose = hash => {
    activate(hash);
    release();
    held = true;
    holdTimer = windowRef?.setTimeout?.(release, NAV_HOLD_MS) ?? null;
  };

  const visibleSections = () => links
    .map(link => {
      const href = link.getAttribute("href");
      return { href, rect: documentRef.querySelector?.(href)?.getBoundingClientRect?.() };
    })
    .filter(({ rect }) => rect && rect.height > 0);

  const follow = () => {
    if (held || !windowRef) return;
    const sections = visibleSections();
    if (sections.length === 0) return;
    const pageHeight = documentRef.documentElement?.scrollHeight ?? 0;
    const atBottom = pageHeight > windowRef.innerHeight
      && windowRef.scrollY + windowRef.innerHeight >= pageHeight - 2;
    if (atBottom) {
      activate(sections.at(-1).href);
      return;
    }
    const line = windowRef.innerHeight * NAV_READING_LINE;
    const passed = sections.filter(({ rect }) => rect.top <= line);
    activate(passed.at(-1)?.href ?? sections[0].href);
  };

  let framePending = false;
  const scheduleFollow = () => {
    if (framePending || held) return;
    framePending = true;
    const run = () => {
      framePending = false;
      follow();
    };
    if (windowRef?.requestAnimationFrame) windowRef.requestAnimationFrame(run);
    else run();
  };

  for (const link of links) {
    link.addEventListener("click", () => choose(link.getAttribute("href")));
  }
  windowRef?.addEventListener("hashchange", () => choose(windowRef.location.hash));
  windowRef?.addEventListener("scroll", scheduleFollow);
  windowRef?.addEventListener("resize", scheduleFollow);
  windowRef?.addEventListener("scrollend", release);

  activate(windowRef?.location?.hash ?? "");
  return true;
}

export async function mountDashboard(
  documentRef,
  {
    loadStats,
    onAuthError = () => {},
    onStats = () => {},
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
    elements.periodLabel.textContent = PERIOD_LABELS[period];
    elements.comparison.textContent = `Новых пользователей: ${formatInteger(stats.newUsers)}`;
    for (const button of periodButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.period === period));
    }
    renderMetrics(documentRef, elements.metrics, stats);
    renderActivity(documentRef, elements.activity, elements.chartDescription, stats);
    renderQuality(documentRef, elements.quality, stats.feedback);
    renderUsers(documentRef, elements.users, stats, now());
    onStats(stats);
    return true;
  };

  for (const button of periodButtons) {
    button.addEventListener("click", () => {
      if (!busy) void render(button.dataset.period);
    });
  }

  return render(initialPeriod);
}

function reportText(documentRef, label, text) {
  const block = createElement(documentRef, "div", "adm-report-text");
  block.append(
    createElement(documentRef, "span", "adm-report-label", label),
    createElement(documentRef, "p", "adm-report-body", text ?? "—"),
  );
  return block;
}

// Reports on answers: the texts are shown as text, the author is never known here.
export function mountReports(
  documentRef,
  { loadReports, changeStatus, onAuthError = () => {}, now = () => new Date() } = {},
) {
  const list = documentRef.querySelector("#adminReports");
  const error = documentRef.querySelector("#adminReportsError");
  const badge = documentRef.querySelector("#adminReportsBadge");
  const filters = [...documentRef.querySelectorAll("[data-report-filter]")];
  if (!list || !error || !badge || typeof loadReports !== "function" || typeof changeStatus !== "function") {
    return null;
  }

  let filter = "new";
  let newCount = 0;
  let request = 0;

  const setNewCount = count => {
    newCount = Math.max(0, count);
    badge.textContent = formatInteger(newCount);
    badge.hidden = newCount === 0;
  };

  const fail = (failure, message) => {
    if (failure?.code === "unauthorized" || failure?.code === "forbidden") {
      onAuthError(failure.code);
      return;
    }
    error.hidden = false;
    error.textContent = message;
  };

  const act = async (report, status, buttons) => {
    for (const button of buttons) button.disabled = true;
    try {
      await changeStatus(report.id, status);
    } catch (failure) {
      for (const button of buttons) button.disabled = false;
      fail(failure, "Не удалось обновить жалобу");
      return;
    }
    if (report.status === "new") setNewCount(newCount - 1);
    else if (status === "new") setNewCount(newCount + 1);
    await load();
  };

  const renderReport = report => {
    const card = createElement(documentRef, "article", `adm-report adm-report-${report.status}`);
    card.dataset.reportId = String(report.id);
    card.setAttribute("role", "listitem");

    const head = createElement(documentRef, "div", "adm-report-head");
    head.append(
      createElement(documentRef, "span", "adm-report-reason", REPORT_REASON_LABELS[report.reason]),
      createElement(documentRef, "span", "adm-report-status", REPORT_STATUS_LABELS[report.status]),
      createElement(documentRef, "span", "adm-report-date", formatActivity(report.createdAt, now())),
    );
    if (report.dialogDeleted) {
      head.append(createElement(documentRef, "span", "adm-report-deleted", "история удалена"));
    }
    card.append(head);
    if (report.comment) {
      card.append(createElement(documentRef, "p", "adm-report-comment", `«${report.comment}»`));
    }
    card.append(
      reportText(documentRef, "Запрос", report.requestText),
      reportText(documentRef, "Ответ", report.answerText),
    );

    const actions = createElement(documentRef, "div", "adm-report-actions");
    const buttons = REPORT_ACTIONS[report.status].map(([status, label]) => {
      const button = createElement(documentRef, "button", `adm-report-action adm-report-action-${status}`, label);
      button.type = "button";
      button.dataset.status = status;
      return button;
    });
    for (const button of buttons) {
      button.addEventListener("click", () => void act(report, button.dataset.status, buttons));
    }
    actions.append(...buttons);
    card.append(actions);
    return card;
  };

  const load = async () => {
    const current = ++request;
    for (const button of filters) {
      button.setAttribute("aria-pressed", String(button.dataset.reportFilter === filter));
    }
    let reports;
    try {
      reports = await loadReports(filter);
    } catch (failure) {
      if (current !== request) return;
      list.replaceChildren();
      fail(failure, "Не удалось загрузить жалобы");
      return;
    }
    if (current !== request) return;
    error.hidden = true;
    error.textContent = "";
    if (reports.length === 0) {
      const empty = createElement(documentRef, "p", "adm-reports-empty", "Жалоб нет");
      empty.setAttribute("role", "listitem");
      list.replaceChildren(empty);
      return;
    }
    list.replaceChildren(...reports.map(renderReport));
  };

  for (const button of filters) {
    button.addEventListener("click", () => {
      filter = button.dataset.reportFilter;
      void load();
    });
  }
  setNewCount(0);
  void load();
  return { setNewCount };
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

// Retries the password change once after a 401 if refresh renews the session.
function changePasswordWithSession(api, redirect) {
  return async passwords => {
    try {
      return await api.changePassword(passwords);
    } catch (error) {
      if (error?.code !== "unauthorized") throw error;
    }
    const session = await refreshSession(api);
    if (session.status === SESSION.ANONYMOUS) {
      redirect(LOGIN_PATH);
      throw new AuthApiError("unauthorized");
    }
    if (session.status !== SESSION.USER) throw new AuthApiError("unavailable");
    try {
      return await api.changePassword(passwords);
    } catch (error) {
      if (error?.code === "unauthorized") redirect(LOGIN_PATH);
      throw error;
    }
  };
}

function mountSettings(documentRef, { api, redirect }) {
  const button = documentRef.querySelector("#adminSettingsButton");
  if (!button) return;
  let leaving = false;
  const leave = url => {
    leaving = true;
    redirect(url);
  };
  const settings = mountPasswordSettings({
    button,
    dialog: documentRef.querySelector("#adminSettings"),
    close: documentRef.querySelector("#adminSettingsClose"),
    form: documentRef.querySelector("#adminPasswordForm"),
    currentPassword: documentRef.querySelector("#adminCurrentPassword"),
    newPassword: documentRef.querySelector("#adminNewPassword"),
    repeatPassword: documentRef.querySelector("#adminRepeatPassword"),
    save: documentRef.querySelector("#adminPasswordSave"),
    status: documentRef.querySelector("#adminPasswordStatus"),
    changePassword: changePasswordWithSession(api, leave),
    isUnloading: () => leaving,
  });
  documentRef.addEventListener?.("keydown", event => {
    if (event.key === "Escape" && settings.isOpen()) settings.close();
  });
}

// Shows the panel to administrators only; the backend checks the role as well.
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
  const greeting = documentRef.querySelector("#adminGreeting");
  if (greeting) {
    greeting.textContent = `${greetingFor((dashboardOptions.now ?? (() => new Date()))())}, ${session.user.login}`;
  }
  mountLogout(documentRef, { api, redirect });
  mountSettings(documentRef, { api, redirect });
  mountAdminNavigation(documentRef, windowRef);
  const onAuthError = code => redirect(code === "forbidden" ? CHAT_PATH : LOGIN_PATH);
  const reports = mountReports(documentRef, {
    loadReports: filter => adminApi.listReports(filter),
    changeStatus: (reportId, status) => adminApi.setReportStatus(reportId, status),
    onAuthError,
    now: dashboardOptions.now,
  });
  return mountDashboard(documentRef, {
    loadStats: period => adminApi.stats(period),
    onAuthError,
    onStats: stats => reports?.setNewCount(stats.reportsNew),
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
