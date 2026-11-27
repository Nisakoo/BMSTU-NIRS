<script lang="ts">
  import type { AdminStats } from "../../entities/admin";
  import { formatInteger } from "../../shared/lib/ru-format";

  let { feedback }: { feedback: AdminStats["feedback"] } = $props();
  const scoreFormat = new Intl.NumberFormat("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  let rated = $derived(feedback.ratedAnswers);
  let totalScore = $derived(feedback.counts.reduce((sum, count, i) => sum + (i + 1) * count, 0));
</script>

<section class="adm-panel adm-quality-panel" aria-labelledby="qualityTitle">
  <div class="adm-panel-heading">
    <div><p class="adm-section-kicker">Состояние агента</p><h2 id="qualityTitle">Качество ответов</h2></div>
  </div>
  <div class="adm-quality" id="adminQuality">
    <div class="adm-quality-summary">
      {#if rated === 0}
        <strong class="adm-quality-empty">Оценок пока нет</strong>
      {:else}
        <div class="adm-quality-score">
          <strong class="adm-quality-average">{scoreFormat.format(totalScore / rated)}</strong>
          <span class="adm-quality-scale">из 5</span>
        </div>
      {/if}
      <span class="adm-quality-note">оценено {formatInteger(rated)} из {formatInteger(feedback.answersTotal)} ответов</span>
    </div>
    {#each [5, 4, 3, 2, 1] as score (score)}
      {@const count = feedback.counts[score - 1]}
      <div class="adm-quality-row" aria-label={`Оценка ${score} из 5: ${formatInteger(count)}`}>
        <span class="adm-quality-row-score">{score}</span>
        <span class="adm-quality-bar"><span class="adm-quality-bar-fill" style:width={(rated ? Math.round(100 * count / rated) : 0) + "%"}></span></span>
        <span class="adm-quality-count">{formatInteger(count)}</span>
      </div>
    {/each}
  </div>
</section>
