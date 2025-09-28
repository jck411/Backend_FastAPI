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

export function renderMarkdown(source: string | null | undefined): string {
  if (!source) {
    return "";
  }

  const rendered = markdownRenderer.render(source);
  return DOMPurify.sanitize(rendered, sanitizerConfig);
}
