import "./no-web-locks.js";
import assert from "node:assert/strict";
import test from "node:test";

import {
  formatActivity,
  formatDay,
  greetingFor,
  mountAdminNavigation,
  mountAdminPage,
  mountDashboard,
  mountReports,
} from "../src/admin/admin.js";
import { AuthApiError } from "../src/auth-api.js";

class FakeElement {
  constructor(tagName = "div") {
    this.tagName = tagName.toUpperCase();
    this.children = [];
    this.listeners = new Map();
    this.attributes = new Map();
    this.dataset = {};
    this.hidden = false;
    this._textContent = "";
    this.className = "";
    this.style = {};
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  click() {
    for (const listener of this.listeners.get("click") ?? []) listener();
  }

  dispatch(type, event = {}) {
    let result;
    const dispatched = { preventDefault() {}, ...event };
    for (const listener of this.listeners.get(type) ?? []) result = listener(dispatched);
    return result;
  }

  focus() {
    FakeElement.focused = this;
  }

  append(...children) {
    this.children.push(...children);
  }

  replaceChildren(...children) {
    this.children = children;
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  removeAttribute(name) {
    this.attributes.delete(name);
  }

  set textContent(value) {
    this._textContent = String(value);
    this.children = [];
  }

  get textContent() {
    return this._textContent + this.children.map(child => child.textContent).join("");
  }

  set innerHTML(_value) {
    throw new Error("dynamic innerHTML is forbidden");
  }
}

class FakeWindow {
  constructor(hash = "") {
    this.location = { hash };
    this.listeners = new Map();
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  dispatch(type) {
    for (const listener of this.listeners.get(type) ?? []) listener();
  }
}

function createNavigationHarness(hash = "") {
  const links = [
    ["#overview", "Обзор"],
    ["#activity", "Активность"],
    ["#users", "Пользователи"],
  ].map(([href, label]) => {
    const link = new FakeElement("a");
    link.setAttribute("href", href);
    link.textContent = label;
    return link;
  });
  const documentRef = {
    querySelectorAll: selector => selector === "[data-admin-nav]" ? links : [],
  };
  return { documentRef, links, windowRef: new FakeWindow(hash) };
}

function activeNavigationLabels(links) {
  return links
    .filter(link => link.getAttribute("aria-current") === "location")
    .map(link => link.textContent);
}

function createHarness() {
  const ids = [
    "#adminContent",
    "#adminError",
    "#adminPeriodLabel",
    "#adminComparison",
    "#adminMetrics",
    "#adminActivity",
    "#adminChartDescription",
    "#adminQuality",
    "#adminUsers",
    "#adminLogout",
    "#adminLogoutError",
    "#adminReports",
    "#adminReportsError",
    "#adminReportsBadge",
    "#adminGreeting",
    "#adminSettingsButton",
    "#adminSettings",
    "#adminSettingsClose",
    "#adminPasswordForm",
    "#adminCurrentPassword",
    "#adminNewPassword",
    "#adminRepeatPassword",
    "#adminPasswordSave",
    "#adminPasswordStatus",
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  elements["#adminSettings"].hidden = true;
  const buttons = ["7", "30", "90"].map(period => {
    const button = new FakeElement("button");
    button.dataset.period = period;
    button.setAttribute("aria-pressed", "false");
    return button;
  });
  const filters = ["new", "resolved", "dismissed", "all"].map(filter => {
    const button = new FakeElement("button");
    button.dataset.reportFilter = filter;
    button.setAttribute("aria-pressed", String(filter === "new"));
    return button;
  });
  const lists = { "[data-period]": buttons, "[data-report-filter]": filters };
  const documentListeners = new Map();
  const documentRef = {
    querySelector: selector => elements[selector] ?? null,
    querySelectorAll: selector => lists[selector] ?? [],
    createElement: tagName => new FakeElement(tagName),
    addEventListener: (type, listener) => {
      documentListeners.set(type, [...(documentListeners.get(type) ?? []), listener]);
    },
    dispatch: (type, event) => {
      for (const listener of documentListeners.get(type) ?? []) listener(event);
    },
  };
  return { documentRef, elements, buttons, filters };
}

const NOW = new Date(2026, 9, 16, 15, 0);
const BUCKET_DAYS = { 7: 1, 30: 3, 90: 10 };

function activityFor(period, counts) {
  const since = NOW.getTime() - Number(period) * 86_400_000;
  const activity = counts.map((dialogs, index) => ({
    start: new Date(since + index * BUCKET_DAYS[period] * 86_400_000).toISOString(),
    dialogs,
  }));
  const dialogs = counts.reduce((sum, count) => sum + count, 0);
  return { dialogs, messages: dialogs * 6, activity };
}

function statsFor(period, overrides = {}) {
  return {
    period,
    usersTotal: 1234,
    activeUsers: { 7: 5, 30: 9, 90: 14 }[period],
    newUsers: { 7: 2, 30: 4, 90: 8 }[period],
    recentUsers: [
      {
        id: "user-1",
        login: "Krosh",
        role: "user",
        registeredAt: new Date(2026, 9, 15, 9, 0).toISOString(),
        lastActiveAt: new Date(2026, 9, 16, 12, 48).toISOString(),
        status: "new",
        dialogs: 12,
      },
      {
        id: "user-2",
        login: "Sovunya",
        role: "admin",
        registeredAt: new Date(2026, 5, 1, 9, 0).toISOString(),
        lastActiveAt: new Date(2026, 9, 15, 21, 17).toISOString(),
        status: "active",
        dialogs: 1234,
      },
      {
        id: "user-3",
        login: "<b>Pin</b>",
        role: "user",
        registeredAt: new Date(2025, 0, 2, 9, 0).toISOString(),
        lastActiveAt: null,
        status: "inactive",
        dialogs: 0,
      },
    ],
    feedback: { answersTotal: 10, ratedAnswers: 5, counts: [1, 0, 1, 1, 2] },
    reportsNew: 3,
    ...activityFor(period, { 7: [0, 1, 2, 0, 3, 1, 4], 30: [5, 0, 2, 1, 0, 3, 4, 2, 1, 6], 90: [9, 8, 0, 7, 6, 5, 4, 3, 10] }[period]),
    ...overrides,
  };
}

function recordingLoader(respond = period => Promise.resolve(statsFor(period))) {
  const calls = [];
  const loadStats = period => (calls.push(period), respond(period));
  return { calls, loadStats };
}

async function mountWithStats(options = {}) {
  const ui = createHarness();
  const loader = recordingLoader(options.respond);
  const authErrors = [];
  const mounted = await mountDashboard(ui.documentRef, {
    loadStats: loader.loadStats,
    onAuthError: code => authErrors.push(code),
    now: () => NOW,
    ...options.dashboard,
  });
  return { ...ui, ...loader, authErrors, mounted };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test("dashboard shows backend user figures for 30 days by default", async () => {
  const ui = await mountWithStats();

  assert.equal(ui.mounted, true);
  assert.deepEqual(ui.calls, ["30"]);
  assert.equal(ui.elements["#adminContent"].hidden, false);
  assert.equal(ui.elements["#adminError"].hidden, true);
  assert.equal(ui.elements["#adminPeriodLabel"].textContent, "30 дней");
  assert.equal(ui.elements["#adminComparison"].textContent, "Новых пользователей: 4");
  const [total, active] = ui.elements["#adminMetrics"].children;
  assert.match(total.textContent, /1 234/);
  assert.match(active.textContent, /9/);
  assert.equal(ui.buttons[1].getAttribute("aria-pressed"), "true");
});

test("dialog and message cards show backend figures without a demo label", async () => {
  const ui = await mountWithStats();
  const cards = ui.elements["#adminMetrics"].children;

  assert.deepEqual(cards.map(card => card.dataset.metric), ["usersTotal", "activeUsers", "dialogs", "messages"]);
  assert.equal(find(cards[2], "adm-metric-value").textContent, "24");
  assert.equal(find(cards[3], "adm-metric-value").textContent, "144");
  for (const element of [...cards, ui.elements["#adminActivity"], ui.elements["#adminQuality"], ui.elements["#adminUsers"]]) {
    assert.doesNotMatch(element.textContent, /демо/);
  }
});

test("recent users show login, role, activity time, registration date and their stories", async () => {
  const ui = await mountWithStats();
  const rows = ui.elements["#adminUsers"].children;

  assert.equal(rows.length, 3);
  assert.match(rows[0].textContent, /Krosh/);
  assert.match(rows[0].textContent, /пользователь/);
  assert.match(rows[0].textContent, /сегодня, 12:48/);
  assert.equal(rows[0].children[3].textContent, "вчера");
  assert.equal(rows[0].children[3].dataset.label, "Регистрация");
  assert.match(rows[1].textContent, /администратор/);
  assert.match(rows[1].textContent, /вчера, 21:17/);
  assert.match(rows[1].children[3].textContent, /^1 июн\.?$/);
  assert.match(rows[2].textContent, /ещё не входил/);
  assert.match(rows[2].children[3].textContent, /^2 янв\.? 2025/);
  for (const row of rows) assert.doesNotMatch(row.textContent, /Новый|Активен|Неактивен/);
  assert.equal(rows[0].children[2].textContent, "12");
  assert.equal(rows[1].children[2].textContent, "1 234");
  assert.equal(rows[2].children[2].textContent, "0");
  assert.equal(rows[2].children[0].children[1].children[0].textContent, "<b>Pin</b>");
});

test("period buttons reload statistics and are locked while loading", async () => {
  let finish;
  const ui = await mountWithStats({
    respond: period => period === "30"
      ? Promise.resolve(statsFor(period))
      : new Promise(resolve => { finish = () => resolve(statsFor(period)); }),
  });

  ui.buttons[2].click();
  assert.equal(ui.buttons.every(button => button.disabled), true);
  ui.buttons[0].click();
  assert.deepEqual(ui.calls, ["30", "90"]);

  finish();
  await settle();
  assert.equal(ui.buttons.every(button => button.disabled), false);
  assert.equal(ui.elements["#adminPeriodLabel"].textContent, "90 дней");
  assert.match(ui.elements["#adminMetrics"].children[1].textContent, /14/);
  assert.equal(find(ui.elements["#adminMetrics"].children[2], "adm-metric-value").textContent, "52");
  assert.equal(ui.elements["#adminActivity"].children.length, 9);
  assert.equal(ui.elements["#adminComparison"].textContent, "Новых пользователей: 8");
  assert.equal(ui.buttons[2].getAttribute("aria-pressed"), "true");
});

test("a failed statistics request shows an error without user data", async () => {
  for (const code of ["unavailable", "invalid_response"]) {
    const ui = await mountWithStats({ respond: () => Promise.reject({ code }) });

    assert.equal(ui.mounted, false);
    assert.equal(ui.elements["#adminContent"].hidden, true);
    assert.equal(ui.elements["#adminError"].hidden, false);
    assert.match(ui.elements["#adminError"].textContent, /Не удалось загрузить статистику/);
    assert.equal(ui.elements["#adminUsers"].children.length, 0);
    assert.equal(ui.elements["#adminMetrics"].children.length, 0);
    assert.deepEqual(ui.authErrors, []);
  }
});

test("lost session or role is reported for a redirect", async () => {
  for (const code of ["unauthorized", "forbidden"]) {
    const ui = await mountWithStats({ respond: () => Promise.reject({ code }) });

    assert.equal(ui.mounted, false);
    assert.deepEqual(ui.authErrors, [code]);
    assert.equal(ui.elements["#adminUsers"].children.length, 0);
  }
});

test("navigation activates overview by default and moves state to the clicked section", () => {
  const ui = createNavigationHarness();

  assert.equal(mountAdminNavigation(ui.documentRef, ui.windowRef), true);
  assert.deepEqual(activeNavigationLabels(ui.links), ["Обзор"]);

  ui.links[1].click();

  assert.deepEqual(activeNavigationLabels(ui.links), ["Активность"]);
  assert.equal(ui.links[0].getAttribute("aria-current"), null);
});

test("navigation follows direct and browser-driven hash changes with a safe fallback", () => {
  const ui = createNavigationHarness("#users");
  mountAdminNavigation(ui.documentRef, ui.windowRef);

  assert.deepEqual(activeNavigationLabels(ui.links), ["Пользователи"]);

  ui.windowRef.location.hash = "#activity";
  ui.windowRef.dispatch("hashchange");
  assert.deepEqual(activeNavigationLabels(ui.links), ["Активность"]);

  ui.windowRef.location.hash = "#missing";
  ui.windowRef.dispatch("hashchange");
  assert.deepEqual(activeNavigationLabels(ui.links), ["Обзор"]);
});

// Sections with a movable viewport: tops are page offsets minus scrollY.
function createScrollHarness({ offsets = [0, 700, 1400, 2100], pageHeight = 2600, hidden = false } = {}) {
  const hrefs = ["#overview", "#activity", "#users", "#reports"];
  const labels = ["Обзор", "Активность", "Пользователи", "Жалобы"];
  const links = hrefs.map((href, index) => {
    const link = new FakeElement("a");
    link.setAttribute("href", href);
    link.textContent = labels[index];
    return link;
  });
  const windowRef = new FakeWindow();
  windowRef.innerHeight = 800;
  windowRef.scrollY = 0;
  const frames = [];
  windowRef.requestAnimationFrame = callback => frames.push(callback);
  const timers = new Map();
  let nextTimer = 0;
  windowRef.setTimeout = (callback, delay) => {
    timers.set(++nextTimer, { callback, delay });
    return nextTimer;
  };
  windowRef.clearTimeout = id => timers.delete(id);
  const state = { hidden };
  const sections = new Map(hrefs.map((href, index) => [href, {
    getBoundingClientRect: () => state.hidden
      ? { top: 0, height: 0 }
      : { top: offsets[index] - windowRef.scrollY, height: 500 },
  }]));
  const documentRef = {
    querySelectorAll: selector => selector === "[data-admin-nav]" ? links : [],
    querySelector: selector => sections.get(selector) ?? null,
    documentElement: { get scrollHeight() { return state.hidden ? 800 : pageHeight; } },
  };
  const scrollTo = y => {
    windowRef.scrollY = y;
    windowRef.dispatch("scroll");
  };
  const flush = () => {
    const pending = frames.splice(0);
    for (const callback of pending) callback();
    return pending.length;
  };
  const runTimers = () => {
    const pending = [...timers.values()];
    timers.clear();
    for (const { callback } of pending) callback();
  };
  return { documentRef, links, windowRef, scrollTo, flush, runTimers, timers, state };
}

const ADMIN = { id: "admin-1", login: "sovunya", role: "admin" };
const USER = { id: "user-1", login: "krosh", role: "user" };

async function mountGuarded({
  me,
  refresh = () => Promise.reject(new AuthApiError("unauthorized")),
  logout = () => Promise.resolve(),
  changePassword = () => Promise.resolve(),
  adminStats = period => Promise.resolve(statsFor(period)),
}) {
  const ui = createHarness();
  const redirects = [];
  const logoutCalls = [];
  const passwordCalls = [];
  const mounted = await mountAdminPage(ui.documentRef, {
    api: {
      me,
      refresh,
      logout: () => (logoutCalls.push("logout"), logout()),
      changePassword: passwords => (passwordCalls.push(passwords), changePassword(passwords)),
    },
    adminApi: {
      stats: period => adminStats(period),
      listReports: () => Promise.resolve([]),
      setReportStatus: () => Promise.resolve(),
    },
    now: () => NOW,
    redirect: url => redirects.push(url),
    windowRef: new FakeWindow(),
  });
  return { ...ui, redirects, mounted, logoutCalls, passwordCalls };
}

test("the administrator is greeted by login as text", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve({ ...ADMIN, login: "<b>sovunya</b>" }) });

  assert.equal(ui.elements["#adminGreeting"].textContent, "Добрый день, <b>sovunya</b>");
});

test("a regular user never gets the administrator greeting", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve(USER) });

