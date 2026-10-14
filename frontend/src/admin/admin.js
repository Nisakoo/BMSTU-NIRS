import { getDashboardData } from "./demo-data.js";

const INTEGER_FORMATTER = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 });
const DECIMAL_FORMATTER = new Intl.NumberFormat("ru-RU", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

const METRICS = Object.freeze([
  { key: "usersTotal", label: "Всего пользователей", hint: "в демонстрационной базе", icon: "◎", tone: "blue" },
  { key: "activeUsers", label: "Активные пользователи", hint: "за выбранный период", icon: "↗", tone: "green" },
  { key: "dialogs", label: "Диалоги", hint: "запущено с агентом", icon: "⌁", tone: "violet" },
  { key: "messages", label: "Сообщения", hint: "пользовательских и AI", icon: "✦", tone: "pink" },
]);

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

function initials(name) {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map(part => part[0])
    .join("")
    .toUpperCase();
}

function renderMetrics(documentRef, container, data) {
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
      formatInteger(data.metrics[metric.key]),
    );
    const hint = createElement(documentRef, "span", "adm-metric-hint", metric.hint);
    card.append(head, value, hint);
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

function renderUsers(documentRef, container, data) {
  const rows = data.recentUsers.map(user => {
    const row = createElement(documentRef, "article", "adm-user-row");
    row.setAttribute("role", "listitem");

    const identity = createElement(documentRef, "div", "adm-user-identity");
    const avatar = createElement(documentRef, "span", "adm-user-avatar", initials(user.name));
    const details = createElement(documentRef, "span", "adm-user-details");
    details.append(
      createElement(documentRef, "strong", "", user.name),
      createElement(documentRef, "small", "", user.id),
    );
    identity.append(avatar, details);

    const activity = createElement(documentRef, "span", "adm-user-cell", user.lastActive);
    activity.dataset.label = "Активность";
    const dialogs = createElement(documentRef, "span", "adm-user-cell", formatInteger(user.dialogs));
    dialogs.dataset.label = "Диалоги";
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

export function mountDashboard(
  documentRef,
  { getData = getDashboardData, initialPeriod = "30" } = {},
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

  if (Object.values(elements).some(element => !element)) return false;

  const render = period => {
    const data = getData(period);
    if (!data) {
      clearDynamicContent(elements);
      elements.content.hidden = true;
      elements.error.hidden = false;
      elements.error.textContent = "Не удалось загрузить демонстрационные данные. Попробуйте выбрать другой период.";
      return false;
    }

    elements.error.hidden = true;
    elements.error.textContent = "";
    elements.content.hidden = false;
    elements.periodLabel.textContent = data.periodLabel;
    elements.comparison.textContent = data.comparison;
    for (const button of periodButtons) {
      button.setAttribute("aria-pressed", String(button.dataset.period === data.period));
    }
    renderMetrics(documentRef, elements.metrics, data);
    renderActivity(documentRef, elements.activity, elements.chartDescription, data);
    renderQuality(documentRef, elements.quality, data);
    renderUsers(documentRef, elements.users, data);
    return true;
  };

  for (const button of periodButtons) {
    button.addEventListener("click", () => render(button.dataset.period));
  }

  render(initialPeriod);
  return true;
}

if (typeof document !== "undefined") {
  mountAdminNavigation(document);
  mountDashboard(document);
}
