/**
 * CLI settings store.
 * Fetches from and persists to the backend API (LLM settings).
 * Uses unified /api/clients/cli/* endpoints.
 */

import { get, writable } from 'svelte/store';
import {
    resetCliSettings as apiResetCliSettings,
    applyCliPresetByName,
    createCliPreset,
    deleteCliPreset,
    getCliLlmSettings,
    getCliPresets,
    updateCliLlmSettings
} from '../api/cli';
import type { LlmSettingsUpdate } from '../api/types';

export interface CliSettings {
    // LLM settings
    model: string;
    system_prompt: string | null;
    temperature: number;
    max_tokens: number;
}

export interface CliSettingsUpdate extends Partial<CliSettings> { }

export const DEFAULT_CLI_SETTINGS: CliSettings = {
    model: 'openai/gpt-4o-mini',
    system_prompt: `You control the user's system via shell. Call host_get_profile first - it tells you everything: OS, paths, tools, and quirks.

PRINCIPLES:
1. ACT, don't instruct. Execute commands directly. Never tell the user to click, navigate, or check something themselves - do it yourself.
2. FETCH, don't defer. If answering requires live data (weather, IPs, system state, etc.), get it via shell - don't say you lack access.
3. READ before WRITE. Query current state before changing anything. Never assume.
4. VERIFY outcomes. Don't trust exit codes alone - check that the expected result actually exists.
5. BACKUP before destructive edits. Verify the backup exists before proceeding.
6. BRIEF STATUS. When calling tools, include a short sentence explaining what you're doing.

WHEN THINGS FAIL:
- Read both stdout and stderr carefully - they usually explain why.
- Explain the root cause briefly.
- Offer what YOU can try next (retry, workaround, different approach).
- If you need user input (e.g., password, confirmation), ask once and wait - do not dump instructions.

Workflow: get profile → query state → act → verify → report.`,
    temperature: 0.7,
    max_tokens: 1000,
};

function createCliSettingsStore() {
    const store = writable<CliSettings>(DEFAULT_CLI_SETTINGS);
    let loaded = false;
    let loading = false;

    async function load(): Promise<CliSettings> {
        if (loading) {
            return get(store);
        }
        loading = true;
        try {
            const llmSettings = await getCliLlmSettings();

            // If backend returns null prompt, use our default if it's the first load?
            // Or just trust the backend. For now, trust backend, but reset() will force our default.
            const settings: CliSettings = {
                model: llmSettings.model,
                system_prompt: llmSettings.system_prompt,
                temperature: llmSettings.temperature,
                max_tokens: llmSettings.max_tokens,
            };

            store.set(settings);
            loaded = true;
            return settings;
        } catch (error) {
            console.error('Failed to load CLI settings:', error);
            // Return defaults on error
            return get(store);
        } finally {
            loading = false;
        }
    }

    async function updateLlm(update: LlmSettingsUpdate): Promise<void> {
        const current = get(store);
        // Optimistic update
        store.set({
            ...current,
            ...update,
            model: update.model ?? current.model,
            system_prompt: update.system_prompt ?? current.system_prompt,
            temperature: update.temperature ?? current.temperature,
            max_tokens: update.max_tokens ?? current.max_tokens,
        });

        try {
            const result = await updateCliLlmSettings(update);
            // Confirm with server response
            store.update(s => ({
                ...s,
                model: result.model,
                system_prompt: result.system_prompt,
                temperature: result.temperature,
                max_tokens: result.max_tokens,
            }));
        } catch (error) {
            console.error('Failed to update CLI LLM settings:', error);
            // Revert on error
            store.set(current);
            throw error;
        }
    }

    async function reset(): Promise<void> {
        try {
            // fast-path: try to apply "default" preset
            try {
                await applyCliPresetByName('default');
                await load();
                return;
            } catch (e) {
                // If no default preset, fall back to hard reset
                console.log('No user default found, performing hard reset');
            }

            await apiResetCliSettings();
            await load(); // Reload to get defaults from server
            // Apply our frontend-specific defaults since backend defaults are generic
            await updateLlm(DEFAULT_CLI_SETTINGS);
        } catch (error) {
            console.error('Failed to reset CLI settings:', error);
            throw error;
        }
    }

    async function saveAsDefault(): Promise<void> {
        const current = get(store);
        try {
            // Check if 'default' preset exists and delete it
            const presets = await getCliPresets();
            if (presets.presets.some(p => p.name === 'default')) {
                await deleteCliPreset('default');
            }

            // Create new 'default' preset with current settings
            await createCliPreset({
                name: 'default',
                llm: {
                    model: current.model,
                    system_prompt: current.system_prompt,
                    temperature: current.temperature,
                    max_tokens: current.max_tokens,
                }
            });

            // Optionally verify validation of creation?
        } catch (error) {
            console.error('Failed to save as default:', error);
            throw error;
        }
    }


    return {
        subscribe: store.subscribe,
        load,
        updateLlm,
        reset,
        saveAsDefault,
    };
}

export const cliSettings = createCliSettingsStore();
