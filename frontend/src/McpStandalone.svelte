<script lang="ts">
  import McpServersModal from "./lib/components/chat/McpServersModal.svelte";
  import "./app.css";

  // Always open
  let open = true;

  function handleClose(): void {
    // Close the window when modal closes
    window.close();
  }
</script>

<div class="mcp-standalone">
  <McpServersModal {open} on:close={handleClose} />
</div>

<style>
  .mcp-standalone {
    min-height: 100vh;
    background: radial-gradient(
      circle at top,
      #162135 0%,
      #05070f 55%,
      #04060d 100%
    );
  }
</style>
