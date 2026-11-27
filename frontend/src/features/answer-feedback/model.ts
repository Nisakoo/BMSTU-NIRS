import type { DialogMessage } from "../../entities/dialog";
import { createStore } from "../../shared/lib/store";

interface Rating {
  score: number | null;
  pending: boolean;
}

type RatingAction = { type: "choose"; score: number } | { type: "saved" } | { type: "restore"; score: number | null };

function reduceRating(state: Rating, action: RatingAction): Rating {
  switch (action.type) {
    case "choose": return { score: action.score === state.score ? null : action.score, pending: true };
    case "saved": return { ...state, pending: false };
    case "restore": return { score: action.score, pending: false };
  }
}

export function createRating(initial: number | null, save: (score: number | null) => Promise<void>) {
  const store = createStore<Rating, RatingAction>({ score: initial, pending: false }, reduceRating);

  async function choose(score: number) {
    const previous = store.getState();
    if (previous.pending) return;
    store.dispatch({ type: "choose", score });
    try {
      await save(store.getState().score);
      store.dispatch({ type: "saved" });
    } catch (error) {
      store.dispatch({ type: "restore", score: previous.score });
      throw error;
    }
  }

  return { subscribe: store.subscribe, choose };
}

interface Report {
  status: DialogMessage["report"];
  pending: boolean;
}

type ReportAction = "send" | "sent" | "failed";

export function createReport(initial: Report["status"], submit: (reason: string, comment: string) => Promise<void>) {
  const store = createStore<Report, ReportAction>({ status: initial, pending: false }, (state, action) => ({
    status: action === "sent" ? "sent" : state.status,
    pending: action === "send",
  }));

  async function send(reason: string, comment: string) {
    const { pending, status } = store.getState();
    if (pending || status) return;
    store.dispatch("send");
    try {
      await submit(reason, comment);
      store.dispatch("sent");
    } catch (error) {
      store.dispatch("failed");
      throw error;
    }
  }

  return { subscribe: store.subscribe, send };
}
