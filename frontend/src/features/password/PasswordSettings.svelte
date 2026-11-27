<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import type { PasswordChange } from '../../entities/session';
  import { createPasswordSettings } from './model';

  interface Props {
    variant: 'admin' | 'chat';
    open: boolean;
    onclose: () => void;
    changePassword: (values: PasswordChange) => Promise<void>;
    isUnloading?: () => boolean;
  }
  let { variant, open, onclose, changePassword, isUnloading = () => false }: Props = $props();
  let disposed = false;
  onDestroy(() => { disposed = true; });
  const settings = createPasswordSettings(values => changePassword(values), () => disposed || isUnloading());
  let prefix = $derived(variant === 'admin' ? 'admin' : 'sai');
  let css = $derived(variant === 'admin' ? 'adm' : 'sai');
  let locked = $derived($settings.status === 'saving');
  let form: HTMLFormElement;
  let current: HTMLInputElement;
  let next: HTMLInputElement;
  let repeat: HTMLInputElement;

  $effect(() => { if (open) current.focus(); });

  function close() {
    if (!open || locked) return;
    form.reset();
    settings.reset();
    onclose();
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    if (!open) return;
    const result = await settings.submit({ currentPassword: current.value, newPassword: next.value }, repeat.value);
    if (result === 'clear-all') form.reset();
    if (result === 'clear-current') {
      await tick();
      current.value = '';
      current.focus();
    }
  }
</script>

<svelte:document onkeydown={event => { if (event.key === 'Escape') close(); }} />
<div class="{css}-settings" id="{prefix}Settings" hidden={!open} role="presentation"
  onclick={event => { if (event.target === event.currentTarget) close(); }}>
  <div class="{css}-settings-card" role="dialog" aria-modal="true" aria-labelledby="{prefix}SettingsTitle">
    <div class="{css}-settings-head">
      <h2 class="{css}-settings-title" id="{prefix}SettingsTitle">Настройки</h2>
      <button class="{css}-settings-close" id="{prefix}SettingsClose" type="button" aria-label="Закрыть" title="Закрыть" disabled={locked} onclick={close}>×</button>
    </div>
    <form class="{css}-password" id="{prefix}PasswordForm" bind:this={form} method="post" novalidate onsubmit={submit}>
      <h3 class="{css}-password-title">Сменить пароль</h3>
      <label class="{css}-password-field">Текущий пароль
        <input id="{prefix}CurrentPassword" bind:this={current} type="password" autocomplete="current-password" disabled={locked} required />
      </label>
      <label class="{css}-password-field">Новый пароль
        <input id="{prefix}NewPassword" bind:this={next} type="password" autocomplete="new-password" disabled={locked} required />
      </label>
      <label class="{css}-password-field">Повторите новый пароль
        <input id="{prefix}RepeatPassword" bind:this={repeat} type="password" autocomplete="new-password" disabled={locked} required />
      </label>
      <p class="{css}-password-status" id="{prefix}PasswordStatus" data-state={$settings.status} aria-live="polite">{$settings.message}</p>
      <button class="{css}-password-save" id="{prefix}PasswordSave" type="submit" disabled={locked}>Сохранить</button>
    </form>
  </div>
</div>
