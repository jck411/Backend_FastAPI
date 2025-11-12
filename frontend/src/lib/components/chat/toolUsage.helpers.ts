import type { ConversationMessage, ConversationRole } from "../../stores/chat";
import type { ToolUsageEntry } from "./toolUsage.types";

export interface ToolUsageTokenSummary {
  inputTokens: number | null;
  outputTokens: number | null;
  totalTokens: number | null;
}

export interface AssistantToolUsageSummary {
  used: boolean;
  count: number;
  tokens: ToolUsageTokenSummary | null;
}

export interface MessagePresentation {
  visibleMessages: ConversationMessage[];
  assistantToolUsage: Record<string, AssistantToolUsageSummary>;
  messageIndexMap: Record<string, number>;
}

const DEFAULT_TOOL_ROLE: ConversationRole = "tool";

const INPUT_TOKEN_KEYS = [
  "prompt_tokens",
  "input_tokens",
  "prompt",
  "input",
  "promptTokens",
  "inputTokens",
];
const OUTPUT_TOKEN_KEYS = [
  "completion_tokens",
  "output_tokens",
  "completion",
  "output",
  "completionTokens",
  "outputTokens",
];
const TOTAL_TOKEN_KEYS = ["total_tokens", "total", "totalTokens"];

export function computeMessagePresentation(
  messages: ConversationMessage[],
  toolRole: ConversationRole = DEFAULT_TOOL_ROLE,
): MessagePresentation {
  const visibleMessages: ConversationMessage[] = [];
  const assistantToolUsage: Record<string, AssistantToolUsageSummary> = {};
  const messageIndexMap: Record<string, number> = {};

  for (let index = 0; index < messages.length; index += 1) {
    const message = messages[index];
    messageIndexMap[message.id] = index;

    if (message.role === "assistant") {
      const toolCalls = message.details?.toolCalls;
      const hasMetadataToolCalls = Array.isArray(toolCalls) && toolCalls.length > 0;
      let toolMessageCount = 0;

      let lookahead = index + 1;
      while (isToolMessage(messages[lookahead], toolRole)) {
        toolMessageCount += 1;
        lookahead += 1;
      }

      const metadataCount = hasMetadataToolCalls ? toolCalls.length : 0;
      const count = Math.max(metadataCount, toolMessageCount);
      const usedTool = count > 0;
      const tokens = extractUsageSummary(message.details?.usage);

      assistantToolUsage[message.id] = {
        used: usedTool,
        count,
        tokens,
      };
    }

    if (message.role !== toolRole) {
      visibleMessages.push(message);
    }
  }

  return {
    visibleMessages,
    assistantToolUsage,
    messageIndexMap,
  };
}

export function deriveToolUsageEntries(
  messages: ConversationMessage[],
  messageIndexMap: Record<string, number>,
  messageId: string,
  toolRole: ConversationRole = DEFAULT_TOOL_ROLE,
): ToolUsageEntry[] {
  const index = messageIndexMap[messageId];
  if (typeof index !== "number") {
    return [];
  }

  const assistantMessage = messages[index];
  if (!assistantMessage || assistantMessage.role !== "assistant") {
    return [];
  }

  const entries: ToolUsageEntry[] = [];
  const metadataCalls = Array.isArray(assistantMessage.details?.toolCalls)
    ? (assistantMessage.details?.toolCalls as Array<Record<string, unknown>>)
    : [];

  let lookaheadIndex = index + 1;
  while (isToolMessage(messages[lookaheadIndex], toolRole)) {
    const toolMessage = messages[lookaheadIndex];
    const details = toolMessage.details ?? {};
    const metadataCall = metadataCalls[entries.length];
    const nameFromDetails = typeof details?.toolName === "string" ? details.toolName : null;
    const name = nameFromDetails ?? extractCallName(metadataCall) ?? "Tool";
    const status = typeof details?.toolStatus === "string" ? details.toolStatus : null;
    const resultFromDetails =
      typeof details?.toolResult === "string" ? details.toolResult : null;
    const contentResult = typeof toolMessage.content === "string" ? toolMessage.content : null;
    const result = resultFromDetails ?? contentResult ?? extractCallResult(metadataCall);
    const input = extractCallArguments(metadataCall);

    entries.push({
      id: toolMessage.id,
      name,
      status,
      input,
      result,
    });

    lookaheadIndex += 1;
  }

  if (entries.length === 0 && metadataCalls.length > 0) {
    metadataCalls.forEach((call, callIndex) => {
      entries.push({
        id: `${assistantMessage.id}-metadata-${callIndex}`,
        name: extractCallName(call) ?? `Tool ${callIndex + 1}`,
        status: null,
        input: extractCallArguments(call),
        result: extractCallResult(call),
      });
    });
  } else if (entries.length > 0 && metadataCalls.length > 0) {
    entries.forEach((entry, entryIndex) => {
      const metadataCall = metadataCalls[entryIndex];
      if (!metadataCall) {
        return;
      }
      if (!entry.name || entry.name === "Tool") {
        entry.name = extractCallName(metadataCall) ?? entry.name;
      }
      if (!entry.input) {
        entry.input = extractCallArguments(metadataCall);
      }
      if (!entry.result) {
        entry.result = extractCallResult(metadataCall);
      }
    });
  }

  return entries;
}

