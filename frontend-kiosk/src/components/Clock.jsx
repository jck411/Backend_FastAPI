import { useEffect, useState } from 'react';

/**
 * Clock component designed for Echo Show 5 (960x480) with photo slideshow background.
 * Time and date are positioned in the bottom-left corner as an overlay.
 */
export default function Clock() {
    const [time, setTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => setTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    const formatTime = (date) => {
        const hours = date.getHours();
        const minutes = date.getMinutes();
        const hour12 = hours % 12 || 12;
        const ampm = hours >= 12 ? 'PM' : 'AM';
        const paddedMinutes = minutes.toString().padStart(2, '0');
        return { time: `${hour12}:${paddedMinutes}`, ampm };
    };

    const formatDate = (date) => {
        return date.toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
        });
    };

    const { time: timeStr, ampm } = formatTime(time);

    return (
        <div className="h-full w-full relative bg-black">
            {/* Slideshow placeholder - photos will render here */}
            <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-black">
                {/* Placeholder gradient - will be replaced by slideshow images */}
            </div>

            {/* Bottom gradient overlay for text legibility */}
            <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/70 via-black/30 to-transparent pointer-events-none" />

            {/* Clock overlay - bottom left positioning */}
            <div className="absolute bottom-6 left-6 z-10">
                {/* Time display */}
                <div className="flex items-baseline gap-2">
                    <span className="text-6xl font-light tracking-tight text-white drop-shadow-lg">
                        {timeStr}
                    </span>
                    <span className="text-xl font-light text-white/80 drop-shadow-lg">
                        {ampm}
                    </span>
                </div>

                {/* Date display */}
                <div className="text-lg font-light text-white/70 tracking-wide mt-1 drop-shadow-lg">
                    {formatDate(time)}
                </div>
            </div>
        </div>
    );
}
