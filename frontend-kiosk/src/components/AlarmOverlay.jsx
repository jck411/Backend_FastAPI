import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

/**
 * AlarmOverlay - Full-screen overlay that appears when an alarm fires.
 * Features:
 * - Pulsing/flashing background
 * - Audio beep pattern using Web Audio API
 * - Dismiss and Snooze buttons
 */
export default function AlarmOverlay({ 
    alarm, 
    onDismiss, 
    onSnooze,
    snoozeMinutes = 5 
}) {
    const audioContextRef = useRef(null);
    const oscillatorRef = useRef(null);
    const gainNodeRef = useRef(null);
    const isPlayingRef = useRef(false);
    const intervalRef = useRef(null);
    const [flashOn, setFlashOn] = useState(true);

    /**
     * Play alarm beep pattern using Web Audio API.
     * Pattern: beep-beep-beep with pauses
     */
    const playAlarmSound = () => {
        if (isPlayingRef.current) return;

        try {
            // Create audio context
            const AudioContext = window.AudioContext || window.webkitAudioContext;
            audioContextRef.current = new AudioContext();
            const ctx = audioContextRef.current;

            // Create oscillator for beep sound
            oscillatorRef.current = ctx.createOscillator();
            gainNodeRef.current = ctx.createGain();

            oscillatorRef.current.connect(gainNodeRef.current);
            gainNodeRef.current.connect(ctx.destination);

            // A5 note (880Hz) - urgent but not harsh
            oscillatorRef.current.frequency.value = 880;
            oscillatorRef.current.type = 'sine';

            // Start silent
            gainNodeRef.current.gain.value = 0;
            oscillatorRef.current.start();
            isPlayingRef.current = true;

            // Beep pattern function
            const playBeepPattern = () => {
                if (!audioContextRef.current || audioContextRef.current.state === 'closed') return;
                
                const now = audioContextRef.current.currentTime;
                const gain = gainNodeRef.current.gain;

                // Pattern: 3 short beeps
                for (let i = 0; i < 3; i++) {
                    gain.setValueAtTime(0.5, now + i * 0.25);      // Beep on
                    gain.setValueAtTime(0, now + i * 0.25 + 0.15); // Beep off
                }
            };

            // Play initial beeps
            playBeepPattern();

            // Repeat every 2 seconds
            intervalRef.current = setInterval(() => {
                if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
                    playBeepPattern();
                }
            }, 2000);

        } catch (e) {
            console.error('Failed to create alarm sound:', e);
        }
    };

    /**
     * Stop the alarm sound and clean up audio resources.
     */
    const stopAlarmSound = () => {
        if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
        }

        if (oscillatorRef.current) {
            try {
                oscillatorRef.current.stop();
            } catch (e) {
                // Oscillator may have already stopped
            }
            oscillatorRef.current = null;
        }

        if (audioContextRef.current && audioContextRef.current.state !== 'closed') {
            audioContextRef.current.close();
            audioContextRef.current = null;
        }

        isPlayingRef.current = false;
    };

    // Start sound when alarm appears
    useEffect(() => {
        if (alarm) {
            playAlarmSound();
        }

        return () => {
            stopAlarmSound();
        };
    }, [alarm]);

    // Flash effect
    useEffect(() => {
        if (!alarm) return;

        const flashInterval = setInterval(() => {
            setFlashOn(prev => !prev);
        }, 500);

        return () => clearInterval(flashInterval);
    }, [alarm]);

    const handleDismiss = () => {
        stopAlarmSound();
        onDismiss(alarm.alarm_id);
    };

    const handleSnooze = () => {
        stopAlarmSound();
        onSnooze(alarm.alarm_id, snoozeMinutes);
    };

    if (!alarm) return null;

    return (
        <AnimatePresence>
            <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 z-[100] flex items-center justify-center"
                style={{
                    backgroundColor: flashOn ? 'rgba(220, 38, 38, 0.95)' : 'rgba(185, 28, 28, 0.95)',
                    transition: 'background-color 0.3s ease'
                }}
            >
                <motion.div
                    initial={{ scale: 0.8, opacity: 0 }}
                    animate={{ scale: 1, opacity: 1 }}
                    transition={{ type: 'spring', stiffness: 300, damping: 25 }}
                    className="text-center p-8 max-w-lg"
                >
                    {/* Alarm Icon */}
                    <motion.div
                        animate={{ 
                            rotate: flashOn ? -15 : 15,
                            scale: flashOn ? 1.1 : 1
                        }}
                        transition={{ duration: 0.3 }}
                        className="text-8xl mb-6"
                    >
                        🔔
                    </motion.div>

                    {/* Alarm Label */}
                    <h1 className="text-4xl font-bold text-white mb-4 drop-shadow-lg">
                        {alarm.label || 'Alarm'}
                    </h1>

                    {/* Alarm Time */}
                    <p className="text-2xl text-white/90 mb-8">
                        {new Date(alarm.alarm_time).toLocaleTimeString([], { 
                            hour: '2-digit', 
                            minute: '2-digit' 
                        })}
                    </p>

                    {/* Action Buttons */}
                    <div className="flex gap-6 justify-center">
                        <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={handleSnooze}
                            className="px-8 py-4 bg-white/20 hover:bg-white/30 text-white text-xl font-semibold rounded-2xl backdrop-blur-sm border-2 border-white/30 transition-colors"
                        >
                            💤 Snooze ({snoozeMinutes}m)
                        </motion.button>

                        <motion.button
                            whileHover={{ scale: 1.05 }}
                            whileTap={{ scale: 0.95 }}
                            onClick={handleDismiss}
                            className="px-8 py-4 bg-white text-red-600 text-xl font-semibold rounded-2xl shadow-lg transition-colors hover:bg-gray-100"
                        >
                            ✓ Dismiss
                        </motion.button>
                    </div>
                </motion.div>
            </motion.div>
        </AnimatePresence>
    );
}
