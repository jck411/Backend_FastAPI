import { useEffect } from 'react';

export default function TranscriptionScreen({ messages, liveTranscript, isListening, agentState, toolStatus, messagesEndRef, onActivateListening }) {
    // Auto-scroll effect
    useEffect(() => {
        if (messagesEndRef.current) {
            messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
        }
    }, [messages, liveTranscript]);

    // Tap-to-listen: only when idle and callback provided
    const canTapToListen = agentState === 'IDLE' && onActivateListening;

    return (
        <div
            className={`h-full w-full flex flex-col bg-black relative overflow-hidden font-sans ${canTapToListen ? 'cursor-pointer' : ''}`}
            onClick={canTapToListen ? onActivateListening : undefined}
        >

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
            </div>

            {/* Content Area */}
            <div
                className="flex-1 w-full max-w-5xl mx-auto flex flex-col justify-end my-8 sm:my-10 px-5 sm:px-8 z-10 overflow-y-auto no-scrollbar"
                style={{ maskImage: 'linear-gradient(to bottom, transparent, black 12%, black 100%)', WebkitMaskImage: 'linear-gradient(to bottom, transparent, black 12%, black 100%)' }}
            >
                <div className="flex-1" />

                <div className="space-y-6 flex flex-col min-h-0">
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

            {/* Empty State - only show when idle with no activity */}
            {messages.length === 0 && !liveTranscript && !isListening && agentState === 'IDLE' && (
                <div className="absolute inset-0 flex flex-col items-center justify-center z-0 pointer-events-none p-10 text-center opacity-40">
                    <h1 className="text-[clamp(2.4rem,9vw,3.5rem)] font-bold text-white mb-4">Hi there.</h1>
                    <p className="text-[clamp(1.2rem,5vw,1.7rem)] text-white font-light">Say "Hey Jarvis" or tap anywhere</p>
                </div>
            )}
        </div>
    );
}
