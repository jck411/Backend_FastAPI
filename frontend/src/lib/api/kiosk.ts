/**
 * Kiosk API client for STT and TTS settings.
 */

import { API_BASE_URL } from './config';

// ============== STT Settings ==============

export interface KioskSttSettings {
    eot_threshold: number;
    eot_timeout_ms: number;
    eager_eot_threshold: number | null;
    keyterms: string[];
}

export interface KioskSttSettingsUpdate {
    eot_threshold?: number;
    eot_timeout_ms?: number;
    eager_eot_threshold?: number | null;
    keyterms?: string[];
}

/**
 * Fetch current kiosk STT settings from the backend.
 */
export async function fetchKioskSttSettings(): Promise<KioskSttSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/stt-settings`);
    if (!response.ok) {
        throw new Error(`Failed to fetch kiosk STT settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update kiosk STT settings on the backend.
 */
export async function updateKioskSttSettings(
    update: KioskSttSettingsUpdate
): Promise<KioskSttSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/stt-settings`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(update),
    });
    if (!response.ok) {
        throw new Error(`Failed to update kiosk STT settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Reset kiosk STT settings to defaults on the backend.
 */
export async function resetKioskSttSettings(): Promise<KioskSttSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/stt-settings/reset`, {
        method: 'POST',
    });
    if (!response.ok) {
        throw new Error(`Failed to reset kiosk STT settings: ${response.statusText}`);
    }
    return response.json();
}

// ============== TTS Settings ==============

export interface KioskTtsSettings {
    enabled: boolean;
    provider: string;
    model: string;
    sample_rate: number;
}

export interface KioskTtsSettingsUpdate {
    enabled?: boolean;
    provider?: string;
    model?: string;
    sample_rate?: number;
}

/**
 * Fetch current kiosk TTS settings from the backend.
 */
export async function fetchKioskTtsSettings(): Promise<KioskTtsSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/tts-settings`);
    if (!response.ok) {
        throw new Error(`Failed to fetch kiosk TTS settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update kiosk TTS settings on the backend.
 */
export async function updateKioskTtsSettings(
    update: KioskTtsSettingsUpdate
): Promise<KioskTtsSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/tts-settings`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(update),
    });
    if (!response.ok) {
        throw new Error(`Failed to update kiosk TTS settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Reset kiosk TTS settings to defaults on the backend.
 */
export async function resetKioskTtsSettings(): Promise<KioskTtsSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/tts-settings/reset`, {
        method: 'POST',
    });
    if (!response.ok) {
        throw new Error(`Failed to reset kiosk TTS settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Voice object returned by the TTS voices endpoint.
 */
export interface TtsVoice {
    id: string;
    name: string;
}

/**
 * Fetch available TTS voice models for the specified provider.
 */
export async function fetchTtsVoices(provider: string = 'deepgram'): Promise<TtsVoice[]> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/tts-voices?provider=${encodeURIComponent(provider)}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch TTS voices: ${response.statusText}`);
    }
    return response.json();
}

// ============== UI Settings ==============

export interface KioskUiSettings {
    idle_return_delay_ms: number;
}

export interface KioskUiSettingsUpdate {
    idle_return_delay_ms?: number;
}

/**
 * Fetch current kiosk UI settings from the backend.
 */
export async function fetchKioskUiSettings(): Promise<KioskUiSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/ui/settings`);
    if (!response.ok) {
        throw new Error(`Failed to fetch kiosk UI settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update kiosk UI settings on the backend.
 */
export async function updateKioskUiSettings(
    update: KioskUiSettingsUpdate
): Promise<KioskUiSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/ui/settings`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(update),
    });
    if (!response.ok) {
        throw new Error(`Failed to update kiosk UI settings: ${response.statusText}`);
    }
    return response.json();
}

// ============== MCP Settings ==============

export interface KioskMcpServerInfo {
    id: string;
    enabled: boolean;
    tool_count: number;
    kiosk_enabled: boolean;
}

/**
 * Fetch all available MCP servers with their kiosk enabled status.
 */
export async function fetchKioskMcpServers(): Promise<KioskMcpServerInfo[]> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/mcp-servers`);
    if (!response.ok) {
        throw new Error(`Failed to fetch kiosk MCP servers: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update kiosk_enabled for a specific MCP server.
 * Uses the main MCP API endpoint.
 */
export async function updateServerKioskEnabled(
    serverId: string,
    kioskEnabled: boolean
): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/api/mcp/servers/${serverId}`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ kiosk_enabled: kioskEnabled }),
    });
    if (!response.ok) {
        throw new Error(`Failed to update kiosk_enabled for ${serverId}: ${response.statusText}`);
    }
}

// ============== LLM Settings ==============

export interface KioskLlmSettings {
    model: string;
    system_prompt: string | null;
    temperature: number;
    max_tokens: number;
    conversation_mode: boolean;
    conversation_timeout_seconds: number;
}

export interface KioskLlmSettingsUpdate {
    model?: string;
    system_prompt?: string | null;
    temperature?: number;
    max_tokens?: number;
    conversation_mode?: boolean;
    conversation_timeout_seconds?: number;
}

/**
 * Fetch current kiosk LLM settings from the backend.
 */
export async function fetchKioskLlmSettings(): Promise<KioskLlmSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/llm-settings`);
    if (!response.ok) {
        throw new Error(`Failed to fetch kiosk LLM settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update kiosk LLM settings on the backend.
 */
export async function updateKioskLlmSettings(
    update: KioskLlmSettingsUpdate
): Promise<KioskLlmSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/llm-settings`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(update),
    });
    if (!response.ok) {
        throw new Error(`Failed to update kiosk LLM settings: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Reset kiosk LLM settings to defaults on the backend.
 */
export async function resetKioskLlmSettings(): Promise<KioskLlmSettings> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/llm-settings/reset`, {
        method: 'POST',
    });
    if (!response.ok) {
        throw new Error(`Failed to reset kiosk LLM settings: ${response.statusText}`);
    }
    return response.json();
}

// ============== Presets ==============

export interface KioskPreset {
    name: string;
    // LLM settings
    model: string;
    system_prompt: string;
    temperature: number;
    max_tokens: number;
    // STT settings
    eot_threshold: number;
    eot_timeout_ms: number;
    keyterms: string[];
    // TTS settings
    tts_enabled: boolean;
    tts_model: string;
    tts_sample_rate: number;
}

export interface KioskPresets {
    presets: KioskPreset[];
    active_index: number;
}

/**
 * Fetch all kiosk presets from the backend.
 */
export async function fetchKioskPresets(): Promise<KioskPresets> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/presets`);
    if (!response.ok) {
        throw new Error(`Failed to fetch kiosk presets: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Activate a preset by index. This also applies its settings.
 */
export async function activateKioskPreset(index: number): Promise<KioskPresets> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/presets/activate`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ index }),
    });
    if (!response.ok) {
        throw new Error(`Failed to activate kiosk preset: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Update a single preset by index.
 */
export async function updateKioskPreset(
    index: number,
    preset: KioskPreset
): Promise<KioskPresets> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/presets`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ index, preset }),
    });
    if (!response.ok) {
        throw new Error(`Failed to update kiosk preset: ${response.statusText}`);
    }
    return response.json();
}

/**
 * Reset all presets to defaults.
 */
export async function resetKioskPresets(): Promise<KioskPresets> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/presets/reset`, {
        method: 'POST',
    });
    if (!response.ok) {
        throw new Error(`Failed to reset kiosk presets: ${response.statusText}`);
    }
    return response.json();
}

