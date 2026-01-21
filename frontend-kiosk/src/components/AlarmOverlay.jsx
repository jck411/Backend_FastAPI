import { useEffect, useRef, useState } from 'react';
import { useDisplayTimezone } from '../context/ConfigContext';

const BellIcon = ({ className = '' }) => (
    <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className={className}
    >
        <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M14.25 18.75a2.25 2.25 0 01-4.5 0M4.5 8.25a7.5 7.5 0 0115 0c0 3.222.917 5.003 1.617 5.941.373.497.56.746.543 1.049-.02.36-.214.691-.532.874-.263.151-.62.151-1.334.151H4.206c-.714 0-1.07 0-1.333-.151a1.125 1.125 0 01-.532-.874c-.018-.303.17-.552.543-1.049C3.583 13.253 4.5 11.472 4.5 8.25z"
        />
    </svg>
);

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
    // Get display timezone from context (sourced from backend)
    const displayTimezone = useDisplayTimezone();

    const audioContextRef = useRef(null);
    const oscillatorRef = useRef(null);
    const gainNodeRef = useRef(null);
    const isPlayingRef = useRef(false);
    const intervalRef = useRef(null);
    const [flashOn, setFlashOn] = useState(true);

    const formatAlarmTime = (isoString) => {
        const date = new Date(isoString);
        // Format time in the target timezone
        const formatter = new Intl.DateTimeFormat('en-US', {
            timeZone: displayTimezone,
            hour: 'numeric',
            minute: '2-digit',
            hour12: true,
        });
        const parts = formatter.formatToParts(date);
        const hour = parts.find(p => p.type === 'hour')?.value || '12';
        const minute = parts.find(p => p.type === 'minute')?.value || '00';
        const dayPeriod = parts.find(p => p.type === 'dayPeriod')?.value?.toUpperCase() || 'AM';
        return { time: `${hour}:${minute}`, ampm: dayPeriod };
    };

    const getTimeUntilAlarm = (isoString) => {
        const alarmTime = new Date(isoString);
        const now = new Date();
        const diffMs = alarmTime - now;

        if (diffMs <= 0) return 'Now';

        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const remainingMins = diffMins % 60;

        if (diffHours > 0) {
            return `in ${diffHours}h ${remainingMins}m`;
        }

        return `in ${diffMins}m`;
    };

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

    const formattedAlarm = formatAlarmTime(alarm.alarm_time);
    const timeUntil = getTimeUntilAlarm(alarm.alarm_time);

    return (
        <div
            className="fixed inset-0 z-[100] flex items-center justify-center overflow-hidden animate-fade-in"
            style={{
                backgroundImage: `
                    radial-gradient(circle at 20% 20%, rgba(56, 189, 248, ${flashOn ? 0.24 : 0.14}), transparent 35%),
                    radial-gradient(circle at 80% 0%, rgba(236, 72, 153, ${flashOn ? 0.22 : 0.12}), transparent 38%),
                    radial-gradient(circle at 50% 80%, rgba(248, 113, 113, ${flashOn ? 0.20 : 0.12}), transparent 32%),
                    linear-gradient(135deg, #05070d 0%, #0a0f1f 45%, #05070d 100%)
                `
            }}
        >
            <div className="absolute inset-0 bg-gradient-to-b from-white/5 via-transparent to-black/70" />

            <div className="relative z-10 w-full max-w-4xl px-4 sm:px-10">
                <div className="flex flex-col items-center gap-6 sm:gap-10">
                    <div className="flex items-center gap-3 text-cyan-200/80 text-xs tracking-[0.3em] uppercase">
                        <span className="h-2 w-2 rounded-full bg-cyan-300 animate-pulse" />
                        <span>Alarm active</span>
                    </div>

                    <div className="relative">
                        <div
                            className={`relative flex items-center justify-center w-36 h-36 sm:w-48 sm:h-48 rounded-full bg-white/5 border border-white/10 transition-transform duration-300 ${flashOn ? 'scale-105' : 'scale-100'}`}
                        >
                            <BellIcon className="w-12 h-12 sm:w-16 sm:h-16 text-white" />
                        </div>
                    </div>

                    <div className="text-center space-y-4">
                        <h1 className="text-[clamp(1.8rem,5vw,2.4rem)] sm:text-4xl font-semibold tracking-tight text-white">
                            {alarm.label || 'Alarm'}
                        </h1>
                        <div className="flex items-baseline justify-center gap-3">
                            <span className="text-[clamp(2.8rem,13vw,4.5rem)] sm:text-7xl font-light tracking-tight text-white">
                                {formattedAlarm.time}
                            </span>
                            <span className="text-[clamp(1.1rem,4vw,1.6rem)] sm:text-2xl font-semibold text-cyan-200/80">
                                {formattedAlarm.ampm}
                            </span>
                        </div>
                        <div className="flex items-center justify-center gap-2.5 text-sm text-white/70">
                            <span className="px-3 py-1 rounded-full bg-white/5 border border-white/10">
                                {timeUntil}
                            </span>
                            <span className="text-cyan-100/80">Snooze: {snoozeMinutes}m</span>
                        </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 sm:gap-6 w-full max-w-2xl">
                        <button
                            onClick={handleSnooze}
                            className="rounded-2xl px-6 py-4 bg-gradient-to-r from-cyan-400 to-sky-500 text-slate-950 font-semibold active:scale-95 transition-transform"
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col items-start">
                                    <span className="text-xs uppercase tracking-[0.2em] text-slate-900/70">Snooze</span>
                                    <span className="text-xl mt-1">Pause for {snoozeMinutes}m</span>
                                </div>
                                <span className="text-2xl">💤</span>
                            </div>
                        </button>

                        <button
                            onClick={handleDismiss}
                            className="rounded-2xl px-6 py-4 bg-gradient-to-r from-rose-500 via-orange-500 to-amber-400 text-white font-semibold active:scale-95 transition-transform"
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex flex-col items-start">
                                    <span className="text-xs uppercase tracking-[0.2em] text-white/70">Dismiss</span>
                                    <span className="text-xl mt-1">I&apos;m awake</span>
                                </div>
                                <span className="text-2xl">✓</span>
                            </div>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    );
}
