<script lang="ts">
  import { REPORT_FILTERS, type ReportStatus } from "../../entities/admin";
  import { formatActivity } from "../../shared/lib/ru-format";
  import type { ReportsModel } from "./model";

  let { model, now }: { model: ReportsModel; now: Date } = $props();
  const filterNames = { new: "Новые", resolved: "Рассмотренные", dismissed: "Отклонённые", all: "Все" };
  const reasons = { scary: "Страшно", rude: "Грубо или обидно", wrong: "Неправильно или непонятно", other: "Другое" };
  const statuses = { new: "Новая", resolved: "Рассмотрена", dismissed: "Отклонена" };
  const actions: Record<ReportStatus, [ReportStatus, string][]> = {
    new: [["resolved", "Рассмотрено"], ["dismissed", "Отклонить"]],
    resolved: [["new", "Вернуть в новые"]],
    dismissed: [["new", "Вернуть в новые"]],
  };
</script>

<section class="adm-panel adm-reports-panel" id="reports" aria-labelledby="reportsTitle">
  <div class="adm-panel-heading">
    <div><p class="adm-section-kicker">Безопасность</p><h2 id="reportsTitle">Жалобы на ответы</h2></div>
    <div class="adm-periods adm-report-filters" role="group" aria-label="Статус жалоб">
      {#each REPORT_FILTERS as filter}
        <button type="button" data-report-filter={filter} aria-pressed={filter === $model.filter} onclick={() => model.load(filter)}>{filterNames[filter]}</button>
      {/each}
    </div>
  </div>
  <p class="adm-reports-error" id="adminReportsError" role="alert" hidden={!$model.error}>{$model.error}</p>
  <div class="adm-reports" id="adminReports" role="list">
    {#if $model.reports}
      {#each $model.reports as report (report.id)}
        <article class="adm-report adm-report-{report.status}" data-report-id={report.id} role="listitem">
          <div class="adm-report-head">
            <span class="adm-report-reason">{reasons[report.reason]}</span>
            <span class="adm-report-status">{statuses[report.status]}</span>
            <span class="adm-report-date">{formatActivity(report.createdAt, now)}</span>
            {#if report.dialogDeleted}<span class="adm-report-deleted">история удалена</span>{/if}
          </div>
          {#if report.comment}<p class="adm-report-comment">«{report.comment}»</p>{/if}
          <div class="adm-report-text"><span class="adm-report-label">Запрос</span><p class="adm-report-body">{report.requestText ?? "—"}</p></div>
          <div class="adm-report-text"><span class="adm-report-label">Ответ</span><p class="adm-report-body">{report.answerText}</p></div>
          <div class="adm-report-actions">
            {#each actions[report.status] as [status, label]}
              <button type="button" data-status={status} class="adm-report-action adm-report-action-{status}" disabled={$model.pending.includes(report.id)} onclick={() => model.change(report, status)}>{label}</button>
            {/each}
          </div>
        </article>
      {:else}
        <p class="adm-reports-empty" role="listitem">Жалоб нет</p>
      {/each}
    {/if}
  </div>
</section>
