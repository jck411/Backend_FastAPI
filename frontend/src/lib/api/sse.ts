import type { SseEvent } from './types';

const LINE_SEPARATOR = /\r?\n/;

export function parseSsePayload(payload: string): SseEvent[] {
  const events: SseEvent[] = [];
  const rawEvents = payload.split(/\n\n|\r\r|\r\n\r\n/);

  for (const raw of rawEvents) {
    const trimmed = raw.trim();
    if (!trimmed) continue;

    const lines = trimmed.split(LINE_SEPARATOR);
    let eventName = 'message';
    let dataLines: string[] = [];
    let eventId: string | undefined;

    for (const line of lines) {
      if (!line) continue;
      if (line.startsWith(':')) {
        // Comment line; ignore.
        continue;
      }
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim() || 'message';
        continue;
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
        continue;
      }
      if (line.startsWith('id:')) {
        eventId = line.slice(3).trim();
        continue;
      }
    }

    events.push({
      event: eventName,
      data: dataLines.length ? dataLines.join('\n') : undefined,
      id: eventId,
    });
  }

  return events;
}
