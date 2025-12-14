import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';

// Placeholder images - in production, fetch from API or local storage
const SAMPLE_PHOTOS = [
    'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=1200',
    'https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=1200',
    'https://images.unsplash.com/photo-1426604966848-d7adac402bff?w=1200',
    'https://images.unsplash.com/photo-1433086966358-54859d0ed716?w=1200',
];

export default function PhotoFrame() {
    const [currentIndex, setCurrentIndex] = useState(0);

    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentIndex((prev) => (prev + 1) % SAMPLE_PHOTOS.length);
        }, 8000); // Change photo every 8 seconds
        return () => clearInterval(timer);
    }, []);

    return (
        <div className="h-full w-full bg-black relative overflow-hidden">
            <AnimatePresence mode="wait">
                <motion.img
                    key={currentIndex}
                    src={SAMPLE_PHOTOS[currentIndex]}
                    alt="Photo"
                    className="absolute inset-0 w-full h-full object-cover"
                    initial={{ opacity: 0, scale: 1.1 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 1.5 }}
                />
            </AnimatePresence>

            {/* Subtle vignette overlay */}
            <div className="absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-black/20 pointer-events-none" />

            {/* Photo counter */}
            <div className="absolute bottom-12 right-6 text-white/50 text-sm font-light">
                {currentIndex + 1} / {SAMPLE_PHOTOS.length}
            </div>
        </div>
    );
}
