// @vitest-environment jsdom
import { afterEach, expect, test, vi } from "vitest";
import { mount, tick, unmount } from "svelte";
import { AuthApiError } from "../src/entities/session";
import { AdminPage, createDashboard } from "../src/pages/admin";
import { greetingFor } from "../src/pages/admin/greeting";

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


const settle = () => new Promise(resolve => setTimeout(resolve, 0));
const ADMIN = { id: "admin-1", login: "<b>sovunya</b>", role: "admin" };
const rejected = code => Promise.reject(new AuthApiError(code));
let page;

async function open({ auth = {}, admin = {}, hash = "" } = {}) {
  window.history.replaceState(null, "", "/admin/" + hash);
  const api = {
    me: vi.fn(async () => ADMIN),
    refresh: vi.fn(() => rejected("unauthorized")),
    logout: vi.fn(async () => {}),
    changePassword: vi.fn(async () => {}),
    ...auth,
  };
  const adminApi = {
    stats: vi.fn(async period => statsFor(period)),
    listReports: vi.fn(async () => []),
    setReportStatus: vi.fn(async () => {}),
    ...admin,
  };
  const redirect = vi.fn();
  const model = createDashboard(api, adminApi, redirect);
  page = mount(AdminPage, { target: document.body, props: { model, now: () => NOW } });
  await settle();
  return { api, adminApi, redirect };
}

