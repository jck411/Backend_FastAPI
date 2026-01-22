/**
 * Optimized Photo Preloader Hook - Loads all photos once for smooth slideshow
 *
 * This replaces the on-demand loading with bulk preloading to:
 * - Eliminate jittery loading during transitions
 * - Reduce memory fragmentation from repeated load/unload cycles
 * - Minimize network requests (load once vs every 30 seconds)
 * - Provide predictable memory usage
 */

import { useCallback, useEffect, useRef, useState } from 'react';

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
        let loadedCount = 0;

        console.log(`🖼️  Starting slideshow preload: ${photoList.length} photos to download`);
        console.log(`📦 Loading in batches of 5 to avoid browser overwhelm...`);

        // Load photos in batches to avoid overwhelming browser (smaller batches for more frequent progress updates)
        const batchSize = 2;
        const totalBatches = Math.ceil(photoList.length / batchSize);

        for (let i = 0; i < photoList.length; i += batchSize) {
            const batch = photoList.slice(i, i + batchSize);
            const batchPromises = batch.map(filename => preloadPhoto(filename));
            const currentBatch = Math.floor(i / batchSize) + 1;

            console.log(`⬇️  Batch ${currentBatch}/${totalBatches}: downloading ${batch.length} photos...`);

            try {
                const results = await Promise.allSettled(batchPromises);
                results.forEach((result, index) => {
                    if (result.status === 'fulfilled') {
                        const { filename, img, url } = result.value;
                        imageMap.set(filename, { img, url });
                        loadedCount++;

                        // Update state immediately for real-time progress bar
                        setPreloadedImages(new Map(imageMap));

                        // Show countdown progress for each photo
                        const remaining = photoList.length - loadedCount;
                        console.log(`✅ ${filename} loaded (${loadedCount}/${photoList.length}) - ${remaining} remaining`);
                    } else {
                        console.warn(`❌ Failed to load: ${batch[index]}`);
                    }
                });

                console.log(`📊 Batch ${currentBatch} complete: ${loadedCount}/${photoList.length} total photos loaded`);
            } catch (err) {
                console.warn('Error in batch loading:', err);
            }
        }

        setPreloadedImages(imageMap);
        setIsLoading(false);

        const successRate = Math.round((imageMap.size / photoList.length) * 100);
        console.log(`🎉 Slideshow preload complete!`);
        console.log(`📈 Success rate: ${imageMap.size}/${photoList.length} photos (${successRate}%)`);
        console.log(`💾 Estimated memory usage: ${Math.round(imageMap.size * 0.8)}MB`); // ~800KB average per photo
        console.log(`🚀 Slideshow ready for smooth 30-second transitions!`);
    }, [preloadPhoto]);

    /**
     * Initialize and refresh photos (simple approach)
     */
    const refreshPhotos = useCallback(async () => {
        const photoList = await fetchPhotoList();
        if (photoList.length > 0) {
            // Simple check: only reload if photo list actually changed
            const photosChanged = JSON.stringify(photoList.sort()) !== JSON.stringify(photos.sort());
            
            if (photosChanged || preloadedImages.size === 0) {
                console.log(`📸 ${photosChanged ? 'Photo list changed' : 'Cache empty'}, preloading ${photoList.length} photos...`);
                setPhotos(photoList);
                await preloadAllPhotos(photoList);
            } else {
                console.log('📋 Photo list unchanged, keeping existing preloaded images');
            }
        }
    }, [fetchPhotoList, preloadAllPhotos, photos, preloadedImages.size]);

    // Load photos on mount and refresh hourly (simplified caching)
    useEffect(() => {
        refreshPhotos();
        const refreshInterval = setInterval(() => {
            console.log('⏰ Hourly photo refresh triggered');
            refreshPhotos();
        }, 60 * 60 * 1000); // 1 hour
        
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
