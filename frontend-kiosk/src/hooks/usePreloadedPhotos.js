/**
 * Sliding-window photo hook — keeps only 3 images in memory at a time.
 * Fetches the full ID list from backend, but only decodes current/next/prev photos.
 * This allows 100+ photos per day while using ~2-3 MB of RAM on the Echo.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

const API_BASE_URL = import.meta.env.DEV
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : '';

/** How many photos to keep decoded ahead/behind the current index */
const WINDOW_AHEAD = 1;
const WINDOW_BEHIND = 1;

function photoUrl(id) {
    return `${API_BASE_URL}/api/slideshow/photo/${id}`;
}

export function usePreloadedPhotos() {
    const [photos, setPhotos] = useState([]);           // full ordered ID list
    const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
    const [isLoading, setIsLoading] = useState(true);   // true until first photo ready
    const windowRef = useRef(new Map());                 // id -> { url, img }
    const [windowReady, setWindowReady] = useState(false);

    // Fetch photo ID list from backend
    const fetchPhotoList = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/slideshow/photos?daily_seed=true`);
            if (!response.ok) return [];
            const data = await response.json();
            return data.photos || [];
        } catch (err) {
            console.warn('Failed to fetch slideshow photos:', err);
            return [];
        }
    }, []);

    // Preload a single photo, returns a promise
    const preloadOne = useCallback((id) => {
        return new Promise((resolve) => {
            const img = new Image();
            const url = photoUrl(id);
            img.onload = () => resolve({ id, url, img });
            img.onerror = () => resolve(null);
            img.src = url;
        });
    }, []);

    // Ensure the sliding window around `index` is populated
    const ensureWindow = useCallback(async (index, ids) => {
        if (ids.length === 0) return;

        const needed = new Set();
        for (let offset = -WINDOW_BEHIND; offset <= WINDOW_AHEAD; offset++) {
            const i = (index + offset + ids.length) % ids.length;
            needed.add(ids[i]);
        }

        // Evict photos outside the window
        const win = windowRef.current;
        for (const id of win.keys()) {
            if (!needed.has(id)) {
                const entry = win.get(id);
                if (entry?.img) {
                    entry.img.src = '';  // release decoded bitmap
                }
                win.delete(id);
            }
        }

        // Load missing photos in parallel
        const toLoad = [...needed].filter(id => !win.has(id));
        if (toLoad.length > 0) {
            const results = await Promise.all(toLoad.map(id => preloadOne(id)));
            for (const r of results) {
                if (r) {
                    win.set(r.id, { url: r.url, img: r.img });
                }
            }
        }

        setWindowReady(win.has(ids[index]));
    }, [preloadOne]);

    // Initial load and hourly refresh of the ID list
    const refreshPhotos = useCallback(async () => {
        const ids = await fetchPhotoList();
        if (ids.length > 0) {
            const changed = JSON.stringify(ids) !== JSON.stringify(photos);
            if (changed) {
                setPhotos(ids);
                setCurrentPhotoIndex(0);
                setIsLoading(true);
                await ensureWindow(0, ids);
                setIsLoading(false);
                console.log(`Slideshow: ${ids.length} photos available (window of ${WINDOW_AHEAD + WINDOW_BEHIND + 1})`);
            }
        }
    }, [fetchPhotoList, ensureWindow, photos]);

    useEffect(() => {
        refreshPhotos();
        const interval = setInterval(refreshPhotos, 60 * 60 * 1000);
        return () => clearInterval(interval);
    }, [refreshPhotos]);

    // Keep the window in sync whenever the index changes
    useEffect(() => {
        if (photos.length > 0) {
            ensureWindow(currentPhotoIndex, photos);
        }
    }, [currentPhotoIndex, photos, ensureWindow]);

    const getCurrentPhotoData = useCallback(() => {
        if (photos.length === 0 || !windowReady) {
            return { currentUrl: null, nextUrl: null, isReady: false };
        }
        const currentId = photos[currentPhotoIndex];
        const nextId = photos[(currentPhotoIndex + 1) % photos.length];
        const win = windowRef.current;
        return {
            currentUrl: win.get(currentId)?.url || null,
            nextUrl: win.get(nextId)?.url || null,
            isReady: !!win.get(currentId),
        };
    }, [photos, windowReady, currentPhotoIndex]);

    const nextPhoto = useCallback(() => {
        if (photos.length > 1) {
            setCurrentPhotoIndex((prev) => (prev + 1) % photos.length);
        }
    }, [photos.length]);

    return {
        photos,
        isLoading,
        isReady: windowReady && !isLoading,
        loadedCount: windowRef.current.size,
        totalCount: photos.length,
        currentPhotoIndex,
        getCurrentPhotoData,
        nextPhoto,
        refreshPhotos
    };
}
