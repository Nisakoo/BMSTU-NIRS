<script lang="ts">
  import type { AdminStats } from "../../entities/admin";
  import { formatActivity, formatDay, formatInteger } from "../../shared/lib/ru-format";

  let { users, now }: { users: AdminStats["recentUsers"]; now: Date } = $props();
  function initials(name: string) {
    return name.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join("").toUpperCase();
  }
</script>

<section class="adm-panel adm-users-panel" id="users" aria-labelledby="usersTitle">
  <div class="adm-panel-heading">
    <div><p class="adm-section-kicker">Аудитория</p><h2 id="usersTitle">Последние пользователи</h2></div>
    <span class="adm-caption">по последней активности</span>
  </div>
  <div class="adm-user-head" aria-hidden="true">
    <span>Пользователь</span><span>Активность</span><span>Диалоги</span><span>Регистрация</span>
  </div>
  <div class="adm-users" id="adminUsers" role="list">
    {#each users as user (user.id)}
      <article class="adm-user-row" role="listitem">
        <div class="adm-user-identity">
          <span class="adm-user-avatar">{initials(user.login)}</span>
          <span class="adm-user-details"><strong>{user.login}</strong><small>{user.role === "admin" ? "администратор" : "пользователь"}</small></span>
        </div>
        <span class="adm-user-cell" data-label="Активность">{user.lastActiveAt ? formatActivity(user.lastActiveAt, now) : "ещё не входил"}</span>
        <span class="adm-user-cell" data-label="Диалоги">{formatInteger(user.dialogs)}</span>
        <span class="adm-user-cell" data-label="Регистрация">{formatDay(user.registeredAt, now)}</span>
      </article>
    {:else}
      <p class="adm-users-empty" role="listitem">Пользователей пока нет</p>
    {/each}
  </div>
</section>
