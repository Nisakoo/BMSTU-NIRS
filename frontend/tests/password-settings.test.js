// @vitest-environment jsdom
import { afterEach, expect, test, vi } from 'vitest';
import { flushSync, mount, unmount } from 'svelte';
import { PasswordSettings } from '../src/features/password/index.ts';
import { AuthApiError } from '../src/entities/session/index.ts';

let dialog;
afterEach(async () => {
  if (dialog) await unmount(dialog);
  document.body.replaceChildren();
});

function render(changePassword, variant = 'chat') {
  const onclose = vi.fn();
  const prefix = variant === 'chat' ? 'sai' : 'admin';
  dialog = mount(PasswordSettings, {
    target: document.body,
    props: { variant, open: true, onclose, changePassword },
  });
  flushSync();
  const get = suffix => document.getElementById(prefix + suffix);
  const fields = ['CurrentPassword', 'NewPassword', 'RepeatPassword'].map(get);
  return {
    fields, status: get('PasswordStatus'), onclose,
    close: get('SettingsClose'), backdrop: get('Settings'),
    submit(current = 'carrot123', next = 'radish456', repeat = next) {
      const values = [current, next, repeat];
      fields.forEach((field, index) => { field.value = values[index]; });
      get('PasswordForm').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
      flushSync();
    },
  };
}

test.each(['chat', 'admin'])('%s settings focus the current password and clear fields on dismiss', variant => {
  const view = render(vi.fn(), variant);
  expect(document.activeElement).toBe(view.fields[0]);
  view.fields[0].value = 'carrot123';
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  expect(view.onclose).toHaveBeenCalledOnce();
  expect(view.fields[0].value).toBe('');
});

test('validation keeps invalid credentials local', () => {
  const changePassword = vi.fn();
  const view = render(changePassword);
  const cases = [
    [['short', 'radish456'], 'Пароль должен быть от 8 до 128 символов'],
    [['carrot123', 'a'.repeat(129)], 'Пароль должен быть от 8 до 128 символов'],
    [['carrot123', 'radish456', 'radish4567'], 'Пароли не совпадают'],
    [['carrot123', 'carrot123'], 'Новый пароль совпадает с текущим'],
  ];
  for (const [values, message] of cases) {
    view.submit(...values);
    expect(view.status.textContent).toBe(message);
  }
  expect(changePassword).not.toHaveBeenCalled();
});

test('a pending save locks settings until success and clears all passwords', async () => {
  let finish;
  const changePassword = vi.fn(() => new Promise(resolve => { finish = resolve; }));
  const view = render(changePassword);
  view.submit();
  expect(view.fields.every(field => field.disabled)).toBe(true);
  expect(view.close.disabled).toBe(true);
  view.submit();
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  view.backdrop.click();
  expect(view.onclose).not.toHaveBeenCalled();
  expect(changePassword.mock.calls).toEqual([[{ currentPassword: 'carrot123', newPassword: 'radish456' }]]);
  finish();
  await vi.waitFor(() => expect(view.status.dataset.state).toBe('ok'));
  expect(view.status.textContent).toBe('Пароль изменён. На других устройствах нужно войти заново');
  expect(view.fields.every(field => !field.disabled && !field.value)).toBe(true);
});

test.each([
  ['wrong_password', 'Неверный текущий пароль'],
  ['same_password', 'Новый пароль совпадает с текущим'],
  ['invalid_fields', 'Пароль должен быть от 8 до 128 символов'],
  ['too_many_attempts', 'Слишком много попыток. Попробуйте позже'],
  ['unavailable', 'Не удалось сменить пароль. Попробуйте ещё раз'],
])('save reports %s and keeps the window available', async (code, message) => {
  const view = render(() => Promise.reject(new AuthApiError(code)));
  view.submit();
  await vi.waitFor(() => expect(view.status.textContent).toBe(message));
  expect(view.fields[0].value).toBe(code === 'wrong_password' ? '' : 'carrot123');
  expect(view.fields[1].value).toBe('radish456');
  expect(view.close.disabled).toBe(false);
  if (code === 'wrong_password') expect(document.activeElement).toBe(view.fields[0]);
});
