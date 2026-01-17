import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';
import { useDisplayTimezone } from '../context/ConfigContext';

/**
 * Format a date string for display.
 * Returns "Today", "Tomorrow", or the day name for dates within a week.
 */
function formatDateHeader(dateStr, timezone) {
    const date = new Date(dateStr);

    // Get today and tomorrow in the display timezone
    const now = new Date();
    const todayStr = now.toLocaleDateString('en-CA', { timeZone: timezone }); // YYYY-MM-DD format
    const tomorrow = new Date(now.getTime() + 86400000);
    const tomorrowStr = tomorrow.toLocaleDateString('en-CA', { timeZone: timezone });

    // Get the event date in the display timezone
    const eventDateStr = date.toLocaleDateString('en-CA', { timeZone: timezone });

    if (eventDateStr === todayStr) {
        return 'Today';
    } else if (eventDateStr === tomorrowStr) {
        return 'Tomorrow';
    } else {
        return date.toLocaleDateString('en-US', {
            timeZone: timezone,
            weekday: 'long',
            month: 'short',
            day: 'numeric'
        });
    }
}

/**
 * Format time from ISO string.
 */
function formatTime(dateStr, timezone) {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', {
        timeZone: timezone,
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

/**
 * Get the date key (YYYY-MM-DD) from a date string.
 */
function getDateKey(dateStr, timezone) {
    // Handle date-only strings (all-day events)
    if (dateStr.length === 10) {
        return dateStr;
    }
    const date = new Date(dateStr);
    // Use the display timezone to get the correct date
    return date.toLocaleDateString('en-CA', { timeZone: timezone });
}

/**
 * Group events by date.
 */
function groupEventsByDate(events, timezone) {
    const groups = {};

    for (const event of events) {
        const dateKey = getDateKey(event.start, timezone);
        if (!groups[dateKey]) {
            groups[dateKey] = [];
        }
        groups[dateKey].push(event);
    }

    // Sort dates
    const sortedDates = Object.keys(groups).sort();

    return sortedDates.map(date => ({
        date,
        label: formatDateHeader(date, timezone),
        events: groups[date],
    }));
}

/**
 * Calendar color based on calendar label.
 */
function getCalendarColor(calendarLabel) {
    const colors = {
        'Your Primary Calendar': 'bg-blue-500',
        'Family Calendar': 'bg-green-500',
        'Holidays in United States': 'bg-red-500',
        'Mom Work Schedule': 'bg-purple-500',
        'Dad Work Schedule': 'bg-orange-500',
    };
    return colors[calendarLabel] || 'bg-cyan-500';
}

export default function CalendarScreen() {
    // Get display timezone from context (sourced from backend)
    const displayTimezone = useDisplayTimezone();

    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const fetchCalendar = async () => {
        try {
            const response = await fetch(`http://${window.location.hostname}:8000/api/kiosk/calendar?days=7`);
            if (!response.ok) {
                let errorDetail = `HTTP ${response.status}`;
                try {
                    const errorData = await response.json();
                    errorDetail = errorData.detail || errorDetail;
                } catch {
                    // Ignore JSON parse errors
                }
                throw new Error(errorDetail);
            }
            const data = await response.json();
            setEvents(data.events || []);
            setError(null);
        } catch (e) {
            console.error('Failed to fetch calendar:', e);
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    // Fetch on mount only (manual refresh via button)
    useEffect(() => {
        fetchCalendar();
    }, []);

    const handleRefresh = () => {
        setLoading(true);
        fetchCalendar();
    };

    const groupedEvents = groupEventsByDate(events, displayTimezone);

    return (
        <div className="h-full w-full flex flex-col bg-black relative overflow-hidden font-sans">
            {/* Header */}
            <div className="px-6 sm:px-8 pt-6 sm:pt-8 pb-4 flex items-start justify-between">
                <div>
                    <h1 className="text-[clamp(1.6rem,5vw,2.1rem)] font-bold text-white">Calendar</h1>
                    <p className="text-white/50 text-[clamp(0.8rem,3vw,0.95rem)] mt-1">Next 7 days</p>
                </div>
                <button
                    onClick={handleRefresh}
                    disabled={loading}
                    className="p-3 sm:p-3.5 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-50 transition-colors"
                    aria-label="Refresh calendar"
                >
                    <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className={`w-5 h-5 text-white ${loading ? 'animate-spin' : ''}`}
                    >
                        <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8" />
                        <path d="M21 3v5h-5" />
                    </svg>
                </button>
            </div>

            {/* Content Area */}
            <div
                className="flex-1 overflow-y-auto no-scrollbar px-6 sm:px-8 pb-16 sm:pb-20"
                style={{
                    maskImage: 'linear-gradient(to bottom, black 0%, black 90%, transparent 100%)',
                    WebkitMaskImage: 'linear-gradient(to bottom, black 0%, black 90%, transparent 100%)'
                }}
            >
                {loading ? (
                    <div className="flex items-center justify-center h-64">
                        <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    </div>
                ) : error ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center">
                        <span className="text-4xl mb-4">📅</span>
                        <p className="text-white/70 text-lg">Unable to load calendar</p>
                        <p className="text-white/40 text-sm mt-2">{error}</p>
                        <button
                            onClick={fetchCalendar}
                            className="mt-4 px-4 py-2 bg-white/10 hover:bg-white/20 rounded-full text-sm text-white transition-colors"
                        >
                            Retry
                        </button>
                    </div>
                ) : events.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-64 text-center opacity-50">
                        <span className="text-6xl mb-4">📅</span>
                        <p className="text-white text-xl">No upcoming events</p>
                        <p className="text-white/70 text-sm mt-2">Your calendar is clear for the next 7 days</p>
                    </div>
                ) : (
                    <div className="space-y-6">
                        {/* Events by Day */}
                        {groupedEvents.map((group, groupIdx) => (
                            <motion.div
                                key={group.date}
                                initial={{ opacity: 0, y: 20 }}
                                animate={{ opacity: 1, y: 0 }}
                                transition={{ delay: groupIdx * 0.1 }}
                            >
                                <h2 className={`sticky top-0 z-10 backdrop-blur-sm bg-black/70 px-2 py-1 -mx-2 rounded-lg text-[clamp(1rem,3.6vw,1.1rem)] font-semibold mb-3 ${group.label === 'Today' ? 'text-cyan-400' : 'text-white/70'
                                    }`}>
                                    {group.label}
                                </h2>

                                <div className="space-y-2">
                                    {group.events.map((event, idx) => (
                                        <motion.div
                                            key={event.id}
                                            initial={{ opacity: 0, x: -20 }}
                                            animate={{ opacity: 1, x: 0 }}
                                            transition={{ delay: groupIdx * 0.1 + idx * 0.05 }}
                                            className="bg-white/5 backdrop-blur-sm rounded-xl p-4 sm:p-4.5 border border-white/10"
                                        >
                                            <div className="flex items-start gap-3">
                                                <div className={`w-1 h-full min-h-[24px] ${getCalendarColor(event.calendar_label)} rounded-full`} />
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-white font-medium truncate text-[clamp(1rem,4vw,1.15rem)] leading-snug">{event.summary}</p>
                                                    <div className="flex flex-wrap items-center gap-2 mt-1">
                                                        {event.is_all_day ? (
                                                            <span className="px-3 py-1 rounded-full bg-white/10 border border-white/15 text-[clamp(0.85rem,3.6vw,1rem)] text-white/80">
                                                                All day
                                                            </span>
                                                        ) : (
                                                            <p className="text-white/60 text-[clamp(0.9rem,3.6vw,1rem)]">
                                                                {formatTime(event.start, displayTimezone)}
                                                                {event.end && ` – ${formatTime(event.end, displayTimezone)}`}
                                                            </p>
                                                        )}
                                                        <span className="text-white/30">•</span>
                                                        <p className="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-white/60 text-[clamp(0.85rem,3.4vw,0.95rem)] truncate">
                                                            {event.calendar_label}
                                                        </p>
                                                    </div>
                                                    {event.location && (
                                                        <p className="text-white/40 text-[clamp(0.85rem,3.4vw,0.95rem)] mt-1 truncate flex items-center gap-1">
                                                            <span>📍</span>
                                                            {event.location}
                                                        </p>
                                                    )}
                                                </div>
                                            </div>
                                        </motion.div>
                                    ))}
                                </div>
                            </motion.div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
