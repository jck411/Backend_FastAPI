export function autoSize(
  node: HTMLTextAreaElement,
  _value?: string | null,
): {
  update: (value?: string | null) => void;
  destroy: () => void;
} {
  const resize = (): void => {
    node.style.height = "auto";
    node.style.height = `${node.scrollHeight}px`;
  };

  const handleInput = (): void => resize();

  resize();
  node.addEventListener("input", handleInput);

  return {
    update: () => resize(),
    destroy: () => {
      node.removeEventListener("input", handleInput);
    },
  };
}
