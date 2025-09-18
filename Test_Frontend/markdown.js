import { marked } from 'https://cdn.jsdelivr.net/npm/marked@12.0.1/lib/marked.esm.js';
import createDOMPurify from 'https://cdn.jsdelivr.net/npm/dompurify@3.0.11/dist/purify.es.mjs';

const DOMPurify = createDOMPurify(window);

marked.setOptions({
  gfm: true,
  breaks: true,
  mangle: false,
  headerIds: false,
});

/**
 * Convert Markdown text into sanitized HTML.
 * @param {string} markdown
 * @returns {string}
 */
export function renderMarkdown(markdown) {
  if (typeof markdown !== 'string' || !markdown.trim()) {
    return DOMPurify.sanitize('');
  }
  const html = marked.parse(markdown);
  return DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
}
