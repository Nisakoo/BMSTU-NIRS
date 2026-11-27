<script lang="ts">
  import { untrack } from "svelte";
  import { createRating } from "./model";
  import ezhik from "../../static/faces/1-ezhik.png";
  import nyusha from "../../static/faces/2-nyusha.png";
  import losyash from "../../static/faces/3-losyash.png";
  import kopatych from "../../static/faces/4-kopatych.png";
  import krosh from "../../static/faces/5-krosh.png";

  const faces = [
    [ezhik, "Совсем не понравилось", "Ёжик грустит"],
    [nyusha, "Скорее не понравилось", "Нюша недовольна"],
    [losyash, "Так себе", "Лосяш задумался"],
    [kopatych, "Понравилось", "Копатыч доволен"],
    [krosh, "Очень понравилось!", "Крош в восторге!"],
  ] as const;
  let { initial, rate, notify, onselection }:
    { initial: number | null; rate: (score: number | null) => Promise<void>;
      notify: (text: string, kind: "error") => void; onselection: (rated: boolean) => void } = $props();
  const model = untrack(() => createRating(initial, rate));
  let score = $derived($model.score);
  $effect(() => onselection(score !== null));
  async function choose(next: number) {
    try {
      await model.choose(next);
    } catch {
      notify("Не удалось сохранить оценку", "error");
    }
  }
</script>
<span class="sai-feedback-q">Как тебе история?</span>
{#each faces as [image, label], i (image)}
  <button type="button" class="sai-face" class:is-selected={score === i + 1} data-value={i + 1} aria-label={`Оценка ${i+1} из 5: ${label}`}
    aria-pressed={score === i + 1} disabled={$model.pending} onclick={() => choose(i + 1)}>
    <img data-score={i + 1} src={image} alt="" width="72" height="72" /><span class="sai-face-tip">{label}</span>
  </button>
{/each}
<span class="sai-feedback-say">{score ? faces[score - 1][2] : ""}</span>
