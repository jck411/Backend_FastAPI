/**
 * Photo Preloader Hook — fetches landscape photos from Immich via backend proxy
 */

import { useCallback, useEffect, useState } from 'react';

const API_BASE_URL = import.meta.env.DEV
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : '';

export function usePreloadedPhotos() {
    const [photos, setPhotos] = useState([]);
    const [preloadedImages, setPreloadedImages] = useState(new Map());
    const [isLoading, setIsLoading] = useState(false);
    const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);

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

    const preloadAllPhotos = useCallback(async (photoIds) => {
        if (photoIds.length === 0) return;
        setIsLoading(true);
        const imageMap = new Map();

        const batchSize = 2;
        for (let i = 0; i < photoIds.length; i += batchSize) {
            const batch = photoIds.slice(i, i + batchSize);
            const promises = batch.map(id => new Promise((resolve) => {
                const img = new Image();
                const url = `${API_BASE_URL}/api/slideshow/photo/${id}`;
                img.onload = () => resolve({ id, url });
                img.onerror = () => resolve(null);
                img.src = url;
            }));

            const results = await Promise.all(promises);
            for (const result of results) {
                if (result) {
                    imageMap.set(result.id, { url: result.url });
                    setPreloadedImages(new Map(imageMap));
                }
            }
        }

        setPreloadedImages(imageMap);
        setIsLoading(false);
        console.log(`Slideshow ready: ${imageMap.size}/${photoIds.length} photos loaded`);
    }, []);

    const refreshPhotos = useCallback(async () => {
        const photoIds = await fetchPhotoList();
        if (photoIds.length > 0) {
            const changed = JSON.stringify(photoIds) !== JSON.stringify(photos);
            if (changed || preloadedImages.size === 0) {
                setPhotos(photoIds);
                await preloadAllPhotos(photoIds);
            }
        }
    }, [fetchPhotoList, preloadAllPhotos, photos, preloadedImages.size]);

    useEffect(() => {
        refreshPhotos();
        const interval = setInterval(refreshPhotos, 60 * 60 * 1000);
        return () => clearInterval(interval);
    }, [refreshPhotos]);

    const getCurrentPhotoData = useCallback(() => {
        if (photos.length === 0 || preloadedImages.size === 0) {
            return { currentUrl: null, nextUrl: null, isReady: false };
        }
        const currentId = photos[currentPhotoIndex];
        const nextId = photos[(currentPhotoIndex + 1) % photos.length];
        return {
            currentUrl: preloadedImages.get(currentId)?.url || null,
            nextUrl: preloadedImages.get(nextId)?.url || null,
            isReady: !!preloadedImages.get(currentId),
        };
    }, [photos, preloadedImages, currentPhotoIndex]);

    const nextPhoto = useCallback(() => {
        if (photos.length > 1 && preloadedImages.size > 0) {
            setCurrentPhotoIndex((prev) => (prev + 1) % photos.length);
        }
    }, [photos.length, preloadedImages.size]);

    return {
        photos,
        isLoading,
        isReady: preloadedImages.size > 0 && !isLoading,
        loadedCount: preloadedImages.size,
        totalCount: photos.length,
        currentPhotoIndex,
        getCurrentPhotoData,
        nextPhoto,
        refreshPhotos
    };
}