  assert.equal(ui.elements["#adminGreeting"].textContent, "");
});

test("an administrator sees the dashboard after the session check", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve(ADMIN) });

  assert.equal(ui.mounted, true);
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.elements["#adminContent"].hidden, false);
  assert.equal(ui.elements["#adminMetrics"].children.length, 4);
});

test("an administrator with an expired access token is renewed via refresh", async () => {
  const ui = await mountGuarded({
    me: () => Promise.reject(new AuthApiError("unauthorized")),
    refresh: () => Promise.resolve(ADMIN),
  });

  assert.equal(ui.mounted, true);
  assert.deepEqual(ui.redirects, []);
});

test("a regular user is sent to the chat without demo data", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve(USER) });

  assert.equal(ui.mounted, false);
  assert.deepEqual(ui.redirects, ["/"]);
  assert.equal(ui.elements["#adminMetrics"].children.length, 0);
});

test("a guest is sent to the login page without demo data", async () => {
  const ui = await mountGuarded({ me: () => Promise.reject(new AuthApiError("unauthorized")) });

  assert.equal(ui.mounted, false);
  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.elements["#adminMetrics"].children.length, 0);
});

test("an unavailable backend shows an error instead of demo data", async () => {
  const ui = await mountGuarded({ me: () => Promise.reject(new AuthApiError("unavailable")) });

  assert.equal(ui.mounted, false);
  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.elements["#adminContent"].hidden, true);
  assert.equal(ui.elements["#adminError"].hidden, false);
  assert.match(ui.elements["#adminError"].textContent, /недоступен/);
  assert.equal(ui.elements["#adminMetrics"].children.length, 0);
});

