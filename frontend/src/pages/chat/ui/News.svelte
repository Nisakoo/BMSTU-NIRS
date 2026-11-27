<script lang="ts">
  import krosh from "../../../static/faces/5-krosh.png";
  import type { ReportNewsItem } from "../../../entities/dialog";
  let { news, dismiss, open }: { news: ReportNewsItem[]; dismiss: () => void; open: (id: string) => void } = $props();
  let item = $derived(news[0]);
  let story = $derived(item?.dialogId != null && item.dialogTitle !== null ? `на историю «${item.dialogTitle}»` : "на одну историю");
</script>
<div class="sai-news" id="saiNews" role="status" hidden={!news.length}>
  {#if item}
    <img src={krosh} class="sai-news-face" alt="" width="72" height="72" />
    <p class="sai-news-say">{news.length > 1 ? `Взрослые посмотрели твои жалобы (${news.length}). Спасибо, что рассказал!` : `Взрослые посмотрели твою жалобу ${story}. Спасибо, что рассказал!`}</p>
    <div class="sai-news-actions">
      <button class="sai-news-ok" type="button" onclick={dismiss}>Хорошо</button>
      {#if news.length === 1 && item.dialogId !== null}
        <button class="sai-news-open" type="button" onclick={() => { const id = item.dialogId!; dismiss(); open(id); }}>Открыть историю</button>
      {/if}
    </div>
  {/if}
</div>
