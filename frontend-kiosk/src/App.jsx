import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import useWebSocket, { ReadyState } from 'react-use-websocket';
import Clock from './components/Clock';
import PhotoFrame from './components/PhotoFrame';
import TranscriptionScreen from './components/TranscriptionScreen';

export default function App() {
    // 0 = Clock, 1 = Photos, 2 = Transcription
    const [currentScreen, setCurrentScreen] = useState(0);

    // WebSocket Connection - connects to backend
    const wsUrl = `ws://${window.location.hostname}:8000/api/voice/connect?client_id=frontend_gui`;

    const [transcript, setTranscript] = useState("");
    const [agentState, setAgentState] = useState("IDLE");

    const {
        sendMessage,
        lastMessage,
        readyState
    } = useWebSocket(wsUrl, {
        onOpen: () => console.log('WebSocket Connected'),
        shouldReconnect: () => true,
        reconnectAttempts: 10,
        reconnectInterval: 3000,
    });

    useEffect(() => {
        if (lastMessage !== null) {
            try {
                const data = JSON.parse(lastMessage.data);
                if (data.type === 'transcript') {
                    setTranscript(data.text);
                } else if (data.type === 'state') {
                    setAgentState(data.state);
                    if (data.state === 'LISTENING' || data.state === 'THINKING') {
                        setCurrentScreen(2); // Auto-jump to transcription screen
                    }
                    if (data.state === 'IDLE') {
                        // Return to clock after delay
                        setTimeout(() => setCurrentScreen(0), 10000);
                    }
                }
            } catch (e) {
                console.error("Failed to parse WS message", e);
            }
        }
    }, [lastMessage]);

    const handleSwipe = (direction) => {
        if (direction > 0) {
            setCurrentScreen((prev) => (prev + 1) % 3);
        } else {
            setCurrentScreen((prev) => (prev === 0 ? 2 : prev - 1));
        }
    };

    const screens = [
        <Clock key="clock" />,
        <PhotoFrame key="photos" />,
        <TranscriptionScreen
            key="transcription"
            transcript={transcript}
            isListening={agentState === 'LISTENING'}
            agentState={agentState}
        />
    ];

    return (
        <div className="w-screen h-screen bg-black overflow-hidden relative font-sans text-white select-none">
            <AnimatePresence mode="popLayout" initial={false}>
                <motion.div
                    key={currentScreen}
                    className="absolute inset-0 w-full h-full"
                    initial={{ x: 300, opacity: 0 }}
                    animate={{ x: 0, opacity: 1 }}
                    exit={{ x: -300, opacity: 0 }}
                    transition={{ type: "spring", stiffness: 300, damping: 30 }}
                    drag="x"
                    dragConstraints={{ left: 0, right: 0 }}
                    dragElastic={0.2}
                    onDragEnd={(e, { offset }) => {
                        if (offset.x < -100) handleSwipe(1);
                        else if (offset.x > 100) handleSwipe(-1);
                    }}
                >
                    {screens[currentScreen]}
                </motion.div>
            </AnimatePresence>

            {/* Page Indicators */}
            <div className="absolute bottom-6 left-1/2 -translate-x-1/2 flex space-x-3 z-50">
                {[0, 1, 2].map((i) => (
                    <div
                        key={i}
                        className={`h-1.5 rounded-full transition-all duration-300 ${i === currentScreen ? 'bg-white w-8' : 'bg-white/40 w-1.5'
                            }`}
                    />
                ))}
            </div>

            {/* Connection Indicator */}
            <div
                className="fixed top-2 right-2 w-2 h-2 rounded-full z-50 transition-colors"
                style={{ backgroundColor: readyState === ReadyState.OPEN ? '#00ADB5' : '#FF4136' }}
            />
        </div>
    );
}
