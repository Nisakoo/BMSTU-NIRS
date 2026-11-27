<script lang="ts">
  import { onMount } from "svelte";
  import { PERIODS } from "../../entities/admin";
  import { PasswordSettings } from "../../features/password";
  import { Navigation } from "../../widgets/admin-navigation";
  import { Reports } from "../../widgets/admin-reports";
  import { Activity, Overview, Quality, Users } from "../../widgets/admin-statistics";
  import { greetingFor } from "./greeting";
  import type { Dashboard } from "./model";

  let { model, now = () => new Date() }: { model: Dashboard; now?: () => Date } = $props();
  let reports = $derived(model.reports);
  let settingsOpen = $state(false);
  let settingsButton: HTMLButtonElement;

  onMount(() => {
    void model.start();
    return () => model.dispose();
  });

  function closeSettings() {
    settingsOpen = false;
    settingsButton.focus();
  }
</script>

<div class="adm-ambient adm-ambient-one" aria-hidden="true"></div>
<div class="adm-ambient adm-ambient-two" aria-hidden="true"></div>
<div class="adm-shell">
  <aside class="adm-sidebar">
    <a class="adm-brand" href="/admin/" aria-label="Смешарики AI — панель администратора">
      <span class="adm-brand-mark" aria-hidden="true">✦</span>
      <span><strong>Смешарики AI</strong><small>панель администратора</small></span>
    </a>
    <Navigation newCount={$model.user ? $reports.newCount : 0} />
    <div class="adm-sidebar-foot">
      <a class="adm-chat-link" href="/">Пользовательский чат <span aria-hidden="true">↗</span></a>
      <button class="adm-settings-button" id="adminSettingsButton" type="button" aria-haspopup="dialog" aria-controls="adminSettings"
        aria-expanded={settingsOpen} disabled={!$model.user} bind:this={settingsButton} onclick={() => settingsOpen = true}>
        <svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="2"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/></svg>
        Настройки
      </button>
      <button class="adm-logout" id="adminLogout" type="button" disabled={!$model.user || $model.loggingOut} onclick={model.logout}>Выйти</button>
      <p class="adm-logout-error" id="adminLogoutError" role="alert" hidden={!$model.logoutFailed}>{$model.logoutFailed ? "Не удалось выйти. Попробуйте ещё раз" : ""}</p>
    </div>
  </aside>
  <main class="adm-main" id="adminDashboard">
    <header class="adm-topbar">
      <div>
        <p class="adm-eyebrow">Центр управления</p>
        <h1 id="adminGreeting">{$model.user ? greetingFor(now()) + ", " + $model.user.login : "Здравствуйте"}</h1>
        <p class="adm-lead">Следите за активностью аудитории и качеством работы агента.</p>
      </div>
    </header>
    <section class="adm-toolbar" aria-label="Настройки отчёта">
      <div>
        <span class="adm-toolbar-label">Период отчёта</span>
        <strong id="adminPeriodLabel">{$model.period} дней</strong>
      </div>
      <div class="adm-periods" role="group" aria-label="Выберите период">
        {#each PERIODS as period}
          <button type="button" data-period={period} aria-pressed={$model.period === period} disabled={!$model.user || $model.loading} onclick={() => model.load(period)}>{period} дней</button>
        {/each}
      </div>
    </section>
    <section class="adm-error" id="adminError" role="alert" aria-live="assertive" hidden={!$model.error}>{$model.error}</section>
    <div id="adminContent" hidden={!$model.stats}>
      {#if $model.stats}
        <Overview stats={$model.stats} />
        <div class="adm-analysis-grid">
          <Activity stats={$model.stats} />
          <Quality feedback={$model.stats.feedback} />
        </div>
        <Users users={$model.stats.recentUsers} now={now()} />
        <Reports model={reports} now={now()} />
      {/if}
    </div>
  </main>
</div>
{#if $model.user}
  <PasswordSettings variant="admin" open={settingsOpen} onclose={closeSettings} changePassword={model.changePassword} isUnloading={model.isUnloading} />
{/if}
