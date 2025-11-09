import { get, writable } from 'svelte/store';
import {
  fetchGoogleAuthStatus,
  startGoogleAuthorization,
} from '../api/client';
import type {
  GoogleAuthAuthorizeResponse,
  GoogleAuthStatusResponse,
} from '../api/types';

interface GoogleAuthState {
  loading: boolean;
  authorizing: boolean;
  authorized: boolean;
  userEmail: string | null;
  expiresAt: string | null;
  services: string[];
  error: string | null;
}

const DEFAULT_SERVICES = [
  'Google Calendar',
  'Google Tasks',
  'Gmail',
  'Google Drive',
];

const INITIAL_STATE: GoogleAuthState = {
  loading: false,
  authorizing: false,
  authorized: false,
  userEmail: null,
  expiresAt: null,
  services: [...DEFAULT_SERVICES],
  error: null,
};

function waitForPopup(popup: Window): Promise<void> {
  return new Promise((resolve, reject) => {
    const messageHandler = (event: MessageEvent) => {
      const payload = event.data;
      if (!payload || typeof payload !== 'object') {
        return;
      }
      if ((payload as Record<string, unknown>).source !== 'google-auth') {
        return;
      }

      cleanup();

      const status = (payload as Record<string, unknown>).status;
      const message = (payload as Record<string, unknown>).message;

      if (status === 'success') {
        resolve();
      } else {
        const error = typeof message === 'string' ? message : 'Authorization failed.';
        reject(new Error(error));
      }
    };

    const timer = window.setInterval(() => {
      if (popup.closed) {
        cleanup();
        reject(new Error('The authorization window was closed before completion.'));
      }
    }, 500);

    const cleanup = () => {
      window.removeEventListener('message', messageHandler);
      window.clearInterval(timer);
    };

    window.addEventListener('message', messageHandler);
  });
}

export function createGoogleAuthStore() {
  const store = writable<GoogleAuthState>({ ...INITIAL_STATE });

  async function load(): Promise<void> {
    store.update((state) => ({ ...state, loading: true, error: null }));
    try {
      const response: GoogleAuthStatusResponse = await fetchGoogleAuthStatus();
      store.set({
        loading: false,
        authorizing: false,
        authorized: response.authorized,
        userEmail: response.user_email ?? null,
        expiresAt: response.expires_at ?? null,
        services: response.services && response.services.length > 0
          ? response.services
          : [...DEFAULT_SERVICES],
        error: null,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Failed to check Google authorization status.';
      store.set({
        ...INITIAL_STATE,
        services: [...DEFAULT_SERVICES],
        loading: false,
        error: message,
      });
    }
  }

  function reset(): void {
    store.set({ ...INITIAL_STATE, services: [...DEFAULT_SERVICES] });
  }

  async function authorize(): Promise<boolean> {
    if (typeof window === 'undefined') {
      store.update((state) => ({
        ...state,
        error: 'Google authorization is only available in a browser environment.',
      }));
      return false;
    }

    const snapshot = get(store);
    if (snapshot.authorizing) {
      return false;
    }

    store.update((state) => ({ ...state, authorizing: true, error: null }));

    try {
      const response: GoogleAuthAuthorizeResponse = await startGoogleAuthorization({});
      const popup = window.open(
        response.auth_url,
        'google-oauth',
        'width=520,height=640,noopener=yes,noreferrer=yes',
      );

      if (!popup) {
        throw new Error('Popup was blocked. Allow pop-ups and try again.');
      }

      popup.focus();
      await waitForPopup(popup);
      await load();
      store.update((state) => ({ ...state, authorizing: false }));
      return true;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : 'Failed to start Google authorization.';
      store.update((state) => ({
        ...state,
        authorizing: false,
        error: message,
      }));
      return false;
    }
  }

  return {
    subscribe: store.subscribe,
    load,
    reset,
    authorize,
  };
}
