<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { formatInteger } from "../../shared/lib/ru-format";

  let { newCount }: { newCount: number } = $props();
  const sections = [
    { hash: "#overview", label: "Обзор", icon: "◈" },
    { hash: "#activity", label: "Активность", icon: "⌁" },
    { hash: "#users", label: "Пользователи", icon: "◎" },
    { hash: "#reports", label: "Жалобы", icon: "⚑" },
  ];
  const supported = (hash: string) => sections.find(section => section.hash === hash)?.hash ?? "#overview";
  let active = $state("#overview");
  let hold: number | undefined;
  let frame: number | undefined;

  function release() {
    window.clearTimeout(hold);
    hold = undefined;
  }

  function choose(hash: string) {
    active = supported(hash);
    release();
    hold = window.setTimeout(release, 1000);
  }

  function follow() {
    frame = undefined;
    if (hold !== undefined) return;
    const visible = sections.flatMap(({ hash }) => {
      const rect = document.querySelector(hash)?.getBoundingClientRect();
      return rect && rect.height > 0 ? [{ hash, top: rect.top }] : [];
    });
    if (visible.length === 0) return;
    const pageHeight = document.documentElement.scrollHeight;
    const atBottom = pageHeight > window.innerHeight && window.scrollY + window.innerHeight >= pageHeight - 2;
    const passed = visible.filter(section => section.top <= window.innerHeight * 0.35);
    active = (atBottom ? visible.at(-1) : passed.at(-1))?.hash ?? visible[0].hash;
  }

  function schedule() {
    if (hold === undefined && frame === undefined) frame = window.requestAnimationFrame(follow);
  }

  onMount(() => { active = supported(window.location.hash); });
  onDestroy(() => {
    release();
    if (frame !== undefined) window.cancelAnimationFrame(frame);
  });
</script>

<svelte:window onhashchange={() => choose(window.location.hash)} onscroll={schedule} onresize={schedule} onscrollend={release} />
<nav class="adm-nav" aria-label="Разделы панели">
  {#each sections as section (section.hash)}
    <a href={section.hash} data-admin-nav aria-current={active === section.hash ? "location" : undefined} onclick={() => choose(section.hash)}>
      <span aria-hidden="true">{section.icon}</span>{section.label}{#if section.hash === "#reports"}<b class="adm-nav-badge" id="adminReportsBadge" hidden={newCount === 0}>{formatInteger(newCount)}</b>{/if}
    </a>
  {/each}
</nav>
