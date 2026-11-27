import { errorCode, type AuthApi, type User } from './api';

export const LOGIN_PATH = '/login/';
export const CHAT_PATH = '/';
export const ADMIN_PATH = '/admin/';
export const REFRESH_LOCK = 'smeshariki-auth-refresh';
export const SESSION = { USER: 'user', ANONYMOUS: 'anonymous', UNAVAILABLE: 'unavailable' } as const;

export type Session = { status: 'user'; user: User } | { status: 'anonymous' } | { status: 'unavailable' };
type SessionApi = Pick<AuthApi, 'me' | 'refresh'>;
type LockOptions = { locks?: Pick<LockManager, 'request'> | null };

function outcome(error: unknown): Session {
  return { status: errorCode(error) === 'unauthorized' ? SESSION.ANONYMOUS : SESSION.UNAVAILABLE };
}

async function callRefresh(api: SessionApi): Promise<Session> {
  try {
    return { status: SESSION.USER, user: await api.refresh() };
  } catch (error) {
    return outcome(error);
  }
}

export async function refreshSession(api: SessionApi, { locks = globalThis.navigator?.locks }: LockOptions = {}): Promise<Session> {
  if (typeof locks?.request !== 'function') return callRefresh(api);
  // The tab that waited first checks whether another tab already refreshed this session.
  return locks.request(REFRESH_LOCK, async (): Promise<Session> => {
    try {
      return { status: SESSION.USER, user: await api.me() };
    } catch (error) {
      if (errorCode(error) !== 'unauthorized') return outcome(error);
    }
    return callRefresh(api);
  });
}

export async function checkSession(api: SessionApi, options?: LockOptions): Promise<Session> {
  try {
    return { status: SESSION.USER, user: await api.me() };
  } catch (error) {
    if (errorCode(error) !== 'unauthorized') return outcome(error);
  }
  return refreshSession(api, options);
}

export function homeFor(user: User) {
  return user.role === 'admin' ? ADMIN_PATH : CHAT_PATH;
}