test("an administrator logs out and is sent to the login page", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve(ADMIN) });
  ui.elements["#adminLogout"].click();
  await settle();

  assert.deepEqual(ui.logoutCalls, ["logout"]);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("admin logout locks the button and ignores repeated clicks", async () => {
  let finish;
  const ui = await mountGuarded({
    me: () => Promise.resolve(ADMIN),
    logout: () => new Promise(resolve => { finish = resolve; }),
  });
  ui.elements["#adminLogout"].click();
  ui.elements["#adminLogout"].click();
  assert.equal(ui.elements["#adminLogout"].disabled, true);
  finish();
  await settle();

  assert.deepEqual(ui.logoutCalls, ["logout"]);
  assert.deepEqual(ui.redirects, ["/login/"]);
});

test("a failed admin logout keeps the panel and shows an error", async () => {
  const ui = await mountGuarded({
    me: () => Promise.resolve(ADMIN),
    logout: () => Promise.reject(new AuthApiError("unavailable")),
  });
  ui.elements["#adminLogout"].click();
  await settle();

  assert.deepEqual(ui.redirects, []);
  assert.equal(ui.elements["#adminLogout"].disabled, false);
  assert.equal(ui.elements["#adminLogoutError"].hidden, false);
  assert.equal(ui.elements["#adminLogoutError"].textContent, "Не удалось выйти. Попробуйте ещё раз");
  assert.equal(ui.elements["#adminContent"].hidden, false);

  ui.elements["#adminLogout"].click();
  await settle();
  assert.equal(ui.logoutCalls.length, 2);
});

