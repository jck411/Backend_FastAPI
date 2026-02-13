import { useCallback, useEffect, useRef } from 'react';
import NoSleep from 'nosleep.js';

export default function useKeepAwake() {
  const wakeLockRef = useRef(null);
  const noSleepRef = useRef(null);
  const noSleepEnabledRef = useRef(false);

  const getNoSleep = useCallback(() => {
    if (!noSleepRef.current) {
      noSleepRef.current = new NoSleep();
    }
    return noSleepRef.current;
  }, []);

  const releaseKeepAwake = useCallback(async () => {
    if (wakeLockRef.current) {
      try {
        await wakeLockRef.current.release();
      } catch (err) {
        console.warn('Failed to release wake lock:', err);
      } finally {
        wakeLockRef.current = null;
      }
    }

    if (noSleepEnabledRef.current) {
      try {
        getNoSleep().disable();
      } catch (err) {
        console.warn('Failed to disable iOS keep-awake fallback:', err);
      } finally {
        noSleepEnabledRef.current = false;
      }
    }
  }, [getNoSleep]);

  const enableNoSleepFallback = useCallback(async () => {
    if (noSleepEnabledRef.current) return true;
    try {
      await getNoSleep().enable();
      noSleepEnabledRef.current = true;
      return true;
    } catch (err) {
      console.warn('Failed to enable iOS keep-awake fallback:', err);
      return false;
    }
  }, [getNoSleep]);

  const requestNativeWakeLock = useCallback(async () => {
    if (typeof navigator === 'undefined' || !navigator.wakeLock?.request) {
      return false;
    }

    try {
      const lock = await navigator.wakeLock.request('screen');
      wakeLockRef.current = lock;
      lock.addEventListener('release', () => {
        if (wakeLockRef.current === lock) {
          wakeLockRef.current = null;
        }
      });
      return true;
    } catch (err) {
      console.warn('Screen wake lock request failed:', err);
      return false;
    }
  }, []);

  const ensureKeepAwake = useCallback(async () => {
    if (typeof document === 'undefined' || document.visibilityState !== 'visible') {
      return false;
    }

    if (wakeLockRef.current || noSleepEnabledRef.current) {
      return true;
    }

    const nativeWakeLock = await requestNativeWakeLock();
    if (nativeWakeLock) return true;
    return enableNoSleepFallback();
  }, [enableNoSleepFallback, requestNativeWakeLock]);

  useEffect(() => {
    void ensureKeepAwake();

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        void ensureKeepAwake();
      } else {
        void releaseKeepAwake();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      void releaseKeepAwake();
    };
  }, [ensureKeepAwake, releaseKeepAwake]);

  return { ensureKeepAwake };
}