afterEach(async () => {
  if (page) await unmount(page);
  page = undefined;
  document.body.replaceChildren();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
const $ = selector => document.querySelector(selector);
const all = selector => [...document.querySelectorAll(selector)];
const activeNav = () => $('nav [aria-current="location"]').hash;
const periodButton = period => $(`[data-period="${period}"]`);
const reportFilter = status => $(`[data-report-filter="${status}"]`);

test("administrator sees greeting, backend figures and safe recent user details", async () => {
  const { adminApi, redirect } = await open();
  expect(redirect).not.toHaveBeenCalled();
  expect(adminApi.stats.mock.calls).toEqual([["30"]]);
  expect($("#adminGreeting").textContent).toBe("Добрый день, <b>sovunya</b>");
  expect($("#adminGreeting b")).toBeNull();
  expect($("#adminContent").hidden).toBe(false);
  expect($("#adminError").hidden).toBe(true);
  expect($("#adminPeriodLabel").textContent).toBe("30 дней");
  expect(periodButton("30").ariaPressed).toBe("true");
  expect($("#adminComparison").textContent).toBe("Новых пользователей: 4");
  expect(all(".adm-metric").map(el => [el.dataset.metric, el.querySelector("strong").textContent]))
    .toEqual([["usersTotal", "1 234"], ["activeUsers", "9"], ["dialogs", "24"], ["messages", "144"]]);
  const rows = all(".adm-user-row");
  expect(rows).toHaveLength(3);
  expect(rows[0].textContent).toContain("пользователь");
  expect(rows[0].textContent).toContain("сегодня, 12:48");
  expect(rows[0].children[2].textContent).toBe("12");
  expect(rows[0].children[3].textContent).toBe("вчера");
  expect(rows[1].textContent).toContain("администратор");
  expect(rows[1].textContent).toContain("вчера, 21:17");
  expect(rows[1].children[2].textContent).toBe("1 234");
  expect(rows[1].children[3].textContent).toMatch(/^1 июн/);
  expect(rows[2].textContent).toContain("ещё не входил");
  expect(rows[2].children[3].textContent).toMatch(/^2 янв\.? 2025/);
  expect(rows[2].querySelector("strong").textContent).toBe("<b>Pin</b>");
  expect(rows[2].querySelector("b")).toBeNull();
  expect($("#adminReportsBadge").textContent).toBe("3");
  expect($("#adminReports").textContent.trim()).toBe("Жалоб нет");
});

test.each([[4, "Доброй ночи"], [5, "Доброе утро"], [11, "Доброе утро"], [12, "Добрый день"],
  [16, "Добрый день"], [17, "Добрый вечер"], [22, "Добрый вечер"], [23, "Доброй ночи"]])(
  "local hour %i selects %s", (hour, greeting) => {
    expect(greetingFor(new Date(2026, 9, 16, hour))).toBe(greeting);
  },
);

test("quality shows the weighted score and accessible histogram for the period", async () => {
  await open();
  expect($(".adm-quality-average").textContent).toBe("3,6");
  expect($(".adm-quality-note").textContent).toBe("оценено 5 из 10 ответов");
  expect(all(".adm-quality-row").map(row => [
    row.getAttribute("aria-label"), row.querySelector(".adm-quality-bar-fill").style.width,
  ])).toEqual([
    ["Оценка 5 из 5: 2", "40%"], ["Оценка 4 из 5: 1", "20%"], ["Оценка 3 из 5: 1", "20%"],
    ["Оценка 2 из 5: 0", "0%"], ["Оценка 1 из 5: 1", "20%"],
  ]);
  expect(all(".adm-chart-column")).toHaveLength(10);
  expect($(".adm-chart-bar-empty").style.height).toBe("0%");
  expect($("#adminChartDescription").textContent).toContain("Истории за 30 дней");
});

test("period changes lock duplicate requests and replace statistics including empty sections", async () => {
  let complete;
  const stats = vi.fn(period => period === "30" ? Promise.resolve(statsFor(period)) : new Promise(resolve => {
    complete = () => resolve(statsFor(period, {
      dialogs: 0, activity: [{ start: NOW.toISOString(), dialogs: 0 }], recentUsers: [],
      feedback: { answersTotal: 4, ratedAnswers: 0, counts: [0, 0, 0, 0, 0] },
    }));
  }));
  await open({ admin: { stats } });
  periodButton("90").click();
  await tick();
  expect(all("[data-period]").every(button => button.disabled)).toBe(true);
  periodButton("7").click();
  expect(stats.mock.calls).toEqual([["30"], ["90"]]);
  complete();
  await settle();
  expect(periodButton("90").ariaPressed).toBe("true");
  expect(all("[data-period]").some(button => button.disabled)).toBe(false);
  expect($("#adminPeriodLabel").textContent).toBe("90 дней");
  expect($("#adminComparison").textContent).toContain("8");
  expect($("#adminChartDescription").textContent).toBe("Историй за 90 дней нет.");
  expect($("#adminQuality").textContent).toContain("Оценок пока нет");
  expect($("#adminUsers").textContent).toContain("Пользователей пока нет");
});

test.each(["invalid_response", "unavailable"])("statistics %s failure clears previous data and supports retry", async code => {
  const stats = vi.fn(async period => statsFor(period));
  await open({ admin: { stats } });
  stats.mockRejectedValueOnce({ code });
  periodButton("7").click();
  await settle();
  expect($("#adminContent").hidden).toBe(true);
  expect($(".adm-user-row")).toBeNull();
  expect($("#adminError").textContent).toContain("Не удалось загрузить статистику");
  periodButton("7").click();
  await settle();
  expect($("#adminContent").hidden).toBe(false);
  expect($("#adminError").hidden).toBe(true);
});

test.each([
  ["guest", () => rejected("unauthorized"), "/login/"],
  ["regular user", async () => ({ ...ADMIN, role: "user" }), "/"],
  ["unavailable session", () => rejected("unavailable"), null],
])("%s cannot load administrative data or actions", async (_label, me, path) => {
  const { api, adminApi, redirect } = await open({ auth: { me } });
  if (path) expect(redirect.mock.calls).toEqual([[path]]);
  else {
    expect(redirect).not.toHaveBeenCalled();
    expect($("#adminError").textContent).toContain("недоступен");
  }
  expect(adminApi.stats).not.toHaveBeenCalled();
  expect(adminApi.listReports).not.toHaveBeenCalled();
  $("#adminLogout").click();
  $("#adminSettingsButton").click();
  expect(api.logout).not.toHaveBeenCalled();
  expect($("#adminSettings")).toBeNull();
  expect($("#adminContent").hidden).toBe(true);
  expect($("#adminGreeting").textContent).not.toContain(ADMIN.login);
});

test("expired access cookie is refreshed before the admin dashboard loads", async () => {
  const { adminApi } = await open({ auth: { me: () => rejected("unauthorized"), refresh: async () => ADMIN } });
  expect(adminApi.stats).toHaveBeenCalledOnce();
  expect($("#adminContent").hidden).toBe(false);
});

test.each([["stats", "forbidden", "/"], ["stats", "unauthorized", "/login/"],
  ["listReports", "forbidden", "/"], ["listReports", "unauthorized", "/login/"]])(
  "%s rejects authorization with %s", async (method, code, path) => {
    const { redirect } = await open({ admin: { [method]: async () => { throw { code }; } } });
    expect(redirect.mock.calls).toEqual([[path]]);
    expect($("#adminContent").hidden).toBe(true);
  },
);

test("failed logout leaves session visible and can be retried once while pending", async () => {
  let finish;
  const logout = vi.fn().mockRejectedValueOnce(new Error()).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const { redirect } = await open({ auth: { logout } });
  $("#adminLogout").click();
  await settle();
  expect($("#adminLogoutError").textContent).toContain("Не удалось выйти");
  expect($("#adminContent").hidden).toBe(false);
  $("#adminLogout").click();
  $("#adminLogout").click();
  await tick();
  expect($("#adminLogout").disabled).toBe(true);
  expect(logout).toHaveBeenCalledTimes(2);
  finish();
  await settle();
  expect(redirect.mock.calls).toEqual([["/login/"]]);
});

test("reports render untrusted texts, review and reopen using the current filter and badge", async () => {
  let report = reportFor(1, { comment: "<b>Обидно</b>", dialogDeleted: true, requestText: null });
  const listReports = vi.fn(async filter => filter === "all" || filter === report.status ? [report] : []);
  const setReportStatus = vi.fn(async (_id, status) => { report = { ...report, status }; });
  await open({ admin: { listReports, setReportStatus } });
  expect(listReports.mock.calls).toEqual([["new"]]);
  expect($(".adm-report-comment").textContent).toBe("«<b>Обидно</b>»");
  expect($(".adm-report-comment b")).toBeNull();
  expect($(".adm-report-deleted").textContent).toBe("история удалена");
  expect($(".adm-report-reason").textContent).toBe("Грубо или обидно");
  expect($(".adm-report-date").textContent).toBe("сегодня, 12:48");
  expect($(".adm-report-body").textContent).toBe("—");
  expect(all("[data-status]").map(button => button.textContent)).toEqual(["Рассмотрено", "Отклонить"]);
  $('[data-status="resolved"]').click();
  await settle();
  expect($("#adminReports").textContent.trim()).toBe("Жалоб нет");
  expect($("#adminReportsBadge").textContent).toBe("2");
  reportFilter("all").click();
  await settle();
  expect(reportFilter("all").ariaPressed).toBe("true");
  expect($(".adm-report-status").textContent).toBe("Рассмотрена");
  $('[data-status="new"]').click();
  await settle();
  expect($(".adm-report-status").textContent).toBe("Новая");
  expect($("#adminReportsBadge").textContent).toBe("3");
  expect(setReportStatus.mock.calls).toEqual([[1, "resolved"], [1, "new"]]);
});

test("a stale report response cannot overwrite a later filter", async () => {
  let complete;
  const listReports = vi.fn(filter => filter === "new" ? new Promise(resolve => { complete = resolve; }) :
    Promise.resolve([reportFor(2, { status: filter })]));
  await open({ admin: { listReports } });
  reportFilter("dismissed").click();
  await settle();
  complete([reportFor(1)]);
  await settle();
  expect($(".adm-report").dataset.reportId).toBe("2");
  expect($(".adm-report-status").textContent).toBe("Отклонена");
});

test("report failures clear the failed list or keep the failed update actionable", async () => {
  const listReports = vi.fn(async () => [reportFor(1)]);
  const setReportStatus = vi.fn(async () => { throw new Error(); });
  await open({ admin: { listReports, setReportStatus } });
  $('[data-status="dismissed"]').click();
  await settle();
  expect($("#adminReportsError").textContent).toBe("Не удалось обновить жалобу");
  expect(all("[data-status]").every(button => !button.disabled)).toBe(true);
  expect($(".adm-report").dataset.reportId).toBe("1");
  listReports.mockRejectedValueOnce(new Error());
  reportFilter("resolved").click();
  await settle();
  expect($("#adminReportsError").textContent).toBe("Не удалось загрузить жалобы");
  expect($(".adm-report")).toBeNull();
});

test("hash, click, history, scroll and resize keep one navigation item current", async () => {
  await open({ hash: "#users" });
  expect(activeNav()).toBe("#users");
  const chooseHash = async hash => {
    window.history.replaceState(null, "", "/admin/" + hash);
    window.dispatchEvent(new Event("hashchange"));
    await tick();
  };
  await chooseHash("#activity");
  expect(activeNav()).toBe("#activity");
  await chooseHash("#missing");
  expect(activeNav()).toBe("#overview");

  let frame;
  const queue = vi.spyOn(window, "requestAnimationFrame").mockImplementation(callback => { frame = callback; return 42; });
  const sections = ["overview", "activity", "users", "reports"];
  const tops = [0, 700, 1400, 2100];
  let scroll = 0;
  let hidden = false;
  for (const [i, id] of sections.entries()) {
    vi.spyOn($("#" + id), "getBoundingClientRect").mockImplementation(() => ({
      top: tops[i] - scroll, height: hidden ? 0 : 500,
    }));
  }
  vi.spyOn(window, "scrollY", "get").mockImplementation(() => scroll);
  vi.spyOn(document.documentElement, "scrollHeight", "get").mockReturnValue(2600);
  const follow = async (y, event = "scroll") => {
    scroll = y;
    window.dispatchEvent(new Event(event));
    if (frame) { const callback = frame; frame = undefined; callback(0); }
    await tick();
  };

  const reportsLink = $('nav a[href="#reports"]');
  reportsLink.addEventListener("click", event => event.preventDefault(), { once: true });
  reportsLink.click();
  await follow(800);
  expect(activeNav()).toBe("#reports");
  expect(queue).not.toHaveBeenCalled();
  window.dispatchEvent(new Event("scrollend"));
  window.dispatchEvent(new Event("scroll"));
  await follow(800, "resize");
  expect(queue).toHaveBeenCalledTimes(1);
  expect(activeNav()).toBe("#activity");
  expect(window.location.hash).toBe("#missing");
  await follow(1900);
  expect(activeNav()).toBe("#reports");
  hidden = true;
  await follow(0);
  expect(activeNav()).toBe("#reports");

  // Browsers without scrollend release a selection after one second.
  vi.useFakeTimers();
  try {
    await chooseHash("#activity");
    hidden = false;
    await follow(0);
    expect(activeNav()).toBe("#activity");
    vi.advanceTimersByTime(1000);
    await follow(0);
    expect(activeNav()).toBe("#overview");
  } finally {
    vi.useRealTimers();
  }
});

async function openSettings() {
  $("#adminSettingsButton").click();
  await tick();
}

async function submitPassword(repeat = "radish456") {
  $("#adminCurrentPassword").value = "carrot123";
  $("#adminNewPassword").value = "radish456";
  $("#adminRepeatPassword").value = repeat;
  $("#adminPasswordForm").dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  await settle();
}

test("settings support close button, Escape, backdrop, focus return and cleared fields", async () => {
  await open();
  for (const close of [
    () => $("#adminSettingsClose").click(),
    () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" })),
    () => $("#adminSettings").click(),
  ]) {
    await openSettings();
    expect($("#adminSettingsButton").ariaExpanded).toBe("true");
    expect(document.activeElement).toBe($("#adminCurrentPassword"));
    $("#adminCurrentPassword").value = "carrot123";
    close();
    await tick();
    expect($("#adminSettings").hidden).toBe(true);
    expect(document.activeElement).toBe($("#adminSettingsButton"));
    expect($("#adminCurrentPassword").value).toBe("");
  }
});

test("password validation, wrong password and successful save use the shared form", async () => {
  const changePassword = vi.fn().mockRejectedValueOnce(new AuthApiError("wrong_password")).mockResolvedValueOnce();
  await open({ auth: { changePassword } });
  await openSettings();
  await submitPassword("radish457");
  expect($("#adminPasswordStatus").textContent).toBe("Пароли не совпадают");
  expect(changePassword).not.toHaveBeenCalled();
  await submitPassword();
  expect($("#adminPasswordStatus").textContent).toBe("Неверный текущий пароль");
  expect($("#adminCurrentPassword").value).toBe("");
  await submitPassword();
  expect(changePassword).toHaveBeenLastCalledWith({ currentPassword: "carrot123", newPassword: "radish456" });
  expect($("#adminPasswordStatus").dataset.state).toBe("ok");
  expect($("#adminNewPassword").value).toBe("");
});

test.each(["ok", "anonymous", "expired", "unavailable"])("password 401 refresh outcome %s", async outcome => {
  const refresh = vi.fn(() => outcome === "anonymous" ? rejected("unauthorized") :
    outcome === "unavailable" ? rejected("unavailable") : Promise.resolve(ADMIN));
  const changePassword = vi.fn().mockRejectedValueOnce(new AuthApiError("unauthorized"));
  if (outcome === "expired") changePassword.mockRejectedValueOnce(new AuthApiError("unauthorized"));
  const { redirect } = await open({ auth: { changePassword, refresh } });
  await openSettings();
  await submitPassword();
  expect(refresh).toHaveBeenCalledOnce();
  expect(changePassword).toHaveBeenCalledTimes(["ok", "expired"].includes(outcome) ? 2 : 1);
  if (["anonymous", "expired"].includes(outcome)) expect(redirect.mock.calls).toEqual([["/login/"]]);
  else {
    expect(redirect).not.toHaveBeenCalled();
    expect($("#adminPasswordStatus").dataset.state).toBe(outcome === "ok" ? "ok" : "error");
  }
});

test("a period response racing a moderation action cannot restore a stale badge", async () => {
  let finishStats, finishReports;
  const stats = vi.fn(async period => statsFor(period)).mockImplementationOnce(async () => statsFor("30"));
  const listReports = vi.fn().mockResolvedValueOnce([reportFor(1)])
    .mockImplementation(() => new Promise(resolve => { finishReports = resolve; }));
  const { adminApi } = await open({ admin: { stats, listReports } });
  stats.mockImplementationOnce(() => new Promise(resolve => { finishStats = resolve; }));
  periodButton("7").click();
  $('[data-status="resolved"]').click();
  await settle();
  expect($("#adminReportsBadge").textContent).toBe("2");
  expect($('[data-status="resolved"]')).toBeNull();
  finishStats(statsFor("7", { reportsNew: 3 }));
  finishReports([]);
  await settle();
  expect($("#adminReportsBadge").textContent).toBe("2");
  expect(adminApi.setReportStatus).toHaveBeenCalledOnce();
});
