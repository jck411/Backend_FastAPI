import { useEffect } from 'react';

/**
 * Transcription Overlay - Modal overlay for voice interaction.
 * Appears when mic is tapped, shows live transcript and AI responses.
 * Auto-closes after idle timeout (handled by parent).
 *
 * PERFORMANCE: Uses CSS transitions instead of Framer Motion to reduce CPU load
 * during TTS playback on low-power devices.
 */
export default function TranscriptionOverlay({
    messages,
    liveTranscript,
    isListening,
    agentState,
    toolStatus,
    messagesEndRef,
    onClose
}) {
    // Auto-scroll effect
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, liveTranscript]);

    return (
        <div
            className="fixed inset-0 z-40 bg-black/90 backdrop-blur-md font-sans animate-fade-in"
        >
            {/* Close Button (top-left, avoiding Fully Kiosk swipe area) */}
            <button
                onClick={onClose}
                className="absolute top-4 left-20 z-50 w-10 h-10 flex items-center justify-center rounded-full bg-white/10 hover:bg-white/20 backdrop-blur-md border border-white/10 transition-colors"
                style={{ touchAction: 'manipulation' }}
            >
                <svg className="w-5 h-5 text-white/70" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>

            {/* Tool Status Indicator (Top Left, after close button) */}
            {toolStatus && (
                <div className="absolute top-4 left-36 z-50">
                    <div className={`flex items-center gap-2 backdrop-blur-md px-3 py-2 rounded-full border text-xs sm:text-sm ${toolStatus.status === 'started'
                        ? 'bg-amber-500/15 border-amber-500/25 text-amber-300'
                        : toolStatus.status === 'finished'
                            ? 'bg-green-500/15 border-green-500/25 text-green-300'
                            : 'bg-red-500/15 border-red-500/25 text-red-300'
                        }`}>
                        <span className="text-base sm:text-lg">
                            {toolStatus.status === 'started' ? '⏵' : toolStatus.status === 'finished' ? '✓' : '⚠︎'}
                        </span>
                        <span className="font-semibold tracking-tight">
                            {toolStatus.name}
                        </span>
                        {toolStatus.status === 'started' && (
                            <div className="w-1.5 h-1.5 bg-current rounded-full animate-pulse" />
                        )}
                    </div>
                </div>
            )}

            {/* Status Indicator (Top Right) */}
            <div className="absolute top-4 right-4 z-50">
                {isListening ? (
                    <div className="flex items-center space-x-2 bg-white/10 backdrop-blur-md px-3 py-2 rounded-full border border-white/10 text-red-300 text-xs sm:text-sm">
                        <div className="w-2 h-2 bg-current rounded-full animate-pulse" />
                        <span className="font-bold tracking-wide">LISTENING</span>
                    </div>
                ) : agentState !== 'IDLE' ? (
                    <div className="flex items-center space-x-2 bg-white/5 backdrop-blur-md px-3 py-2 rounded-full border border-white/5 text-cyan-300 text-xs sm:text-sm">
                        <div className="w-2 h-2 bg-current rounded-full animate-pulse" />
                        <span className="font-bold tracking-wide uppercase truncate max-w-[9ch]">{agentState}</span>
                    </div>
                ) : (
                    <div className="flex items-center space-x-2 bg-white/5 backdrop-blur-md px-3 py-2 rounded-full border border-white/5 text-white/40 text-xs sm:text-sm">
                        <span className="font-medium tracking-wide">Closing soon...</span>
                    </div>
                )}
            </div>

            {/* Content Area - no mask to avoid clipping bottom text */}
            <div
                className="h-full w-full max-w-5xl mx-auto flex flex-col justify-end pt-16 pb-12 px-6 sm:px-10 z-10 overflow-y-auto no-scrollbar"
            >
                <div className="flex-1" />

                <div className="space-y-6 flex flex-col min-h-0">
                    {messages.map((msg, idx) => (
                        <div
                            key={idx}
                            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} w-full animate-slide-up`}
                        >
                            <div className={`max-w-[85%] ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                                <p className={`${msg.role === 'user'
                                    ? 'text-[clamp(1.05rem,4vw,1.35rem)] text-white/70 leading-[1.35]'
                                    : 'text-[clamp(1.35rem,5vw,2rem)] font-medium text-white leading-snug'
                                    } break-words whitespace-pre-wrap`}>
                                    {msg.text}
                                    {msg.pending && <span className="animate-pulse">▋</span>}
                                </p>
                            </div>
                        </div>
                    ))}

                    {liveTranscript && (
                        <div className="flex flex-col items-end w-full animate-fade-in">
                            <div className="max-w-[90%] text-right">
                                <p className="text-[clamp(1.2rem,4.8vw,1.6rem)] text-white italic opacity-80 break-words leading-[1.35]">
                                    {liveTranscript}
                                </p>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} className="h-16 w-full" />
                </div>
            </div>

            {/* Empty State - only show when listening with no activity */}
            {messages.length === 0 && !liveTranscript && isListening && (
                <div className="absolute inset-0 flex flex-col items-center justify-center z-0 pointer-events-none p-10 text-center">
                    <div className="space-y-4 animate-fade-in">
                        <div className="w-16 h-16 mx-auto rounded-full bg-red-500/20 border-2 border-red-400/50 flex items-center justify-center">
                            <div className="w-4 h-4 bg-red-400 rounded-full animate-pulse" />
                        </div>
                        <h1 className="text-[clamp(1.8rem,7vw,2.5rem)] font-bold text-white">Listening...</h1>
                        <p className="text-[clamp(1rem,4vw,1.3rem)] text-white/60 font-light">Speak now</p>
                    </div>
                </div>
            )}
        </div>
    );
}