function isToolMessage(
  value: ConversationMessage | undefined,
  toolRole: ConversationRole,
): value is ConversationMessage {
  return value?.role === toolRole;
}

function extractCallName(call: Record<string, unknown> | null | undefined): string | null {
  if (!call) {
    return null;
  }

  const name = call["name"];
  if (typeof name === "string" && name.trim().length > 0) {
    return name;
  }

  const fn = call["function"];
  if (fn && typeof fn === "object") {
    const functionName = (fn as Record<string, unknown>).name;
    if (typeof functionName === "string" && functionName.trim().length > 0) {
      return functionName;
    }
  }

  return null;
}

function extractCallResult(call: Record<string, unknown> | null | undefined): string | null {
  if (!call) {
    return null;
  }

  const resultValue = call["result"];
  if (typeof resultValue === "string") {
    return resultValue;
  }

  if (resultValue && typeof resultValue === "object") {
    try {
      return JSON.stringify(resultValue, null, 2);
    } catch (error) {
      console.warn("Failed to stringify tool result", error);
    }
  }

  const fn = call["function"];
  if (fn && typeof fn === "object") {
    const args = (fn as Record<string, unknown>)["arguments"];
    if (typeof args === "string") {
      return args;
    }
    if (args && typeof args === "object") {
      try {
        return JSON.stringify(args, null, 2);
      } catch (error) {
        console.warn("Failed to stringify tool arguments", error);
      }
    }
  }

  return null;
}

function extractCallArguments(call: Record<string, unknown> | null | undefined): string | null {
  if (!call) {
    return null;
  }

  const directArgs = call["arguments"];
  const normalizedArgs = normalizeArgumentValue(directArgs);
  if (normalizedArgs) {
    return normalizedArgs;
  }

  const fn = call["function"];
  if (fn && typeof fn === "object") {
    const functionArgs = normalizeArgumentValue((fn as Record<string, unknown>)["arguments"]);
    if (functionArgs) {
      return functionArgs;
    }
  }

  return null;
}

function extractUsageSummary(
  usage: Record<string, unknown> | null | undefined,
): ToolUsageTokenSummary | null {
  if (!usage || typeof usage !== "object") {
    return null;
  }

  const record = usage as Record<string, unknown>;
  const inputTokens = findNumericValue(record, INPUT_TOKEN_KEYS);
  const outputTokens = findNumericValue(record, OUTPUT_TOKEN_KEYS);
  let totalTokens = findNumericValue(record, TOTAL_TOKEN_KEYS);

  if (totalTokens == null) {
    if (inputTokens != null || outputTokens != null) {
      totalTokens = (inputTokens ?? 0) + (outputTokens ?? 0);
    }
  }

  if (inputTokens == null && outputTokens == null && totalTokens == null) {
    return null;
  }

  return {
    inputTokens,
    outputTokens,
    totalTokens,
  };
}

function findNumericValue(
  record: Record<string, unknown>,
  keys: string[],
): number | null {
  for (const key of keys) {
    if (!(key in record)) {
      continue;
    }
    const value = toNumeric(record[key]);
    if (value != null) {
      return value;
    }
  }
  return null;
}

function toNumeric(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function normalizeArgumentValue(value: unknown): string | null {
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    try {
      const parsed = JSON.parse(trimmed);
      if (typeof parsed === "string") {
        return parsed;
      }
      return JSON.stringify(parsed, null, 2);
    } catch (error) {
      return trimmed;
    }
  }

  if (value && typeof value === "object") {
    try {
      return JSON.stringify(value, null, 2);
    } catch (error) {
      console.warn("Failed to stringify tool arguments", error, value);
    }
  }

  return null;
}
