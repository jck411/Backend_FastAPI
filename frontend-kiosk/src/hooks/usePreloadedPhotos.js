/**
 * Optimized Photo Preloader Hook - Loads all photos once for smooth slideshow
 * 
 * This replaces the on-demand loading with bulk preloading to:
 * - Eliminate jittery loading during transitions
 * - Reduce memory fragmentation from repeated load/unload cycles
 * - Minimize network requests (load once vs every 30 seconds)
 * - Provide predictable memory usage
 */

import { useState, useEffect, useCallback, useRef } from 'react';

const API_BASE_URL = `${window.location.protocol}//${window.location.hostname}:8000`;

/**
 * Hook to preload all slideshow photos into memory for smooth transitions
 */
export function usePreloadedPhotos() {
    const [photos, setPhotos] = useState([]);
    const [preloadedImages, setPreloadedImages] = useState(new Map());
    const [isLoading, setIsLoading] = useState(false);
    const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
    const preloadPromisesRef = useRef(new Map());

    /**
     * Fetch photo list from backend
     */
    const fetchPhotoList = useCallback(async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/api/slideshow/photos?daily_seed=true`);
            if (!response.ok) {
                console.warn('Slideshow photos not available');
                return [];
            }
            const data = await response.json();
            return data.photos || [];
        } catch (err) {
            console.warn('Failed to fetch slideshow photos:', err);
            return [];
        }
    }, []);

    /**
     * Preload a single photo and return a Promise
     */
    const preloadPhoto = useCallback((filename) => {
        // Return existing promise if already loading
        if (preloadPromisesRef.current.has(filename)) {
            return preloadPromisesRef.current.get(filename);
        }

        const promise = new Promise((resolve, reject) => {
            const img = new Image();
            const url = `${API_BASE_URL}/api/slideshow/photo/${filename}`;
            
            img.onload = () => {
                console.log(`Preloaded: ${filename} (${Math.round(img.naturalWidth)}x${img.naturalHeight})`);
                resolve({ filename, img, url });
            };
            
            img.onerror = (err) => {
                console.warn(`Failed to preload: ${filename}`, err);
                reject(err);
            };
            
            img.src = url;
        });

        preloadPromisesRef.current.set(filename, promise);
        return promise;
    }, []);

    /**
     * Preload all photos with progress tracking
     */
    const preloadAllPhotos = useCallback(async (photoList) => {
        if (photoList.length === 0) return;
        
        setIsLoading(true);
        const imageMap = new Map();
        
        console.log(`Preloading ${photoList.length} photos for smooth slideshow...`);
        
        // Load photos in batches to avoid overwhelming browser
        const batchSize = 5;
        for (let i = 0; i < photoList.length; i += batchSize) {
            const batch = photoList.slice(i, i + batchSize);
            const batchPromises = batch.map(filename => preloadPhoto(filename));
            
            try {
                const results = await Promise.allSettled(batchPromises);
                results.forEach((result, index) => {
                    if (result.status === 'fulfilled') {
                        const { filename, img, url } = result.value;
                        imageMap.set(filename, { img, url });
                    } else {
                        console.warn(`Failed to load photo in batch: ${batch[index]}`);
                    }
                });
                
                console.log(`Loaded batch ${Math.floor(i/batchSize) + 1}/${Math.ceil(photoList.length/batchSize)}`);
            } catch (err) {
                console.warn('Error in batch loading:', err);
            }
        }
        
        setPreloadedImages(imageMap);
        setIsLoading(false);
        
        console.log(`Slideshow ready: ${imageMap.size}/${photoList.length} photos loaded`);
        console.log(`Estimated memory usage: ${Math.round(imageMap.size * 0.8)}MB`); // ~800KB average per photo
    }, [preloadPhoto]);

    /**
     * Initialize and refresh photos
     */
    const refreshPhotos = useCallback(async () => {
        const photoList = await fetchPhotoList();
        if (photoList.length > 0 && JSON.stringify(photoList) !== JSON.stringify(photos)) {
            setPhotos(photoList);
            await preloadAllPhotos(photoList);
        }
    }, [fetchPhotoList, preloadAllPhotos, photos]);

    // Load photos on mount and refresh hourly
    useEffect(() => {
        refreshPhotos();
        const refreshInterval = setInterval(refreshPhotos, 60 * 60 * 1000); // 1 hour
        return () => clearInterval(refreshInterval);
    }, [refreshPhotos]);

    /**
     * Get current and next photo URLs for smooth transitions
     */
    const getCurrentPhotoData = useCallback(() => {
        if (photos.length === 0 || preloadedImages.size === 0) {
            return { currentUrl: null, nextUrl: null, isReady: false };
        }

        const currentFilename = photos[currentPhotoIndex];
        const nextIndex = (currentPhotoIndex + 1) % photos.length;
        const nextFilename = photos[nextIndex];

        const current = preloadedImages.get(currentFilename);
        const next = preloadedImages.get(nextFilename);

        return {
            currentUrl: current?.url || null,
            nextUrl: next?.url || null,
            isReady: !!current,
            currentFilename,
            nextFilename
        };
    }, [photos, preloadedImages, currentPhotoIndex]);

    /**
     * Advance to next photo (instant since preloaded)
     */
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