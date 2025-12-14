import { AnimatePresence, motion } from 'framer-motion';

export default function TranscriptionScreen({ transcript, isListening, agentState }) {
    return (
        <div className="h-full w-full flex flex-col items-center justify-center p-12 bg-black relative">
            {/* Status Indicator */}
            <div className="absolute top-12 left-12 flex items-center space-x-4">
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

            {/* Main Content Area */}
            <div className="w-full max-w-5xl text-center">
                <AnimatePresence mode='wait'>
                    {transcript ? (
                        <motion.div
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0 }}
                        >
                            <p className="text-4xl md:text-5xl font-light tracking-tight text-white leading-relaxed">
                                "{transcript}"
                            </p>
                        </motion.div>
                    ) : (
                        <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="text-white/40"
                        >
                            <p className="text-3xl font-light tracking-wide">Say "Hey Jarvis"</p>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>

            {/* Ambient glow when listening */}
            {isListening && (
                <motion.div
                    className="absolute inset-0 pointer-events-none"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                >
                    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-red-500/10 rounded-full blur-3xl animate-pulse" />
                </motion.div>
            )}
        </div>
    );
}
