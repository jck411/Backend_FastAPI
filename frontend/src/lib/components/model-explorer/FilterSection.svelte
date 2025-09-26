<script lang="ts">
  export let title: string;
  export let startOpen = false;
  export let forceOpen = false;

  let expanded = startOpen;
  let wasForcedOpen = false;
  const panelId = createPanelId(title);

  function toggle() {
    if (forceOpen) {
      return;
    }
    expanded = !expanded;
  }

  function createPanelId(value: string): string {
    const normalized = value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/(^-|-$)/g, '') || 'section';
    const hash = Math.abs(
      Array.from(value).reduce((acc, char) => acc * 31 + char.charCodeAt(0), 7),
    ).toString(36);
    return `filter-section-${normalized}-${hash}`;
  }
  $: if (forceOpen) {
    if (!expanded) {
      expanded = true;
    }
    wasForcedOpen = true;
  } else if (wasForcedOpen) {
    expanded = startOpen;
    wasForcedOpen = false;
  }
</script>

<section class={`filter-section ${expanded ? 'expanded' : 'collapsed'}`}>
  <header>
    <button
      type="button"
      class="toggle"
      aria-expanded={expanded}
      aria-controls={panelId}
      on:click={toggle}
      aria-disabled={forceOpen}
      class:locked={forceOpen}
    >
      <span class="title">{title}</span>
      <span class="chevron" aria-hidden="true"></span>
    </button>
  </header>
  <div id={panelId} class="content" hidden={!expanded}>
    <slot />
  </div>
</section>

<style>
  .filter-section {
    border: 1px solid #1c253f;
    border-radius: 0.9rem;
    padding: 0;
    background: rgba(10, 16, 29, 0.92);
    transition: border-color 0.2s ease, background 0.2s ease;
  }

  .filter-section.expanded {
    border-color: #2a3760;
    background: rgba(12, 19, 34, 0.95);
  }

  .filter-section header {
    margin: 0;
  }

  .toggle {
    width: 100%;
    border: none;
    background: none;
    color: inherit;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 0.95rem 1.1rem;
    font-size: 0.95rem;
    font-weight: 600;
    cursor: pointer;
    transition: color 0.2s ease;
  }

  .toggle:hover,
  .toggle:focus-visible {
    color: #38bdf8;
  }

  .toggle.locked {
    cursor: default;
    pointer-events: none;
    color: inherit;
  }

  .toggle:focus-visible {
    outline: 2px solid #38bdf8;
    outline-offset: 2px;
  }

  .toggle:focus:not(:focus-visible) {
    outline: none;
  }

  .title {
    flex: 1;
    text-align: left;
  }

  .chevron {
    width: 0.9rem;
    height: 0.9rem;
    position: relative;
    transition: transform 0.25s ease;
  }

  .chevron::before {
    content: '';
    position: absolute;
    inset: 0;
    mask: url('data:image/svg+xml,%3Csvg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"%3E%3Cpath fill="white" d="m8.59 16.59 1.41 1.41L16 12l-5.99-5.99-1.41 1.41L13.17 12z"/%3E%3C/svg%3E') center / contain no-repeat;
    background: currentColor;
  }

  .filter-section.expanded .chevron {
    transform: rotate(90deg);
  }

  .content {
    padding: 1rem 1.1rem 1.2rem;
    border-top: 1px solid rgba(28, 37, 63, 0.75);
  }

  .filter-section.collapsed .content {
    display: none;
  }
</style>