test("logout is not wired for visitors who are redirected away", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve(USER) });
  ui.elements["#adminLogout"].click();
  await settle();

  assert.deepEqual(ui.logoutCalls, []);
  assert.deepEqual(ui.redirects, ["/"]);
});

test("the admin page redirects when statistics reject the session or role", async () => {
  const lost = await mountGuarded({
    me: () => Promise.resolve(ADMIN),
    adminStats: () => Promise.reject({ code: "unauthorized" }),
  });
  const demoted = await mountGuarded({
    me: () => Promise.resolve(ADMIN),
    adminStats: () => Promise.reject({ code: "forbidden" }),
  });

  assert.deepEqual(lost.redirects, ["/login/"]);
  assert.deepEqual(demoted.redirects, ["/"]);
});

const find = (element, className) => element.className === className
  ? element
  : element.children.map(child => find(child, className)).find(Boolean);
const findAll = (element, className) => [
  ...(element.className === className ? [element] : []),
  ...element.children.flatMap(child => findAll(child, className)),
];

test("answer quality shows the average score and numbered rows for the period", async () => {
  const ui = await mountWithStats();
  const quality = ui.elements["#adminQuality"];

  assert.equal(find(quality, "adm-quality-average").textContent, "3,6");
  assert.match(quality.textContent, /из 5/);
  assert.equal(find(quality, "adm-quality-face"), undefined);
  assert.match(quality.textContent, /оценено 5 из 10 ответов/);
  const rows = findAll(quality, "adm-quality-row");
  assert.deepEqual(
    rows.map(row => [
      find(row, "adm-quality-row-score").textContent,
      find(row, "adm-quality-bar-fill").style.width,
      find(row, "adm-quality-count").textContent,
    ]),
    [
      ["5", "40%", "2"],
      ["4", "20%", "1"],
      ["3", "20%", "1"],
      ["2", "0%", "0"],
      ["1", "20%", "1"],
    ],
  );
  assert.equal(rows[0].getAttribute("aria-label"), "Оценка 5 из 5: 2");
  assert.equal(rows[4].getAttribute("aria-label"), "Оценка 1 из 5: 1");
});

