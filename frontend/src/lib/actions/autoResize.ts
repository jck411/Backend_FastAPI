export interface AutoResizeOptions {
  // Multiplier for maximum height relative to initial height
  maxMultiplier?: number; // default 2
}

/**
 * Svelte action to auto-resize a textarea as the user types,
 * clamped to a maximum height of N times its initial height (default 2x).
 */
export function autoResize(
  node: HTMLTextAreaElement,
  opts: AutoResizeOptions | string | number | null = null,
) {
  let initialHeight = 0;
  let maxMultiplier = 2;

  // Allow shorthand like use:autoResize={prompt} or use:autoResize={2}
  function resolveOptions(options: AutoResizeOptions | string | number | null) {
    if (typeof options === 'number') {
      maxMultiplier = Number.isFinite(options) && options > 0 ? options : 2;
    } else if (options && typeof options === 'object' && 'maxMultiplier' in options) {
      const mm = (options as AutoResizeOptions).maxMultiplier;
      if (typeof mm === 'number' && Number.isFinite(mm) && mm > 0) {
        maxMultiplier = mm;
      }
    }
  }

  resolveOptions(opts);

  // Compute initial height after layout
  function measure() {
    // If unset, let the browser size it naturally for a single row
    const prevHeight = node.style.height;
    node.style.height = 'auto';
    initialHeight = node.clientHeight || node.scrollHeight || 0;
    node.style.height = prevHeight;
    if (!initialHeight) {
      // Fallback to computed line-height
      const cs = getComputedStyle(node);
      const lh = parseFloat(cs.lineHeight || '0');
      initialHeight = lh || 24; // sensible default
    }
  }

  function clampResize() {
    const maxHeight = Math.max(1, Math.round(initialHeight * maxMultiplier));
    // Reset to auto to measure content height accurately
    node.style.height = 'auto';
    const needed = node.scrollHeight;
    const next = Math.min(needed, maxHeight);
    node.style.height = `${next}px`;
    node.style.overflowY = needed > maxHeight ? 'auto' : 'hidden';
    node.style.maxHeight = `${maxHeight}px`;
  }

  function onInput() {
    clampResize();
  }

  // Initial measure + resize after current frame to ensure styles applied
  const raf = requestAnimationFrame(() => {
    measure();
    clampResize();
  });

  node.addEventListener('input', onInput);

  return {
    update(newOpts: AutoResizeOptions | string | number | null) {
      resolveOptions(newOpts);
      // Re-measure in case styles changed or content updated programmatically
      measure();
      clampResize();
    },
    destroy() {
      cancelAnimationFrame(raf);
      node.removeEventListener('input', onInput);
      // Clean up overflow if we changed it
      node.style.overflowY = '';
      node.style.maxHeight = '';
    },
  };
}

