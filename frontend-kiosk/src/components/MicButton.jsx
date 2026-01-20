import { motion } from 'framer-motion';

/**
 * Push-to-talk microphone button.
 * Hold to record, release to stop.
 */
export default function MicButton({ isRecording, onStart, onStop, disabled, error }) {
    return (
        <div className="absolute top-4 left-4 z-50 flex flex-col items-center">
            {/* Error message */}
            {error && (
                <div className="mb-2 px-3 py-1 bg-red-500/80 rounded-lg text-xs text-white">
                    {error}
                </div>
            )}

            {/* Microphone button */}
            <motion.button
                className={`w-14 h-14 rounded-full flex items-center justify-center transition-colors shadow-lg backdrop-blur-md border ${isRecording
                    ? 'bg-red-500/90 border-red-400/50 shadow-red-500/50'
                    : disabled
                        ? 'bg-gray-600/50 border-gray-500/30'
                        : 'bg-white/15 border-white/20 hover:bg-white/25'
                    }`}
                whileTap={{ scale: 0.95 }}
                animate={isRecording ? {
                    scale: [1, 1.1, 1],
                    transition: { repeat: Infinity, duration: 1 }
                } : {}}
                onTouchStart={(e) => {
                    e.preventDefault();
                    if (!disabled) onStart();
                }}
                onTouchEnd={(e) => {
                    e.preventDefault();
                    onStop();
                }}
                onMouseDown={() => !disabled && onStart()}
                onMouseUp={onStop}
                onMouseLeave={onStop}
                disabled={disabled}
                style={{ touchAction: 'manipulation' }}
            >
                {/* Microphone icon */}
                <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="currentColor"
                    className={`w-7 h-7 ${isRecording ? 'text-white' : 'text-white/80'}`}
                >
                    <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                    <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                </svg>
            </motion.button>
        </div>
    );
}

