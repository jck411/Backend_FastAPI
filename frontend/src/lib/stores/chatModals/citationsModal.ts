import { writable } from "svelte/store";
import type { MessageCitation } from "../chat";

export type CitationsModalState = {
    open: boolean;
    messageId: string | null;
    citations: MessageCitation[];
};

const initialState: CitationsModalState = {
    open: false,
    messageId: null,
    citations: [],
};

export function createCitationsModalStore() {
    const { subscribe, set, update } = writable<CitationsModalState>(initialState);

    function openWithCitations(messageId: string, citations: MessageCitation[]): void {
        set({
            open: true,
            messageId,
            citations,
        });
    }

    function close(): void {
        set(initialState);
    }

    return {
        subscribe,
        openWithCitations,
        close,
    };
}

export const citationsModal = createCitationsModalStore();
