import type { AdminApi, AdminStats, Period } from "../../entities/admin";
import {
  AuthApiError, CHAT_PATH, LOGIN_PATH, SESSION, checkSession, errorCode, refreshSession,
  type AuthApi, type PasswordChange, type User,
} from "../../entities/session";
import { createStore } from "../../shared/lib/store";
import { createReports } from "../../widgets/admin-reports";

interface DashboardState {
  user: User | null;
  stats: AdminStats | null;
  period: Period;
  loading: boolean;
  error: string;
  loggingOut: boolean;
  logoutFailed: boolean;
}

type Action =
  | { type: "authenticated"; user: User }
  | { type: "unavailable" | "loading" | "statsFailed" | "logout" | "logoutFailed" | "leave" }
  | { type: "loaded"; stats: AdminStats };

const initial: DashboardState = {
  user: null, stats: null, period: "30", loading: false, error: "", loggingOut: false, logoutFailed: false,
};

function reduce(state: DashboardState, action: Action): DashboardState {
  switch (action.type) {
    case "authenticated": return { ...state, user: action.user };
    case "unavailable": return { ...initial, error: "Сервис временно недоступен. Обновите страницу позже." };
    case "loading": return { ...state, loading: true };
    case "loaded": return { ...state, loading: false, stats: action.stats, period: action.stats.period, error: "" };
    case "statsFailed": return { ...state, loading: false, stats: null, error: "Не удалось загрузить статистику. Попробуйте обновить страницу" };
    case "logout": return { ...state, loggingOut: true, logoutFailed: false };
    case "logoutFailed": return { ...state, loggingOut: false, logoutFailed: true };
    case "leave": return initial;
  }
}

export function createDashboard(
  api: Pick<AuthApi, "me" | "refresh" | "changePassword" | "logout">,
  adminApi: Pick<AdminApi, "stats" | "listReports" | "setReportStatus">,
  redirect: (url: string) => void,
) {
  const store = createStore(initial, reduce);
  let active = true;

  function leave(url: string) {
    if (!active) return;
    dispose();
    store.dispatch({ type: "leave" });
    redirect(url);
  }

  function handleAuthError(error: unknown) {
    const code = errorCode(error);
    if (code === "unauthorized") leave(LOGIN_PATH);
    else if (code === "forbidden") leave(CHAT_PATH);
    else return false;
    return true;
  }

  const reports = createReports(adminApi, handleAuthError);

  async function load(period: Period) {
    const state = store.getState();
    if (!state.user || state.loading) return;
    const revision = reports.countRevision;
    store.dispatch({ type: "loading" });
    try {
      const stats = await adminApi.stats(period);
      if (active) {
        store.dispatch({ type: "loaded", stats });
        reports.setCount(stats.reportsNew, revision);
      }
    } catch (error) {
      if (active && !handleAuthError(error)) store.dispatch({ type: "statsFailed" });
    }
  }

  async function start() {
    const session = await checkSession(api);
    if (!active) return;
    if (session.status === SESSION.ANONYMOUS) return leave(LOGIN_PATH);
    if (session.status === SESSION.UNAVAILABLE) return store.dispatch({ type: "unavailable" });
    if (session.user.role !== "admin") return leave(CHAT_PATH);
    store.dispatch({ type: "authenticated", user: session.user });
    await Promise.all([reports.load(), load("30")]);
  }

  async function logout() {
    if (!store.getState().user || store.getState().loggingOut) return;
    store.dispatch({ type: "logout" });
    try {
      await api.logout();
      leave(LOGIN_PATH);
    } catch {
      if (active) store.dispatch({ type: "logoutFailed" });
    }
  }

  async function changePassword(values: PasswordChange) {
    try {
      return await api.changePassword(values);
    } catch (error) {
      if (errorCode(error) !== "unauthorized") throw error;
    }
    const session = await refreshSession(api);
    if (session.status === SESSION.ANONYMOUS) {
      leave(LOGIN_PATH);
      throw new AuthApiError("unauthorized");
    }
    if (session.status !== SESSION.USER) throw new AuthApiError("unavailable");
    try {
      return await api.changePassword(values);
    } catch (error) {
      if (errorCode(error) === "unauthorized") leave(LOGIN_PATH);
      throw error;
    }
  }

  function dispose() {
    active = false;
    reports.dispose();
  }

  return {
    subscribe: store.subscribe, start, load, logout, changePassword, reports,
    isUnloading: () => !active,
    dispose,
  };
}

export type Dashboard = ReturnType<typeof createDashboard>;
