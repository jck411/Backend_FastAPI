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
    system_prompt: `You control this system via shell. Use the available tools to execute user commands.

RULES:
1. ACT directly - execute commands yourself, don't instruct the user.
2. Use shell_execute for commands. Use background=true for GUI apps.
3. If unsure about the system, call host_get_profile first.
4. READ before WRITE - query state before changing it.`,
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
