// Only the backend checks ownership. This tab-local pointer is a navigation hint.
const uuid = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;

function key(userId: string) {
  return `smeshariki.dialog.${userId}`;
}

export function selectedDialog(userId: string): string | null {
  try {
    const id = sessionStorage.getItem(key(userId));
    if (id && uuid.test(id)) return id;
    if (id !== null) sessionStorage.removeItem(key(userId));
  } catch { /* Storage may be unavailable in private browsing. */ }
  return null;
}

export function rememberDialog(userId: string, id: string | null) {
  try {
    if (id && uuid.test(id)) sessionStorage.setItem(key(userId), id);
    else sessionStorage.removeItem(key(userId));
  } catch { /* The current page can still use the dialog in memory. */ }
}

// There is no task-status endpoint. This deadline bounds a wait if the terminal
// SSE event was lost and the backend never committed an answer (e.g. an error).
export const PENDING_WINDOW_MS = 120_000;

export interface PendingTurn {
  dialogId: string;
  lastAnswer: number | null;
  expiresAt: number;
}

export function writeTurn(userId: string, turn: PendingTurn) {
  if (!uuid.test(turn.dialogId)) return;
  try {
    sessionStorage.setItem(`smeshariki.turn.${userId}`, JSON.stringify(turn));
  } catch { /* The live page still tracks its own request. */ }
}

export function clearTurn(userId: string) {
  try {
    sessionStorage.removeItem(`smeshariki.turn.${userId}`);
  } catch { /* Storage is optional. */ }
}

export function pendingTurn(userId: string, id: string): PendingTurn | null {
  try {
    const raw = sessionStorage.getItem(`smeshariki.turn.${userId}`);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    const now = Date.now();
    if (value && typeof value === 'object' && 'dialogId' in value && value.dialogId === id
      && 'lastAnswer' in value && (value.lastAnswer === null || (typeof value.lastAnswer === 'number' && Number.isSafeInteger(value.lastAnswer)))
      && 'expiresAt' in value && typeof value.expiresAt === 'number'
      && value.expiresAt > now && value.expiresAt <= now + PENDING_WINDOW_MS) {
      return { dialogId: id, lastAnswer: value.lastAnswer, expiresAt: value.expiresAt };
    }
  } catch { /* Ignore damaged entries and blocked storage. */ }
  clearTurn(userId);
  return null;
}
