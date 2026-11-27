<script module lang="ts">
  const phrases = [
    "Красим скамейку…",
    "Раскладываем фантики…",
    "Поливаем грядки…",
    "Ищем карту Кроша…",
  ];
  let lastPhrase: string;

  function pickPhrase() {
    const choices = phrases.filter(phrase => phrase !== lastPhrase);
    lastPhrase = choices[Math.floor(Math.random() * choices.length)];
    return lastPhrase;
  }
</script>

<script lang="ts">
  import { onMount } from "svelte";
  let phrase = $state(pickPhrase());

  onMount(() => {
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let timer: number | undefined;
    function updateMotion() {
      window.clearInterval(timer);
      if (!motion?.matches) {
        timer = window.setInterval(() => { phrase = pickPhrase(); }, 3000);
      }
    }
    updateMotion();
    motion?.addEventListener("change", updateMotion);
    return () => {
      window.clearInterval(timer);
      motion?.removeEventListener("change", updateMotion);
    };
  });
</script>

<div class="sai-row" data-story-waiting aria-hidden="true">
  <div class="sai-msg-icon">⭐</div>
  <div class="sai-wait">
    <span class="sai-wait-dots"><i></i><i></i><i></i></span>
    <span class="sai-wait-phrase">{phrase}</span>
  </div>
</div>

<style>
  .sai-wait {
    display: flex;
    align-items: center;
    gap: .7rem;
    width: min(15.5rem, calc(100% - 46px));
    min-height: 3.25rem;
    padding: .65rem 1rem;
    border: 1px solid #2c516d;
    border-radius: 20px 20px 20px 6px;
    background: rgba(18, 48, 74, .9);
    color: #c9e7f8;
    font: 600 .88rem/1.45 Inter, system-ui, sans-serif;
  }
  .sai-wait-dots { display: flex; align-items: center; gap: 3px; }
  .sai-wait-dots i {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #83d5f8;
    animation: pulse 1.25s ease-in-out infinite;
  }
  .sai-wait-dots i:nth-child(2) { animation-delay: .16s; }
  .sai-wait-dots i:nth-child(3) { animation-delay: .32s; }
  @keyframes pulse { 50% { transform: translateY(-3px); opacity: .55; } }
  @media (prefers-reduced-motion: reduce) {
    .sai-wait-dots i { animation: none; }
  }
</style>
