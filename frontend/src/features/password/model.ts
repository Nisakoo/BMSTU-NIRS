import { errorCode, type PasswordChange } from '../../entities/session';
import { createStore } from '../../shared/lib/store';

const lengthError = 'Пароль должен быть от 8 до 128 символов';
const sameError = 'Новый пароль совпадает с текущим';
const messages: Record<string, string> = {
  wrong_password: 'Неверный текущий пароль',
  same_password: sameError,
  invalid_fields: lengthError,
  too_many_attempts: 'Слишком много попыток. Попробуйте позже',
};

function passwordProblem({ currentPassword, newPassword }: PasswordChange, repeat: string) {
  if ([currentPassword, newPassword].some(value => value.length < 8 || value.length > 128)) return lengthError;
  if (newPassword !== repeat) return 'Пароли не совпадают';
  if (newPassword === currentPassword) return sameError;
}

type State = { status: '' | 'saving' | 'error' | 'ok'; message: string };
type Action = { type: 'reset' | 'save' | 'saved' } | { type: 'error'; message: string };
const initial: State = { status: '', message: '' };

function reduce(_: State, action: Action): State {
  switch (action.type) {
    case 'reset': return initial;
    case 'save': return { status: 'saving', message: 'Сохраняем…' };
    case 'saved': return { status: 'ok', message: 'Пароль изменён. На других устройствах нужно войти заново' };
    case 'error': return { status: 'error', message: action.message };
  }
}

export function createPasswordSettings(changePassword: (values: PasswordChange) => Promise<void>, isUnloading: () => boolean) {
  const store = createStore(initial, reduce);

  async function submit(passwords: PasswordChange, repeat: string) {
    if (store.getState().status === 'saving') return;
    const problem = passwordProblem(passwords, repeat);
    if (problem) {
      store.dispatch({ type: 'error', message: problem });
      return;
    }

    store.dispatch({ type: 'save' });
    try {
      await changePassword(passwords);
      if (isUnloading()) return;
      store.dispatch({ type: 'saved' });
      return 'clear-all';
    } catch (error) {
      if (isUnloading()) return;
      const code = errorCode(error);
      store.dispatch({ type: 'error', message: messages[code] ?? 'Не удалось сменить пароль. Попробуйте ещё раз' });
      if (code === 'wrong_password') return 'clear-current';
    }
  }
  return { subscribe: store.subscribe, reset: () => store.dispatch({ type: 'reset' }), submit };
}
