import { useEffect, useState } from 'react';

export default function Clock() {
    const [time, setTime] = useState(new Date());

    useEffect(() => {
        const timer = setInterval(() => setTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    const formatTime = (date) => {
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: true,
        });
    };

    const formatDate = (date) => {
        return date.toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
        });
    };

    return (
        <div className="h-full w-full flex flex-col items-center justify-center bg-gradient-to-br from-gray-900 via-black to-gray-900">
            {/* Time */}
            <div className="text-8xl md:text-9xl font-extralight tracking-tight text-white mb-4">
                {formatTime(time)}
            </div>

            {/* Date */}
            <div className="text-2xl md:text-3xl font-light text-white/60 tracking-wide">
                {formatDate(time)}
            </div>

            {/* Subtle ambient glow */}
            <div className="absolute inset-0 pointer-events-none">
                <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-cyan-500/5 rounded-full blur-3xl" />
            </div>
        </div>
    );
}
