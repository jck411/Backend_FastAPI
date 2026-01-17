/**
 * ConfigContext - Provides app-wide configuration from the backend.
 *
 * The display timezone is sourced from the backend's UiSettings API,
 * which defaults to EASTERN_TIMEZONE_NAME from time_context.py.
 * This ensures consistency with the backend's timezone handling (DRY principle).
 */

import { createContext, useContext, useEffect, useState } from 'react';

/**
 * Fallback timezone if the API is unavailable.
 * Matches backend's EASTERN_TIMEZONE_NAME from time_context.py.
 */
const DEFAULT_DISPLAY_TIMEZONE = 'America/New_York';

/** API base URL - auto-detect protocol based on page */
const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:8000`;

const ConfigContext = createContext({
    displayTimezone: DEFAULT_DISPLAY_TIMEZONE,
    idleReturnDelayMs: 10000,
    isLoaded: false,
});

/**
 * ConfigProvider - Fetches and provides app configuration from the backend.
 */
export function ConfigProvider({ children }) {
    const [config, setConfig] = useState({
        displayTimezone: DEFAULT_DISPLAY_TIMEZONE,
        idleReturnDelayMs: 10000,
        isLoaded: false,
    });

    useEffect(() => {
        const fetchConfig = async () => {
            try {
                const response = await fetch(`${API_BASE_URL}/api/clients/kiosk/ui`);
                if (response.ok) {
                    const settings = await response.json();
                    setConfig({
                        displayTimezone: settings.display_timezone || DEFAULT_DISPLAY_TIMEZONE,
                        idleReturnDelayMs: settings.idle_return_delay_ms || 10000,
                        isLoaded: true,
                    });
                    console.log(`Config loaded: timezone=${settings.display_timezone}`);
                } else {
                    setConfig(prev => ({ ...prev, isLoaded: true }));
                }
            } catch (err) {
                console.warn('Failed to load config, using defaults:', err);
                setConfig(prev => ({ ...prev, isLoaded: true }));
            }
        };

        fetchConfig();
    }, []);

    return (
        <ConfigContext.Provider value={config}>
            {children}
        </ConfigContext.Provider>
    );
}

/**
 * useConfig - Hook to access the app configuration.
 */
export function useConfig() {
    return useContext(ConfigContext);
}

/**
 * useDisplayTimezone - Hook to get just the display timezone.
 */
export function useDisplayTimezone() {
    const { displayTimezone } = useContext(ConfigContext);
    return displayTimezone;
}

export default ConfigContext;