test("changing the period reloads answer quality", async () => {
  const ui = await mountWithStats({
    respond: period => Promise.resolve(statsFor(period, {
      feedback: period === "7"
        ? { answersTotal: 4, ratedAnswers: 2, counts: [0, 0, 0, 1, 1] }
        : { answersTotal: 10, ratedAnswers: 5, counts: [1, 0, 1, 1, 2] },
    })),
  });
  const quality = ui.elements["#adminQuality"];
  assert.equal(find(quality, "adm-quality-average").textContent, "3,6");

  ui.buttons[0].click();
  await settle();

  assert.equal(find(quality, "adm-quality-average").textContent, "4,5");
  assert.equal(find(quality, "adm-quality-face"), undefined);
  assert.match(quality.textContent, /оценено 2 из 4 ответов/);
});


function reportFor(id, overrides = {}) {
  return {
    id,
    reason: "rude",
    comment: null,
    requestText: "Расскажи про Нюшу",
    answerText: "Грубый ответ",
    status: "new",
    createdAt: new Date(2026, 9, 16, 12, 48).toISOString(),
    resolvedAt: null,
    dialogDeleted: false,
    ...overrides,
  };
}

function actionButtons(card) {
  return find(card, "adm-report-actions").children;
}

async function mountReportsWith({ lists = {}, change = () => Promise.resolve() } = {}) {
  const ui = createHarness();
  const loads = [];
  const changes = [];
  const authErrors = [];
  const reports = mountReports(ui.documentRef, {
    loadReports: filter => {
      loads.push(filter);
      const result = lists[filter] ?? [];
      return typeof result === "function" ? result() : Promise.resolve(result);
    },
    changeStatus: (id, status) => (changes.push([id, status]), change(id, status)),
    onAuthError: code => authErrors.push(code),
    now: () => NOW,
  });
  await settle();
  return { ...ui, reports, loads, changes, authErrors, cards: () => ui.elements["#adminReports"].children };
}

