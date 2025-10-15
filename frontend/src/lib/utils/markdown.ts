import MarkdownIt from "markdown-it";
import DOMPurify from "dompurify";
import type { Config } from "dompurify";

const markdownRenderer = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
});

const sanitizerConfig: Config = {
  USE_PROFILES: { html: true },
  ADD_ATTR: ["target", "rel", "class", "colspan", "rowspan", "scope"],
  ADD_TAGS: ["table", "thead", "tbody", "tfoot", "tr", "th", "td"],
};

// Ensure all links open in a new tab and are safe
DOMPurify.addHook("afterSanitizeAttributes", (node) => {
  // Only process anchor elements
  // Using tagName check to avoid relying on DOM globals in different environments
  const el = node as unknown as Element;
  if (!el || typeof (el as any).tagName !== "string") return;
  if (el.tagName.toUpperCase() !== "A") return;

  // Always open links in a new tab
  el.setAttribute("target", "_blank");

  // Ensure safe rel attributes (merge with any existing ones)
  const existing = (el.getAttribute("rel") || "").split(/\s+/).filter(Boolean);
  const required = ["noopener", "noreferrer", "nofollow", "ugc"];
  const merged = Array.from(new Set([...existing, ...required]));
  el.setAttribute("rel", merged.join(" "));
});

export function renderMarkdown(source: string | null | undefined): string {
  if (!source) {
    return "";
  }

  const rendered = markdownRenderer.render(source);
  return DOMPurify.sanitize(rendered, sanitizerConfig);
}
