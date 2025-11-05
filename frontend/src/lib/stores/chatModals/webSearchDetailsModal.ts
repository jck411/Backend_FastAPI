import { writable } from "svelte/store";
import type { ConversationMessage } from "../chat";

export type WebSearchDetails = {
    engine: string | null;
    maxResults: number | null;
    contextSize: string | null;
    searchPrompt: string | null;
};

export type WebSearchDetailsModalState = {
    open: boolean;
    messageId: string | null;
    details: WebSearchDetails | null;
};

const initialState: WebSearchDetailsModalState = {
    open: false,
    messageId: null,
    details: null,
};

export function createWebSearchDetailsModalStore() {
    const { subscribe, set, update } = writable<WebSearchDetailsModalState>(initialState);

    function openWithDetails(messageId: string, details: WebSearchDetails | null): void {
        set({
            open: true,
            messageId,
            details: details ?? {
                engine: null,
                maxResults: null,
                contextSize: null,
                searchPrompt: null,
            },
        });
    }

    function openForMessage(message: ConversationMessage): void {
        const webSearchConfig = message.details?.webSearchConfig;
        if (webSearchConfig && typeof webSearchConfig === 'object') {
            const details: WebSearchDetails = {
                engine: (webSearchConfig as any).engine ?? null,
                maxResults: (webSearchConfig as any).maxResults ?? null,
                contextSize: (webSearchConfig as any).contextSize ?? null,
                searchPrompt: (webSearchConfig as any).searchPrompt ?? null,
            };
            openWithDetails(message.id, details);
        } else {
            openWithDetails(message.id, null);
        }
    }

    function close(): void {
        set(initialState);
    }

    return {
        subscribe,
        openWithDetails,
        openForMessage,
        close,
    };
}