test("new reports show the reason, texts and a deleted story as text", async () => {
  const ui = await mountReportsWith({
    lists: {
      new: [
        reportFor(1, { comment: "<b>Обидно</b>", dialogDeleted: true }),
        reportFor(2, { reason: "scary", requestText: null }),
      ],
    },
  });

  assert.deepEqual(ui.loads, ["new"]);
  const [first, second] = ui.cards();
  assert.equal(first.dataset.reportId, "1");
  assert.equal(find(first, "adm-report-reason").textContent, "Грубо или обидно");
  assert.equal(find(first, "adm-report-status").textContent, "Новая");
  assert.equal(find(first, "adm-report-date").textContent, "сегодня, 12:48");
  assert.equal(find(first, "adm-report-deleted").textContent, "история удалена");
  assert.equal(find(first, "adm-report-comment").textContent, "«<b>Обидно</b>»");
  assert.match(first.textContent, /Запрос.*Расскажи про Нюшу/);
  assert.match(first.textContent, /Ответ.*Грубый ответ/);
  assert.equal(find(second, "adm-report-reason").textContent, "Страшно");
  assert.equal(find(second, "adm-report-deleted"), undefined);
  assert.equal(find(second, "adm-report-comment"), undefined);
  assert.match(second.textContent, /Запрос—/);
  assert.deepEqual(actionButtons(first).map(button => [button.textContent, button.dataset.status]), [
    ["Рассмотрено", "resolved"],
    ["Отклонить", "dismissed"],
  ]);
});

