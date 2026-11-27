<script lang="ts">
  import { onDestroy } from "svelte";
  let { text, onerror }: { text: string; onerror: () => void } = $props();
  let copied = $state(false);
  let timer: number | undefined;
  let disposed = false;
  onDestroy(() => { disposed = true; window.clearTimeout(timer); });

  function fallback() {
    const area = document.createElement("textarea");
    area.readOnly = true;
    area.value = text;
    area.className = "sai-copy-buffer";
    document.body.append(area);
    try {
      area.select();
      return document.execCommand("copy");
    } catch {
      return false;
    } finally {
      area.remove();
    }
  }
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      if (!fallback()) return onerror();
    }
    if (disposed) return;
    copied = true;
    window.clearTimeout(timer);
    timer = window.setTimeout(() => copied = false, 1500);
  }
</script>
<button type="button" class="sai-copy" class:is-done={copied} aria-label="Скопировать сообщение" onclick={copy}>{copied ? "Скопировано" : "Копировать"}</button>
