import { forwardRef, useCallback, useEffect, useMemo, useRef } from 'react';

const DEFAULT_FADE_ZONE_PX = 140;
const DEFAULT_SLIDE_DIST_PX = 10;
const DEFAULT_FADE_MS = 600;
const DEFAULT_SLIDE_MS = 600;
const MAX_CHUNK_CHARS = 120;

const chunkText = (text, maxChars) => {
  const chunks = [];
  let remaining = text.trim();
  if (!remaining) return chunks;

  const minSplit = Math.floor(maxChars * 0.6);

  while (remaining.length > maxChars) {
    let splitAt = remaining.lastIndexOf(' ', maxChars);
    if (splitAt < minSplit) {
      splitAt = maxChars;
    }
    const chunk = remaining.slice(0, splitAt).trim();
    if (chunk) chunks.push(chunk);
    remaining = remaining.slice(splitAt).trim();
  }

  if (remaining) chunks.push(remaining);
  return chunks;
};

const splitText = (text, maxChars) => {
  if (!text) return [];
  const normalized = text.replace(/\r\n/g, '\n').trim();
  if (!normalized) return [];

  const paragraphs = normalized.split(/\n+/);
  const segments = [];

  paragraphs.forEach((paragraph, index) => {
    chunkText(paragraph, maxChars).forEach(chunk => segments.push(chunk));
    if (index < paragraphs.length - 1) {
      segments.push('');
    }
  });

  return segments;
};

const ScrollFadeText = forwardRef(({
  visible = false,
  onScroll,
  items = [],
  fadeZonePx = DEFAULT_FADE_ZONE_PX,
  slideDistPx = DEFAULT_SLIDE_DIST_PX,
  fadeMs = DEFAULT_FADE_MS,
  slideMs = DEFAULT_SLIDE_MS,
  className = '',
}, forwardedRef) => {
  const localRef = useRef(null);

  const setRefs = useCallback((node) => {
    localRef.current = node;
    if (!forwardedRef) return;
    if (typeof forwardedRef === 'function') {
      forwardedRef(node);
    } else {
      forwardedRef.current = node;
    }
  }, [forwardedRef]);

  const segments = useMemo(() => {
    const nextSegments = [];
    items.forEach((item, itemIndex) => {
      const pieces = splitText(item.text, item.maxChars || MAX_CHUNK_CHARS);
      pieces.forEach((piece, pieceIndex) => {
        if (!piece) {
          nextSegments.push({
            key: `${item.id || itemIndex}-gap-${pieceIndex}`,
            isGap: true,
            gapType: 'paragraph',
          });
          return;
        }
        nextSegments.push({
          key: `${item.id || itemIndex}-${pieceIndex}`,
          text: piece,
          className: item.className,
        });
      });
      if (itemIndex < items.length - 1 && pieces.length) {
        nextSegments.push({
          key: `${item.id || itemIndex}-gap-group`,
          isGap: true,
          gapType: 'group',
        });
      }
    });
    return nextSegments;
  }, [items]);

  useEffect(() => {
    const container = localRef.current;
    if (!container) return;
    container.style.setProperty('--slide-dist', `${slideDistPx}px`);
    container.style.setProperty('--fade-dur', `${fadeMs}ms`);
    container.style.setProperty('--slide-dur', `${slideMs}ms`);
  }, [fadeMs, slideDistPx, slideMs]);

  useEffect(() => {
    const container = localRef.current;
    if (!container || !visible) return;

    const nodes = container.querySelectorAll('.fade-in-section');
    if (!nodes.length) return;

    const canScroll = container.scrollHeight - container.clientHeight > 8;
    if (!canScroll) {
      nodes.forEach(node => node.classList.add('is-visible'));
      return;
    }

    if (typeof IntersectionObserver === 'undefined') {
      nodes.forEach(node => node.classList.add('is-visible'));
      return;
    }

    const maxMargin = Math.max(0, Math.floor((container.clientHeight - 2) / 2));
    const marginPx = Math.min(fadeZonePx, maxMargin);
    container.style.setProperty('--fade-zone', `${marginPx}px`);

    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        entry.target.classList.toggle('is-visible', entry.isIntersecting);
      });
    }, {
      root: container,
      threshold: 0,
      rootMargin: `-${marginPx}px 0px`,
    });

    nodes.forEach(node => observer.observe(node));

    return () => observer.disconnect();
  }, [fadeZonePx, segments.length, visible]);

  return (
    <div
      ref={setRefs}
      onScroll={onScroll}
      className={`floating-text ${visible ? 'visible' : ''} ${className}`.trim()}
    >
      <div className="fade-spacer" aria-hidden="true" />
      {segments.map(segment => {
        if (segment.isGap) {
          const gapClass = segment.gapType === 'group' ? 'text-gap text-gap-group' : 'text-gap';
          return <div key={segment.key} className={gapClass} aria-hidden="true" />;
        }
        return (
          <p key={segment.key} className={`text-chunk fade-in-section ${segment.className}`}>
            {segment.text}
          </p>
        );
      })}
      <div className="fade-spacer" aria-hidden="true" />
    </div>
  );
});

ScrollFadeText.displayName = 'ScrollFadeText';

export default ScrollFadeText;
