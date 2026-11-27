<script lang="ts">
  import { untrack } from "svelte";
  import { Ratings, Report } from "../../features/answer-feedback";
  import { Voiceover } from "../../features/voiceover";
  import type { ChatMessage, MessageActions } from "./types";

  let { dialogId, id, message, actions, voice, open, toggle }: {
    dialogId: string; id: number; message: ChatMessage; actions: MessageActions;
    voice: string; open: boolean; toggle: (value: boolean) => void;
  } = $props();
  let rated = $state(untrack(() => message.feedback != null));
</script>
<div class="sai-feedback" class:is-rated={rated}>
  <Ratings initial={message.feedback ?? null} rate={score => actions.rate(id, score)} notify={actions.notify} onselection={value => rated = value} />
  <Report initial={message.report ?? null} {open} {toggle} send={(reason, comment) => actions.report(id, reason, comment)} notify={actions.notify} />
  <Voiceover {dialogId} {id} {voice} available={message.audioVoices ?? []}
    startAudio={actions.startAudio} getAudio={actions.getAudio} downloadAudio={actions.downloadAudio} />
</div>
