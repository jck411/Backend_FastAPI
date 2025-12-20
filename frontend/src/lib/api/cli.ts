import { API_BASE_URL } from './config';
import type { ClientSettings, LlmSettings, LlmSettingsUpdate } from './types';

export const CLI_CLIENT_ID = 'cli';

export interface ClientPreset {
    name: string;
    llm: LlmSettings;
    [key: string]: unknown;
}

export interface ClientPresets {
    presets: ClientPreset[];
    active_index: number | null;
}


/**
 * Get current CLI LLM settings
 */
export async function getCliLlmSettings(): Promise<LlmSettings> {
    const response = await fetch(`${API_BASE_URL}/api/clients/cli/llm`);
    if (!response.ok) {
        throw new Error(`Failed to fetch CLI LLM settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update CLI LLM settings
 */
export async function updateCliLlmSettings(
    update: LlmSettingsUpdate
): Promise<LlmSettings> {
    const response = await fetch(`${API_BASE_URL}/api/clients/cli/llm`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(update),
    });

    if (!response.ok) {
        throw new Error(`Failed to update CLI LLM settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Reset CLI settings to defaults (optional, but good to have)
 */
export async function resetCliSettings(): Promise<ClientSettings> {
    const response = await fetch(`${API_BASE_URL}/api/clients/cli/reset`, {
        method: 'POST',
    });

    if (!response.ok) {
        throw new Error(`Failed to reset CLI settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Get all CLI presets
 */
export async function getCliPresets(): Promise<ClientPresets> {
    const response = await fetch(`${API_BASE_URL}/api/clients/cli/presets`);
    if (!response.ok) {
        throw new Error(`Failed to fetch CLI presets: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Create a new CLI preset
 */
export async function createCliPreset(preset: ClientPreset): Promise<ClientPresets> {
    const response = await fetch(`${API_BASE_URL}/api/clients/cli/presets`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(preset),
    });

    if (!response.ok) {
        throw new Error(`Failed to create CLI preset: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Delete a CLI preset
 */
export async function deleteCliPreset(name: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/clients/cli/presets/by-name/${name}`, {
        method: 'DELETE',
    });

    if (!response.ok) {
        throw new Error(`Failed to delete CLI preset: ${response.statusText}`);
    }
}

/**
 * Apply a CLI preset by name
 * Returns the applied settings
 */
export async function applyCliPresetByName(name: string): Promise<ClientSettings> {

    const response = await fetch(`${API_BASE_URL}/api/clients/cli/presets/by-name/${name}/apply`, {
        method: 'POST',
    });

    if (!response.ok) {
        throw new Error(`Failed to apply CLI preset: ${response.statusText}`);
    }
    return response.json();
}
