import { AnimatePresence, motion } from 'framer-motion';

export default function TranscriptionScreen({ messages, liveTranscript, isListening, agentState, messagesEndRef }) {
    return (
        <div className="h-full w-full flex flex-col p-8 bg-black relative">
            {/* Status Indicator */}
            <div className="absolute top-8 left-8 flex items-center space-x-4 z-50">
                {isListening ? (
                    <div className="flex items-center space-x-2 text-red-500">
                        <div className="w-3 h-3 bg-current rounded-full animate-pulse" />
                        <span className="text-sm font-medium tracking-widest uppercase">Listening</span>
                    </div>
                ) : (
                    <div className="flex items-center space-x-2 text-gray-600">
                        <div className="w-3 h-3 bg-current rounded-full" />
                        <span className="text-sm font-medium tracking-widest uppercase">{agentState}</span>
                    </div>
                )}
            </div>

            {/* Chat History */}
            <div className="flex-1 w-full max-w-5xl mx-auto overflow-y-auto space-y-6 pt-16 pb-32 no-scrollbar">
                {messages.map((msg, idx) => (
                    <motion.div
                        key={idx}
                        initial={{ opacity: 0, y: 10 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                    >
                        <div className={`max-w-[80%] rounded-2xl p-6 ${msg.role === 'user'
                                ? 'bg-white/10 text-white rounded-br-none'
                                : 'bg-cyan-500/10 text-cyan-400 rounded-bl-none'
                            }`}>
                            <p className="text-2xl md:text-3xl font-light leading-relaxed">
                                {msg.text}
                            </p>
                        </div>
                    </motion.div>
                ))}

                {/* Live Transcript (Pending User Input) */}
                <AnimatePresence>
                    {liveTranscript && (
                        <motion.div
                            initial={{ opacity: 0, y: 10 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                            className="flex flex-col items-end"
                        >
                            <div className="max-w-[80%] bg-white/5 text-white/70 rounded-2xl p-6 rounded-br-none backdrop-blur-sm">
                                <p className="text-2xl md:text-3xl font-light leading-relaxed italic">
                                    {liveTranscript}...
                                </p>
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>

                <div ref={messagesEndRef} />
            </div>

            {/* Empty State Prompt */}
            {messages.length === 0 && !liveTranscript && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <motion.div
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        className="text-white/40"
                    >
                        <p className="text-3xl font-light tracking-wide">Say "Hey Jarvis"</p>
                    </motion.div>
                </div>
            )}

            {/* Ambient glow when listening */}
            {isListening && (
                <motion.div
                    className="absolute inset-0 pointer-events-none z-0"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                >
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-red-500/5 rounded-full blur-3xl animate-pulse" />
                </motion.div>
            )}
        </div>
    );
}