test("filters reload the reports and mark the chosen one", async () => {
  const ui = await mountReportsWith({
    lists: { resolved: [reportFor(3, { status: "resolved", resolvedAt: NOW.toISOString() })] },
  });

  ui.filters[1].click();
  await settle();

  assert.deepEqual(ui.loads, ["new", "resolved"]);
  assert.deepEqual(ui.filters.map(button => button.getAttribute("aria-pressed")), ["false", "true", "false", "false"]);
  const [card] = ui.cards();
  assert.equal(find(card, "adm-report-status").textContent, "Рассмотрена");
  assert.deepEqual(actionButtons(card).map(button => [button.textContent, button.dataset.status]), [
    ["Вернуть в новые", "new"],
  ]);
});

test("closing and reopening a report updates the list and the counter", async () => {
  let open = [reportFor(1)];
  let closed = [];
  const ui = await mountReportsWith({
    lists: { new: () => Promise.resolve(open), all: () => Promise.resolve([...open, ...closed]) },
    change: (id, status) => {
      if (status === "new") [open, closed] = [closed.map(item => ({ ...item, status })), []];
      else [open, closed] = [[], open.map(item => ({ ...item, status }))];
      return Promise.resolve();
    },
  });
  const badge = ui.elements["#adminReportsBadge"];
  ui.reports.setNewCount(3);
  assert.equal(badge.hidden, false);
  assert.equal(badge.textContent, "3");

  actionButtons(ui.cards()[0])[0].click();
  await settle();
  assert.deepEqual(ui.changes, [[1, "resolved"]]);
  assert.equal(ui.cards()[0].textContent, "Жалоб нет");
  assert.equal(badge.textContent, "2");

  ui.filters[3].click();
  await settle();
  actionButtons(ui.cards()[0])[0].click();
  await settle();
  assert.deepEqual(ui.changes, [[1, "resolved"], [1, "new"]]);
  assert.equal(find(ui.cards()[0], "adm-report-status").textContent, "Новая");
  assert.equal(badge.textContent, "3");

  ui.reports.setNewCount(0);
  assert.equal(badge.hidden, true);
});

test("a failed status change keeps the report and says so", async () => {
  const ui = await mountReportsWith({
    lists: { new: [reportFor(1)] },
    change: () => Promise.reject(new Error("offline")),
  });

  actionButtons(ui.cards()[0])[1].click();
  await settle();

  const error = ui.elements["#adminReportsError"];
  assert.equal(error.hidden, false);
  assert.equal(error.textContent, "Не удалось обновить жалобу");
  assert.equal(ui.cards()[0].dataset.reportId, "1");
  assert.ok(actionButtons(ui.cards()[0]).every(button => button.disabled === false));
});

test("a failed report list says so", async () => {
  const ui = await mountReportsWith({ lists: { new: () => Promise.reject(new Error("offline")) } });

  assert.equal(ui.elements["#adminReportsError"].hidden, false);
  assert.equal(ui.elements["#adminReportsError"].textContent, "Не удалось загрузить жалобы");
  assert.equal(ui.cards().length, 0);
});

test("a lost session or role on reports is reported for a redirect", async () => {
  const forbidden = Object.assign(new Error("forbidden"), { code: "forbidden" });
  const ui = await mountReportsWith({ lists: { new: () => Promise.reject(forbidden) } });

  assert.deepEqual(ui.authErrors, ["forbidden"]);
});

test("the admin page shows the number of new reports from the statistics", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve(ADMIN) });

  assert.equal(ui.elements["#adminReportsBadge"].textContent, "3");
  assert.equal(ui.elements["#adminReports"].children[0].textContent, "Жалоб нет");
});

const meAdmin = () => Promise.resolve(ADMIN);

