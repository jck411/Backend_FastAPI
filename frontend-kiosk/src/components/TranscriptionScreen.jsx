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
                <div className="absolute top-6 left-6 z-50">
                    <div className={`flex items-center space-x-2 backdrop-blur-md px-4 py-2 rounded-full border ${toolStatus.status === 'started'
                            ? 'bg-amber-500/20 border-amber-500/30 text-amber-400'
                            : toolStatus.status === 'finished'
                                ? 'bg-green-500/20 border-green-500/30 text-green-400'
                                : 'bg-red-500/20 border-red-500/30 text-red-400'
                        }`}>
                        <span className="text-lg">🔧</span>
                        <span className="text-sm font-medium">
                            {toolStatus.status === 'started' ? 'Running' : toolStatus.status === 'finished' ? 'Done' : 'Error'}: {toolStatus.name}
                        </span>
                        {toolStatus.status === 'started' && (
                            <div className="w-2 h-2 bg-current rounded-full animate-pulse" />
                        )}
                    </div>
                </div>
            )}

            {/* Status Indicator (Top Right) */}
            <div className="absolute top-6 right-6 z-50">
                <AnimatePresence mode="wait">
                    {isListening ? (
                        <div className="flex items-center space-x-3 bg-white/10 backdrop-blur-md px-4 py-2 rounded-full border border-white/10 text-red-400">
                            <div className="w-2 h-2 bg-current rounded-full animate-pulse" />
                            <span className="text-sm font-bold tracking-wide">LISTENING</span>
                        </div>
                    ) : agentState !== 'IDLE' ? (
                        <div className="flex items-center space-x-3 bg-white/5 backdrop-blur-md px-4 py-2 rounded-full border border-white/5 text-cyan-400">
                            <div className="w-2 h-2 bg-current rounded-full animate-pulse" />
                            <span className="text-sm font-bold tracking-wide uppercase">{agentState}</span>
                        </div>
                    ) : null}
                </AnimatePresence>
            </div>

            {/* Content Area */}
            <div
                className="flex-1 w-full max-w-5xl mx-auto flex flex-col justify-end my-12 px-8 z-10 overflow-y-auto no-scrollbar"
                style={{ maskImage: 'linear-gradient(to bottom, transparent, black 15%, black 100%)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, black 15%, black 100%)' }}
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
                                    ? 'text-xl text-white/70'
                                    : 'text-3xl font-medium text-white leading-snug'
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
                                <p className="text-2xl text-white italic opacity-80 break-words">
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
                <div className="absolute inset-0 flex flex-col items-center justify-center z-0 pointer-events-none p-12 text-center opacity-40">
                    <h1 className="text-6xl font-bold text-white mb-4">Hi there.</h1>
                    <p className="text-2xl text-white font-light">Say "Hey Jarvis" or tap the mic</p>
                </div>
            )}

            {/* Listen Button (Bottom Center) */}
            {agentState === 'IDLE' && onActivateListening && (
                <motion.button
                    initial={{ opacity: 0, scale: 0.8 }}
                    animate={{ opacity: 1, scale: 1 }}
                    exit={{ opacity: 0, scale: 0.8 }}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={onActivateListening}
                    className="absolute bottom-20 left-1/2 -translate-x-1/2 z-50 w-16 h-16 rounded-full bg-white/10 backdrop-blur-md border border-white/20 flex items-center justify-center text-white hover:bg-white/20 transition-colors"
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
