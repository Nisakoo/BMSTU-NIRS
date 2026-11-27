<script lang="ts">
  import { tick } from "svelte";
  import type { ChatState } from "../model/state";
  let { chat, locked, open, openSettings, settings, create, select, remove, reload, logout, close }: {
    chat: ChatState; locked: boolean; open: boolean; settings: boolean;
    openSettings: (trigger: HTMLButtonElement) => void; create: () => void;
    select: (id: string) => void; remove: (id: string) => Promise<void>;
    reload: () => void; logout: () => void; close: () => void;
  } = $props();
  let confirming = $state<string | null>(null);
  let rows: HTMLUListElement;
  let cancelButton = $state<HTMLButtonElement>();
  async function ask(id: string) {
    confirming = id;
    await tick();
    cancelButton?.focus();
  }
  async function cancel() {
    const id = confirming;
    confirming = null;
    await tick();
    Array.from(rows.querySelectorAll<HTMLButtonElement>(".sai-history-delete")).find(el => el.dataset.id === id)?.focus();
  }
</script>
<svelte:document onkeydown={e => { if (e.key === "Escape" && !e.defaultPrevented && !settings && confirming && !chat.deletingId) void cancel(); }} />
<aside class="sai-sidebar" class:is-open={open} id="saiSidebar" aria-label="Мои истории">
  <a class="sai-brand" href="/"><span class="sai-mark" aria-hidden="true">✦</span>Смешарики AI</a>
  <button class="sai-new" id="saiNewStory" type="button" disabled={locked || !chat.user} onclick={() => { close(); create(); }}>+ Новая история</button>
  <h2 class="sai-history-title">Мои истории</h2>
  <nav class="sai-history-wrap" aria-label="Сохранённые истории">
    <ul class="sai-history" id="saiHistory" bind:this={rows}>
      {#each chat.dialogs as item (item.dialogId)}
        {@const label = item.title ?? "Без названия"}
        <li class="sai-history-row" class:is-confirming={confirming === item.dialogId}>
          {#if confirming === item.dialogId}
            <span class="sai-history-confirm-text">Удалить историю?</span>
            <button type="button" class="sai-history-confirm-delete" disabled={locked} onclick={async () => { await remove(item.dialogId); confirming = null; }}>Удалить</button>
            <button type="button" class="sai-history-confirm-cancel" disabled={locked} bind:this={cancelButton} onclick={cancel}>Отмена</button>
          {:else}
            <button type="button" class="sai-history-item" title={label} aria-current={item.dialogId === chat.dialogId ? "true" : undefined} disabled={locked}
              onclick={() => { close(); select(item.dialogId); }}>{label}</button>
            <button type="button" class="sai-history-delete" data-id={item.dialogId} aria-label={`Удалить историю «${label}»`} title="Удалить историю" disabled={locked} onclick={() => ask(item.dialogId)}></button>
          {/if}
        </li>
      {/each}
    </ul>
    <p class="sai-history-state" id="saiHistoryState">{chat.history === "failed" ? "Не удалось загрузить истории" : chat.history === "loading" ? "Загрузка…" : chat.dialogs.length ? "" : "Здесь появятся ваши истории"}</p>
    <button class="sai-history-retry" id="saiHistoryRetry" type="button" hidden={chat.history !== "failed"} onclick={reload}>Повторить</button>
  </nav>
    <a class="sai-admin-link" id="saiAdminLink" href="/admin/" hidden={chat.user?.role !== "admin"}><span aria-hidden="true">⚙</span>Панель администратора</a>
    <button class="sai-settings-button" id="saiSettingsButton" type="button" aria-haspopup="dialog" aria-controls="saiSettings" aria-expanded={settings} onclick={e => openSettings(e.currentTarget)}><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>Настройки</button>
    <div class="sai-user">
      <span class="sai-user-avatar" aria-hidden="true">✦</span>
      <span class="sai-user-login" id="saiUserLogin" title={chat.user?.login}>{chat.user?.login ?? ""}</span>
      <button class="sai-logout" disabled={chat.loggingOut} onclick={logout} id="saiLogout" type="button"><svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M14 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" stroke="currentColor" stroke-width="2" stroke-linecap="round"/><path d="M10 8l-4 4 4 4M6 12h9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>Выйти</button>
    </div>
  </aside>
