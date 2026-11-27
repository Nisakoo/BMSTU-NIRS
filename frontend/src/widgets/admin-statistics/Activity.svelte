<script lang="ts">
  import type { AdminStats } from "../../entities/admin";
  import { formatInteger } from "../../shared/lib/ru-format";

  let { stats }: { stats: AdminStats } = $props();
  const date = new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit" });
  let points = $derived(stats.activity.map(({ start, dialogs }) => ({
    label: date.format(new Date(start)), value: dialogs,
  })));
  let maximum = $derived(Math.max(1, ...points.map(point => point.value)));
  let description = $derived(points.map(p => p.label + ": " + formatInteger(p.value)).join(", "));
</script>

<section class="adm-panel adm-activity-panel" id="activity" aria-labelledby="activityTitle">
  <div class="adm-panel-heading">
    <div><p class="adm-section-kicker">Динамика</p><h2 id="activityTitle">Активность диалогов</h2></div>
  </div>
  <div class="adm-chart" id="adminActivity" aria-hidden="true">
    {#each points as point}
      {@const height = point.value === 0 ? 0 : Math.max(12, Math.round(100 * point.value / maximum))}
      <div class="adm-chart-column" aria-label={point.label + ": " + formatInteger(point.value)}>
        <span class="adm-chart-value">{formatInteger(point.value)}</span>
        <span class="adm-chart-track">
          <span class="adm-chart-bar" class:adm-chart-bar-empty={point.value === 0} style:height={height + "%"}></span>
        </span>
        <span class="adm-chart-label">{point.label}</span>
      </div>
    {/each}
    {#if stats.dialogs === 0}<p class="adm-chart-empty">Историй за период нет</p>{/if}
  </div>
  <p class="adm-sr-only" id="adminChartDescription">{stats.dialogs === 0 ? `Историй за ${stats.period} дней нет.` : `Истории за ${stats.period} дней: ${description}.`}</p>
</section>
