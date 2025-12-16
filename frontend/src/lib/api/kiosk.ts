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
 * Fetch available TTS voice models.
 */
export async function fetchTtsVoices(): Promise<string[]> {
    const response = await fetch(`${API_BASE_URL}/api/kiosk/tts-voices`);
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
