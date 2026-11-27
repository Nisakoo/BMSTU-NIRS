import { checkSession, errorCode, homeFor, SESSION, type AuthApi, type Credentials } from '../../entities/session';
import { createStore } from '../../shared/lib/store';

export type LoginApi = Pick<AuthApi, 'me' | 'refresh' | 'login' | 'register'>;
type Mode = 'login' | 'register';
type Field = 'login' | 'password' | 'confirm';
type Errors = Partial<Record<Field, string>>;

interface LoginState {
  mode: Mode;
  busy: boolean;
  errors: Errors;
  message: string;
}

type Action = { type: 'select'; mode: Mode } | { type: 'invalid'; errors: Errors }
  | { type: 'submit' } | { type: 'failed'; message: string };

const initial: LoginState = { mode: 'login', busy: false, errors: {}, message: '' };

function reduce(state: LoginState, action: Action): LoginState {
  switch (action.type) {
    case 'select': return state.busy ? state : { ...initial, mode: action.mode };
    case 'invalid': return { ...state, errors: action.errors, message: '' };
    case 'submit': return { ...state, errors: {}, message: '', busy: true };
    case 'failed': return { ...state, message: action.message, busy: false };
  }
}

const messages: Record<string, string> = {
  login_taken: 'Этот логин уже занят',
  invalid_credentials: 'Неверный логин или пароль',
  invalid_fields: 'Проверьте логин и пароль',
  too_many_attempts: 'Слишком много попыток. Попробуйте позже',
};

function validate(mode: Mode, { login, password }: Credentials, confirm: string): Errors {
  const errors: Errors = {};
  if (!/^[A-Za-z0-9_.-]{3,32}$/.test(login)) {
    errors.login = 'От 3 до 32 символов: латинские буквы, цифры, «_», «.» или «-»';
  }
  if (password.length < 8 || password.length > 128) errors.password = 'Пароль должен быть от 8 до 128 символов';
  if (mode === 'register' && confirm !== password) errors.confirm = 'Пароли не совпадают';
  return errors;
}

type Submission = { focus: Field; clearPasswords?: boolean } | undefined;

export function createLogin(api: LoginApi, navigate: (url: string) => void) {
  const store = createStore(initial, reduce);

  // A delayed startup check belongs to the session that existed before manual sign-in.
  let version = 0;

  async function check() {
    const checked = version;
    const session = await checkSession(api);
    if (checked === version && session.status === SESSION.USER) navigate(homeFor(session.user));
  }

  async function submit(credentials: Credentials, confirm: string): Promise<Submission> {
    const { busy, mode } = store.getState();
    if (busy) return;
    const errors = validate(mode, credentials, confirm);
    const firstInvalid = (['login', 'password', 'confirm'] as const).find(field => errors[field]);
    if (firstInvalid) {
      store.dispatch({ type: 'invalid', errors });
      return { focus: firstInvalid };
    }

    const submitted = ++version;
    store.dispatch({ type: 'submit' });
    try {
      if (mode === 'register') await api.register(credentials);
      if (submitted !== version) return;
      const user = await api.login(credentials);
      if (submitted === version) navigate(homeFor(user));
    } catch (error) {
      if (submitted !== version) return;
      store.dispatch({ type: 'failed', message: messages[errorCode(error)] ?? 'Сервис временно недоступен. Попробуйте позже' });
      return { focus: 'password', clearPasswords: true };
    }
  }

  return {
    subscribe: store.subscribe,
    select: (mode: Mode) => store.dispatch({ type: 'select', mode }),
    check, submit,
    destroy() { version++; },
  };
}
