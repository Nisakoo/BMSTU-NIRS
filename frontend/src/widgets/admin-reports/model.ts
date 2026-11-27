import type { AdminApi, Report, ReportFilter, ReportStatus } from "../../entities/admin";
import { createStore } from "../../shared/lib/store";

interface ReportsState {
  filter: ReportFilter;
  reports: Report[] | null;
  error: string;
  pending: number[];
  newCount: number;
}

type Action =
  | { type: "filter"; filter: ReportFilter }
  | { type: "loaded"; reports: Report[] }
  | { type: "loadFailed" }
  | { type: "changing"; id: number }
  | { type: "changed"; id: number; status: ReportStatus; delta: number }
  | { type: "changeFailed"; id: number }
  | { type: "count"; value: number };

function reduce(state: ReportsState, action: Action): ReportsState {
  switch (action.type) {
    case "filter": return { ...state, filter: action.filter };
    case "loaded": return { ...state, reports: action.reports, error: "" };
    case "loadFailed": return { ...state, reports: null, error: "Не удалось загрузить жалобы" };
    case "changing": return { ...state, pending: [...state.pending, action.id] };
    case "changed": return {
      ...state,
      pending: state.pending.filter(id => id !== action.id),
      newCount: Math.max(0, state.newCount + action.delta),
      reports: state.reports?.map(report => report.id === action.id ? { ...report, status: action.status } : report)
        .filter(report => state.filter === "all" || report.status === state.filter) ?? null,
    };
    case "changeFailed": return {
      ...state,
      pending: state.pending.filter(id => id !== action.id),
      error: "Не удалось обновить жалобу",
    };
    case "count": return { ...state, newCount: action.value };
  }
}

export function createReports(
  api: Pick<AdminApi, "listReports" | "setReportStatus">,
  handleAuthError: (error: unknown) => boolean,
) {
  const store = createStore({ filter: "new", reports: null, pending: [], newCount: 0, error: "" }, reduce);
  let request = 0;
  let countRevision = 0;
  let active = true;

  async function load(filter = store.getState().filter) {
    if (!active) return;
    const current = ++request;
    store.dispatch({ type: "filter", filter });
    try {
      const reports = await api.listReports(filter);
      if (current === request) store.dispatch({ type: "loaded", reports });
    } catch (error) {
      if (current === request && !handleAuthError(error)) store.dispatch({ type: "loadFailed" });
    }
  }

  async function change(report: Report, status: ReportStatus) {
    if (!active || store.getState().pending.includes(report.id)) return;
    ++countRevision;
    store.dispatch({ type: "changing", id: report.id });
    try {
      await api.setReportStatus(report.id, status);
    } catch (error) {
      if (active && !handleAuthError(error)) store.dispatch({ type: "changeFailed", id: report.id });
      return;
    }
    if (!active) return;
    ++countRevision;
    const delta = Number(status === "new") - Number(report.status === "new");
    store.dispatch({ type: "changed", id: report.id, status, delta });
    await load();
  }

  return {
    subscribe: store.subscribe, load, change,
    get countRevision() { return countRevision; },
    setCount(value: number, revision: number) {
      // A stats request overlapping moderation can carry the count before or after the PATCH.
      if (revision === countRevision && store.getState().pending.length === 0) {
        store.dispatch({ type: "count", value });
      }
    },
    dispose() {
      active = false;
      ++request;
    },
  };
}

export type ReportsModel = ReturnType<typeof createReports>;
