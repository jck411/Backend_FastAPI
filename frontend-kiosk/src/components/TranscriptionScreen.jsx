import { AnimatePresence, motion } from 'framer-motion';
import { useEffect } from 'react';

export default function TranscriptionScreen({ messages, liveTranscript, isListening, agentState, toolStatus, messagesEndRef, onActivateListening }) {
    // Auto-scroll effect
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, liveTranscript]);

    return (
        <div className="h-full w-full flex flex-col bg-black relative overflow-hidden font-sans">

            {/* Tool Status Indicator (Top Left) */}
            {toolStatus && (
                <div className="absolute top-4 left-4 z-50">
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
                <AnimatePresence mode="wait">
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
                    ) : null}
                </AnimatePresence>
            </div>

            {/* Content Area */}
            <div
                className="flex-1 w-full max-w-5xl mx-auto flex flex-col justify-end my-8 sm:my-10 px-5 sm:px-8 z-10 overflow-y-auto no-scrollbar"
                style={{ maskImage: 'linear-gradient(to bottom, transparent, black 12%, black 100%)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, black 12%, black 100%)' }}
            >

                <div className="flex-1" /> {/* Spacer */}

                <div className="space-y-6 flex flex-col min-h-0">
                    {/* History Messages */}
                    {messages.map((msg, idx) => (
                        <div
                            key={idx}
                            className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'} w-full`}
                        >
                            <div className={`max-w-[85%] ${msg.role === 'user' ? 'text-right' : 'text-left'}`}>
                                <p className={`${msg.role === 'user'
                                    ? 'text-[clamp(1.05rem,4vw,1.35rem)] text-white/70 leading-[1.35]'
                                    : 'text-[clamp(1.35rem,5vw,2rem)] font-medium text-white leading-snug'
                                    } break-words whitespace-pre-wrap`}>
                                    {msg.text}
                                </p>
                            </div>
                        </div>
                    ))}

                    {/* Live Transcript (Active Input) */}
                    {liveTranscript && (
                        <div className="flex flex-col items-end w-full">
                            <div className="max-w-[90%] text-right">
                                <p className="text-[clamp(1.2rem,4.8vw,1.6rem)] text-white italic opacity-80 break-words leading-[1.35]">
                                    {liveTranscript}
                                </p>
                            </div>
                        </div>
                    )}

                    <div ref={messagesEndRef} className="h-8 w-full" />
                </div>
            </div>

            {/* Empty State */}
            {messages.length === 0 && !liveTranscript && (
                <div className="absolute inset-0 flex flex-col items-center justify-center z-0 pointer-events-none p-10 text-center opacity-40">
                    <h1 className="text-[clamp(2.4rem,9vw,3.5rem)] font-bold text-white mb-4">Hi there.</h1>
                    <p className="text-[clamp(1.2rem,5vw,1.7rem)] text-white font-light">Say "Hey Jarvis" or tap the mic</p>
                </div>
            )}

            {/* Soft glow behind mic button */}
            <div className="pointer-events-none absolute bottom-10 left-1/2 -translate-x-1/2 w-72 h-44 rounded-full bg-gradient-to-r from-cyan-300/28 via-white/12 to-rose-400/28 blur-[90px]" />

            {/* Listen Button (Bottom Center) */}
            {agentState === 'IDLE' && onActivateListening && (
                <motion.button
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={onActivateListening}
                    className="absolute bottom-16 left-1/2 -translate-x-1/2 z-50 w-16 h-16 sm:w-18 sm:h-18 rounded-full bg-white/10 backdrop-blur-lg border border-white/20 flex items-center justify-center text-white hover:bg-white/20 transition-colors shadow-[0_12px_40px_rgba(0,0,0,0.45)]"
                    aria-label="Start listening"
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        className="w-8 h-8"
                    >
                        <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                        <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                    </svg>
                </motion.button>
            )}
        </div>
    );
}
