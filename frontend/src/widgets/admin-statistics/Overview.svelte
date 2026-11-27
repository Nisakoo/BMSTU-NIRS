<script lang="ts">
  import type { AdminStats } from "../../entities/admin";
  import { formatInteger } from "../../shared/lib/ru-format";

  let { stats }: { stats: AdminStats } = $props();
  const metrics = [
    { key: "usersTotal", label: "Всего пользователей", hint: "зарегистрировано", icon: "◎", tone: "blue" },
    { key: "activeUsers", label: "Активные пользователи", hint: "входили за период", icon: "↗", tone: "green" },
    { key: "dialogs", label: "Диалоги", hint: "историй за период", icon: "⌁", tone: "violet" },
    { key: "messages", label: "Сообщения", hint: "пользовательских и AI", icon: "✦", tone: "pink" },
  ] as const;
</script>

<section id="overview" aria-labelledby="overviewTitle">
  <div class="adm-section-heading">
    <div>
      <p class="adm-section-kicker">Общая картина</p>
      <h2 id="overviewTitle">Ключевые показатели</h2>
    </div>
    <span class="adm-comparison" id="adminComparison">Новых пользователей: {formatInteger(stats.newUsers)}</span>
  </div>
  <div class="adm-metrics" id="adminMetrics">
    {#each metrics as metric (metric.key)}
      <article class="adm-metric adm-metric-{metric.tone}" data-metric={metric.key}>
        <div class="adm-metric-head">
          <span class="adm-metric-label">{metric.label}</span>
          <span class="adm-metric-icon">{metric.icon}</span>
        </div>
        <strong class="adm-metric-value">{formatInteger(stats[metric.key])}</strong>
        <span class="adm-metric-hint">{metric.hint}</span>
      </article>
    {/each}
  </div>
</section>
