/**
 * Kiosk API client for STT settings.
 */

import { API_BASE_URL } from './config';

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
