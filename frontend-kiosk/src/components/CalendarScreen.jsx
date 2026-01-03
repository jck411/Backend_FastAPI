import { motion } from 'framer-motion';
import { useEffect, useState } from 'react';

/**
 * Format a date string for display.
 * Returns "Today", "Tomorrow", or the day name for dates within a week.
 */
function formatDateHeader(dateStr) {
    const date = new Date(dateStr);
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    
    const tomorrow = new Date(today);
    tomorrow.setDate(tomorrow.getDate() + 1);
    
    const eventDate = new Date(date);
    eventDate.setHours(0, 0, 0, 0);
    
    if (eventDate.getTime() === today.getTime()) {
        return 'Today';
    } else if (eventDate.getTime() === tomorrow.getTime()) {
        return 'Tomorrow';
    } else {
        return date.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
    }
}

/**
 * Format time from ISO string.
 */
function formatTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', hour12: true });
}

/**
 * Get the date key (YYYY-MM-DD) from a date string.
 */
function getDateKey(dateStr) {
    // Handle date-only strings (all-day events)
    if (dateStr.length === 10) {
        return dateStr;
    }
    const date = new Date(dateStr);
    return date.toISOString().split('T')[0];
}

/**
 * Group events by date.
 */
function groupEventsByDate(events) {
    const groups = {};
    
    for (const event of events) {
        const dateKey = getDateKey(event.start);
        if (!groups[dateKey]) {
            groups[dateKey] = [];
        }
        groups[dateKey].push(event);
    }
    
    // Sort dates
    const sortedDates = Object.keys(groups).sort();
    
    return sortedDates.map(date => ({
        date,
        label: formatDateHeader(date),
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
    const [events, setEvents] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [lastFetched, setLastFetched] = useState(null);

    const fetchCalendar = async () => {
        try {
            const response = await fetch(`http://${window.location.hostname}:8000/api/kiosk/calendar?days=7`);
            if (!response.ok) {
                // Try to get error details from response
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
            setLastFetched(new Date());
            setError(null);
        } catch (e) {
            console.error('Failed to fetch calendar:', e);
            setError(e.message);
        } finally {
            setLoading(false);
        }
    };

    // Fetch on mount and every hour (use refresh button for immediate updates)
    useEffect(() => {
        fetchCalendar();
        const interval = setInterval(fetchCalendar, 60 * 60 * 1000);
        return () => clearInterval(interval);
    }, []);

    const handleRefresh = () => {
        setLoading(true);
        fetchCalendar();
    };

    const groupedEvents = groupEventsByDate(events);

    return (
        <div className="h-full w-full flex flex-col bg-black relative overflow-hidden font-sans">
            {/* Header */}
            <div className="px-8 pt-8 pb-4 flex items-start justify-between">
                <div>
                    <h1 className="text-3xl font-bold text-white">Calendar</h1>
                    <p className="text-white/50 text-sm mt-1">
                        {lastFetched ? `Updated ${lastFetched.toLocaleTimeString()}` : 'Loading...'}
                    </p>
                </div>
                <button
                    onClick={handleRefresh}
                    disabled={loading}
                    className="p-3 rounded-full bg-white/10 hover:bg-white/20 disabled:opacity-50 transition-colors"
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
                className="flex-1 overflow-y-auto no-scrollbar px-8 pb-20"
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
                                <h2 className={`text-lg font-semibold mb-3 ${
                                    group.label === 'Today' ? 'text-cyan-400' : 'text-white/70'
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
                                            className="bg-white/5 backdrop-blur-sm rounded-xl p-4 border border-white/10"
                                        >
                                            <div className="flex items-start gap-3">
                                                <div className={`w-1 h-full min-h-[24px] ${getCalendarColor(event.calendar_label)} rounded-full`} />
                                                <div className="flex-1 min-w-0">
                                                    <p className="text-white font-medium truncate">{event.summary}</p>
                                                    <div className="flex items-center gap-2 mt-1">
                                                        <p className="text-white/50 text-sm">
                                                            {event.is_all_day ? (
                                                                'All day'
                                                            ) : (
                                                                <>
                                                                    {formatTime(event.start)}
                                                                    {event.end && ` – ${formatTime(event.end)}`}
                                                                </>
                                                            )}
                                                        </p>
                                                        <span className="text-white/30">•</span>
                                                        <p className="text-white/40 text-sm truncate">{event.calendar_label}</p>
                                                    </div>
                                                    {event.location && (
                                                        <p className="text-white/40 text-sm mt-1 truncate flex items-center gap-1">
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