function settingsParts(ui) {
  const e = ui.elements;
  return {
    button: e["#adminSettingsButton"],
    dialog: e["#adminSettings"],
    close: e["#adminSettingsClose"],
    form: e["#adminPasswordForm"],
    current: e["#adminCurrentPassword"],
    next: e["#adminNewPassword"],
    repeat: e["#adminRepeatPassword"],
    save: e["#adminPasswordSave"],
    status: e["#adminPasswordStatus"],
  };
}

function fillAdminPassword(parts, current = "carrot123", next = "radish456", repeat = next) {
  parts.current.value = current;
  parts.next.value = next;
  parts.repeat.value = repeat;
}

test("the admin settings window opens and closes like in the chat", async () => {
  const ui = await mountGuarded({ me: meAdmin });
  const parts = settingsParts(ui);

  for (const close of [
    () => parts.close.click(),
    () => ui.documentRef.dispatch("keydown", { key: "Escape" }),
    () => parts.dialog.dispatch("click", { target: parts.dialog }),
  ]) {
    parts.button.click();
    assert.equal(parts.dialog.hidden, false);
    assert.equal(FakeElement.focused, parts.current);
    fillAdminPassword(parts);
    close();
    assert.equal(parts.dialog.hidden, true);
    assert.equal(FakeElement.focused, parts.button);
    assert.equal(parts.current.value, "");
  }
  assert.deepEqual(ui.passwordCalls, []);
});

test("the admin password form checks fields locally and saves a new password", async () => {
  const ui = await mountGuarded({ me: meAdmin });
  const parts = settingsParts(ui);
  parts.button.click();

  fillAdminPassword(parts, "carrot123", "radish456", "radish457");
  await parts.form.dispatch("submit");
  assert.equal(parts.status.textContent, "Пароли не совпадают");
  assert.deepEqual(ui.passwordCalls, []);

  fillAdminPassword(parts);
  await parts.form.dispatch("submit");
  assert.deepEqual(ui.passwordCalls, [{ currentPassword: "carrot123", newPassword: "radish456" }]);
  assert.equal(parts.status.textContent, "Пароль изменён. На других устройствах нужно войти заново");
  assert.equal(parts.status.dataset.state, "ok");
  assert.equal(parts.next.value, "");
});

test("a wrong admin current password is reported", async () => {
  const ui = await mountGuarded({
    me: meAdmin,
    changePassword: () => Promise.reject(new AuthApiError("wrong_password")),
  });
  const parts = settingsParts(ui);
  parts.button.click();
  fillAdminPassword(parts);

  await parts.form.dispatch("submit");

  assert.equal(parts.status.textContent, "Неверный текущий пароль");
  assert.equal(parts.current.value, "");
});

test("a 401 on the admin password change refreshes once and retries", async () => {
  let calls = 0;
  const ui = await mountGuarded({
    me: meAdmin,
    refresh: () => Promise.resolve(ADMIN),
    changePassword: () => (calls += 1) === 1
      ? Promise.reject(new AuthApiError("unauthorized"))
      : Promise.resolve(),
  });
  const parts = settingsParts(ui);
  parts.button.click();
  fillAdminPassword(parts);

  await parts.form.dispatch("submit");

  assert.equal(ui.passwordCalls.length, 2);
  assert.equal(parts.status.textContent, "Пароль изменён. На других устройствах нужно войти заново");
  assert.deepEqual(ui.redirects, []);
});

test("an admin password change without a session opens the login page", async () => {
  const ui = await mountGuarded({
    me: meAdmin,
    changePassword: () => Promise.reject(new AuthApiError("unauthorized")),
  });
  const parts = settingsParts(ui);
  parts.button.click();
  fillAdminPassword(parts);

  await parts.form.dispatch("submit");

  assert.deepEqual(ui.redirects, ["/login/"]);
  assert.equal(ui.passwordCalls.length, 1);
});

test("the settings window is not mounted for a regular user", async () => {
  const ui = await mountGuarded({ me: () => Promise.resolve({ ...ADMIN, role: "user" }) });
  const parts = settingsParts(ui);

  parts.button.click();

  assert.equal(parts.dialog.hidden, true);
});
