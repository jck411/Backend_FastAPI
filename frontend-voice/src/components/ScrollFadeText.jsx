import { forwardRef, useCallback, useEffect, useMemo, useRef } from 'react';
import { normalizeMarkdownText, parseHeading, parseInlineRuns } from '../utils/markdown';

const DEFAULT_FADE_ZONE_PX = 140;
const DEFAULT_SLIDE_DIST_PX = 10;
const DEFAULT_FADE_MS = 600;
const DEFAULT_SLIDE_MS = 600;
const MAX_CHUNK_CHARS = 120;
const MAX_OBSERVED_SEGMENTS = 220;

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
  const normalized = normalizeMarkdownText(text).trim();
  if (!normalized) return [];

  const paragraphs = normalized.split(/\n+/);
  const segments = [];

  paragraphs.forEach((paragraph, index) => {
    const trimmed = paragraph.trim();
    if (!trimmed) return;
    const { text: content, level } = parseHeading(trimmed);
    chunkText(content, maxChars).forEach(chunk => {
      segments.push({
        text: chunk,
        runs: parseInlineRuns(chunk),
        headingLevel: level,
      });
    });
    if (index < paragraphs.length - 1) {
      segments.push({ isGap: true, gapType: 'paragraph' });
    }
  });

  return segments;
};

const renderInlineRuns = (runs, keyPrefix) => {
  if (!runs || !runs.length) return null;
  return runs.map((run, index) => {
    if (!run.text) return null;
    if (!run.bold && !run.italic) return run.text;
    const key = `${keyPrefix}-md-${index}`;
    if (run.bold && run.italic) {
      return (
        <strong key={key}>
          <em>{run.text}</em>
        </strong>
      );
    }
    if (run.bold) return <strong key={key}>{run.text}</strong>;
    return <em key={key}>{run.text}</em>;
  });
};

const ScrollFadeText = forwardRef(({
  visible = false,
  onScroll,
  onInteractionStart,
  onInteractionEnd,
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
        if (piece.isGap) {
          nextSegments.push({
            key: `${item.id || itemIndex}-gap-${pieceIndex}`,
            isGap: true,
            gapType: piece.gapType || 'paragraph',
          });
          return;
        }
        nextSegments.push({
          key: `${item.id || itemIndex}-${pieceIndex}`,
          runs: piece.runs,
          headingLevel: piece.headingLevel || 0,
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

    const prefersReducedMotion = typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (prefersReducedMotion || segments.length > MAX_OBSERVED_SEGMENTS) {
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

  const handleClick = useCallback((event) => {
    event.stopPropagation();
  }, []);

  const handleInteractionStart = useCallback((event) => {
    event.stopPropagation();
    onInteractionStart?.();
  }, [onInteractionStart]);

  const handleInteractionEnd = useCallback((event) => {
    event.stopPropagation();
    onInteractionEnd?.();
  }, [onInteractionEnd]);

  return (
    <div
      ref={setRefs}
      onScroll={onScroll}
      onClick={handleClick}
      onPointerDown={handleInteractionStart}
      onPointerUp={handleInteractionEnd}
      onPointerCancel={handleInteractionEnd}
      onTouchStart={handleInteractionStart}
      onTouchEnd={handleInteractionEnd}
      onTouchCancel={handleInteractionEnd}
      onWheel={handleInteractionStart}
      className={`floating-text ${visible ? 'visible' : ''} ${className}`.trim()}
    >
      <div className="fade-spacer" aria-hidden="true" />
      {segments.map(segment => {
        if (segment.isGap) {
          const gapClass = segment.gapType === 'group' ? 'text-gap text-gap-group' : 'text-gap';
          return <div key={segment.key} className={gapClass} aria-hidden="true" />;
        }
        const headingClass = segment.headingLevel
          ? `text-heading text-heading-${segment.headingLevel}`
          : '';
        return (
          <p
            key={segment.key}
            className={`text-chunk fade-in-section ${segment.className} ${headingClass}`.trim()}
          >
            {renderInlineRuns(segment.runs, segment.key)}
          </p>
        );
      })}
      <div className="fade-spacer" aria-hidden="true" />
    </div>
  );
});

ScrollFadeText.displayName = 'ScrollFadeText';

export default ScrollFadeText;
