export const normalizeMarkdownText = (text) => {
  if (!text) return '';
  return String(text).replace(/\r\n/g, '\n');
};

export const parseHeading = (line) => {
  const match = line.match(/^(#{1,6})\s+(.*)$/);
  if (!match) {
    return { text: line, level: 0 };
  }
  const level = Math.min(3, match[1].length);
  return { text: match[2].trim(), level };
};

export const parseInlineRuns = (text) => {
  const runs = [];
  let buffer = '';
  let bold = false;
  let italic = false;

  const pushBuffer = () => {
    if (!buffer) return;
    runs.push({ text: buffer, bold, italic });
    buffer = '';
  };

  let i = 0;
  while (i < text.length) {
    if (text[i] === '*' && text[i + 1] === '*') {
      const hasClosing = bold || text.indexOf('**', i + 2) !== -1;
      if (hasClosing) {
        pushBuffer();
        bold = !bold;
        i += 2;
        continue;
      }
      buffer += '**';
      i += 2;
      continue;
    }

    if (text[i] === '*') {
      const hasClosing = italic || text.indexOf('*', i + 1) !== -1;
      if (hasClosing) {
        pushBuffer();
        italic = !italic;
        i += 1;
        continue;
      }
      buffer += '*';
      i += 1;
      continue;
    }

    buffer += text[i];
    i += 1;
  }

  pushBuffer();
  return runs;
};
