import assert from "node:assert/strict";
import test from "node:test";

import { getDashboardData } from "../src/admin/demo-data.js";
import { formatActivity, mountAdminNavigation, mountAdminPage, mountDashboard } from "../src/admin/admin.js";
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
  ];
  const elements = Object.fromEntries(ids.map(id => [id, new FakeElement()]));
  const buttons = ["7", "30", "90"].map(period => {
    const button = new FakeElement("button");
    button.dataset.period = period;
    button.setAttribute("aria-pressed", "false");
    return button;
  });
  const documentRef = {
    querySelector: selector => elements[selector] ?? null,
    querySelectorAll: selector => selector === "[data-period]" ? buttons : [],
    createElement: tagName => new FakeElement(tagName),
  };
  return { documentRef, elements, buttons };
}

const NOW = new Date(2026, 9, 16, 15, 0);

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
      },
      {
        id: "user-2",
        login: "Sovunya",
        role: "admin",
        registeredAt: new Date(2026, 5, 1, 9, 0).toISOString(),
        lastActiveAt: new Date(2026, 9, 15, 21, 17).toISOString(),
        status: "active",
      },
      {
        id: "user-3",
        login: "<b>Pin</b>",
        role: "user",
        registeredAt: new Date(2025, 0, 2, 9, 0).toISOString(),
        lastActiveAt: null,
        status: "inactive",
      },
    ],
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

test("only agent figures carry the demo label", async () => {
  const ui = await mountWithStats();
  const demo = getDashboardData("30");
  const cards = ui.elements["#adminMetrics"].children;

  assert.deepEqual(cards.map(card => card.dataset.source), ["backend", "backend", "demo", "demo"]);
  assert.doesNotMatch(cards[0].textContent, /демо/);
  assert.doesNotMatch(cards[1].textContent, /демо/);
  assert.match(cards[2].textContent, /демо-данные/);
  assert.match(cards[2].textContent, /3 542/);
  assert.match(cards[3].textContent, /демо-данные/);
  assert.equal(ui.elements["#adminActivity"].children.length, demo.activity.length);
  assert.match(ui.elements["#adminQuality"].textContent, /97,2%/);
  assert.doesNotMatch(ui.elements["#adminUsers"].textContent, /демо/);
});

test("recent users show login, role, activity time, status and no dialog count", async () => {
  const ui = await mountWithStats();
  const rows = ui.elements["#adminUsers"].children;

  assert.equal(rows.length, 3);
  assert.match(rows[0].textContent, /Krosh/);
  assert.match(rows[0].textContent, /пользователь/);
  assert.match(rows[0].textContent, /сегодня, 12:48/);
  assert.match(rows[0].textContent, /Новый/);
  assert.match(rows[1].textContent, /администратор/);
  assert.match(rows[1].textContent, /вчера, 21:17/);
  assert.match(rows[1].textContent, /Активен/);
  assert.match(rows[2].textContent, /ещё не входил/);
  assert.match(rows[2].textContent, /Неактивен/);
  assert.equal(rows[0].children[2].textContent, "—");
  assert.equal(rows[2].children[0].children[1].children[0].textContent, "<b>Pin</b>");
});

test("an empty user list is reported in place", async () => {
  const ui = await mountWithStats({
    respond: period => Promise.resolve(statsFor(period, { usersTotal: 0, recentUsers: [] })),
  });

  assert.equal(ui.elements["#adminUsers"].children.length, 1);
  assert.equal(ui.elements["#adminUsers"].textContent, "Пользователей пока нет");
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

test("missing demo data keeps the safe error state", async () => {
  const ui = await mountWithStats({ dashboard: { getData: () => null } });

  assert.equal(ui.elements["#adminContent"].hidden, true);
  assert.match(ui.elements["#adminError"].textContent, /не удалось загрузить/i);
  assert.deepEqual(ui.calls, []);
});

test("activity time falls back to a date for older visits", () => {
  assert.equal(formatActivity(new Date(2026, 9, 16, 0, 5).toISOString(), NOW), "сегодня, 00:05");
  assert.match(formatActivity(new Date(2026, 8, 3, 9, 30).toISOString(), NOW), /^3 сент\.?, 09:30$/);
  assert.match(formatActivity(new Date(2025, 11, 31, 9, 30).toISOString(), NOW), /2025/);
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

const ADMIN = { id: "admin-1", login: "sovunya", role: "admin" };
const USER = { id: "user-1", login: "krosh", role: "user" };

async function mountGuarded({
  me,
  refresh = () => Promise.reject(new AuthApiError("unauthorized")),
  logout = () => Promise.resolve(),
  adminStats = period => Promise.resolve(statsFor(period)),
}) {
  const ui = createHarness();
  const redirects = [];
  const logoutCalls = [];
  const mounted = await mountAdminPage(ui.documentRef, {
    api: { me, refresh, logout: () => (logoutCalls.push("logout"), logout()) },
    adminApi: { stats: period => adminStats(period) },
    now: () => NOW,
    redirect: url => redirects.push(url),
    windowRef: new FakeWindow(),
  });
  return { ...ui, redirects, mounted, logoutCalls };
}

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
