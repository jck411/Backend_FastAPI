const COPY_ICON =
  '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><rect width="8" height="4" x="8" y="2" rx="1" ry="1"></rect><path d="M8 4H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2"></path><path d="M16 4h2a2 2 0 0 1 2 2v4"></path><path d="M21 14H11"></path><path d="m15 10-4 4 4 4"></path></svg>';

const CHECK_ICON =
  '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"></path></svg>';

type CleanupFn = () => void;

type CopyButtonState = {
  cleanup: CleanupFn;
};

const COPIED_TIMEOUT_MS = 2000;
const COPY_BUTTON_CLASS = "copy-code-button";
const COPY_BLOCK_CLASS = "copy-code-block";

function attachCopyButton(pre: HTMLElement): CopyButtonState {
  pre.classList.add(COPY_BLOCK_CLASS);

  const button = document.createElement("button");
  button.type = "button";
  button.className = COPY_BUTTON_CLASS;
  button.setAttribute("aria-label", "Copy code");
  button.setAttribute("title", "Copy code");
  button.innerHTML = COPY_ICON;

  let resetHandle: number | null = null;

  const handleClick = async () => {
    const codeElement = pre.querySelector("code");
    const text = codeElement?.textContent ?? pre.textContent ?? "";

    if (!text) {
      return;
    }

    if (!navigator?.clipboard?.writeText) {
      console.warn("Clipboard API unavailable; cannot copy code block");
      return;
    }

    try {
      await navigator.clipboard.writeText(text);
    } catch (error) {
      console.error("Failed to copy code block", error);
      return;
    }

    if (resetHandle !== null) {
      window.clearTimeout(resetHandle);
    }

    button.classList.add("copied");
    button.setAttribute("aria-label", "Code copied");
    button.innerHTML = CHECK_ICON;

    resetHandle = window.setTimeout(() => {
      if (!pre.isConnected) {
        return;
      }
      button.classList.remove("copied");
      button.setAttribute("aria-label", "Copy code");
      button.innerHTML = COPY_ICON;
      resetHandle = null;
    }, COPIED_TIMEOUT_MS);
  };
  button.addEventListener("click", handleClick);

  pre.appendChild(button);

  return {
    cleanup: () => {
      button.removeEventListener("click", handleClick);
      if (resetHandle !== null) {
        window.clearTimeout(resetHandle);
      }
      button.remove();
      pre.classList.remove(COPY_BLOCK_CLASS);
    },
  };
}

function enhanceCodeBlocks(container: HTMLElement, states: Map<HTMLElement, CopyButtonState>): void {
  const blocks = container.querySelectorAll<HTMLElement>("pre");

  blocks.forEach((pre) => {
    if (!states.has(pre)) {
      states.set(pre, attachCopyButton(pre));
    }
  });

  Array.from(states.keys()).forEach((pre) => {
    if (!container.contains(pre)) {
      const state = states.get(pre);
      if (state) {
        state.cleanup();
        states.delete(pre);
      }
    }
  });
}

export function copyableCode(node: HTMLElement): { destroy: CleanupFn } {
  const states = new Map<HTMLElement, CopyButtonState>();

  const observer = new MutationObserver(() => {
    enhanceCodeBlocks(node, states);
  });

  observer.observe(node, { childList: true, subtree: true });
  enhanceCodeBlocks(node, states);

  return {
    destroy: () => {
      observer.disconnect();
      Array.from(states.values()).forEach((state) => state.cleanup());
      states.clear();
    },
  };
}
