import { useCallback, useEffect, useRef, useState } from 'react';

/** Slideshow settings */
const SLIDESHOW_INTERVAL = 30 * 1000; // 30 seconds between photos
const SLIDESHOW_TRANSITION_DURATION = 1500; // 1.5 second crossfade
const SLIDESHOW_REFRESH_INTERVAL = 60 * 60 * 1000; // Refresh photo list every hour

/**
 * AccuWeather icon mapping to emoji/unicode symbols.
 * Icons 1-44 from AccuWeather API: https://developer.accuweather.com/weather-icons
 * We'll replace these with actual icon images later if desired.
 */
const WEATHER_ICONS = {
    1: '☀️',   // Sunny
    2: '🌤️',   // Mostly Sunny
    3: '⛅',   // Partly Sunny
    4: '⛅',   // Intermittent Clouds
    5: '🌥️',   // Hazy Sunshine
    6: '☁️',   // Mostly Cloudy
    7: '☁️',   // Cloudy
    8: '☁️',   // Dreary (Overcast)
    11: '🌫️',  // Fog
    12: '🌧️',  // Showers
    13: '🌦️',  // Mostly Cloudy w/ Showers
    14: '🌦️',  // Partly Sunny w/ Showers
    15: '⛈️',  // T-Storms
    16: '⛈️',  // Mostly Cloudy w/ T-Storms
    17: '⛈️',  // Partly Sunny w/ T-Storms
    18: '🌧️',  // Rain
    19: '🌨️',  // Flurries
    20: '🌨️',  // Mostly Cloudy w/ Flurries
    21: '🌨️',  // Partly Sunny w/ Flurries
    22: '❄️',  // Snow
    23: '❄️',  // Mostly Cloudy w/ Snow
    24: '🧊',  // Ice
    25: '🌧️',  // Sleet
    26: '🌧️',  // Freezing Rain
    29: '🌧️',  // Rain and Snow
    30: '🌡️',  // Hot
    31: '🥶',  // Cold
    32: '💨',  // Windy
    33: '🌙',  // Clear (night)
    34: '🌙',  // Mostly Clear (night)
    35: '☁️',  // Partly Cloudy (night)
    36: '☁️',  // Intermittent Clouds (night)
    37: '🌫️',  // Hazy Moonlight (night)
    38: '☁️',  // Mostly Cloudy (night)
    39: '🌧️',  // Partly Cloudy w/ Showers (night)
    40: '🌧️',  // Mostly Cloudy w/ Showers (night)
    41: '⛈️',  // Partly Cloudy w/ T-Storms (night)
    42: '⛈️',  // Mostly Cloudy w/ T-Storms (night)
    43: '🌨️',  // Mostly Cloudy w/ Flurries (night)
    44: '❄️',  // Mostly Cloudy w/ Snow (night)
};

/**
 * Get weather icon emoji from AccuWeather icon number
 */
const getWeatherIcon = (iconNumber) => WEATHER_ICONS[iconNumber] || '🌡️';

/** Weather refresh interval: 15 minutes */
const WEATHER_REFRESH_INTERVAL = 15 * 60 * 1000;

/**
 * Analyze hourly forecast to generate a smart rain alert.
 * Returns an object with alert text and severity level.
 * 
 * Uses rain_chance field from AccuWeather API (PrecipitationProbability).
 * This is REAL data from the API, not made up.
 */
const analyzeRainForecast = (hourlyData, threshold = 30) => {
    if (!hourlyData || hourlyData.length === 0) {
        return null;
    }

    // Find all hours with rain chance above threshold
    // API returns rain_chance (from PrecipitationProbability field)
    const rainyHours = hourlyData
        .map((h, idx) => ({ ...h, index: idx }))
        .filter(h => h.rain_chance >= threshold);

    if (rainyHours.length === 0) {
        return {
            type: 'clear',
            text: 'No rain expected next 12 hours',
            icon: '☀️',
            severity: 'low',
        };
    }

    const firstRainyHour = rainyHours[0];
    const maxRainChance = Math.max(...rainyHours.map(h => h.rain_chance));
    
    // Find rain window (consecutive or close hours with rain)
    const firstRainIndex = firstRainyHour.index;
    let lastRainIndex = firstRainIndex;
    
    for (const h of rainyHours) {
        if (h.index <= lastRainIndex + 2) { // Allow 1-hour gaps in rain window
            lastRainIndex = h.index;
        }
    }

    const hoursUntilRain = firstRainIndex;
    const rainDuration = lastRainIndex - firstRainIndex + 1;

    // Determine severity based on max rain chance
    let severity = 'low';
    if (maxRainChance >= 70) severity = 'high';
    else if (maxRainChance >= 50) severity = 'medium';

    // Generate appropriate message
    let text;
    let icon = '🌧️';

    if (hoursUntilRain === 0) {
        // Rain is happening now or very soon
        if (rainDuration > 1) {
            text = `Rain now through ${hourlyData[lastRainIndex].hour}`;
        } else {
            text = `Rain now (${maxRainChance}%)`;
        }
        icon = '⛈️';
    } else if (hoursUntilRain === 1) {
        text = `Rain likely in ~1 hour (${maxRainChance}%)`;
    } else if (hoursUntilRain <= 3) {
        text = `Rain likely around ${firstRainyHour.hour} (${maxRainChance}%)`;
    } else {
        text = `Rain possible at ${firstRainyHour.hour} (${maxRainChance}%)`;
        icon = '🌦️';
    }

    return {
        type: 'rain',
        text,
        icon,
        severity,
        hoursUntilRain,
        maxChance: maxRainChance,
    };
};

/**
 * Clock component designed for Echo Show 5 (960x480) with photo slideshow background.
 * Includes weather display with current conditions, rain alert, and 5-day forecast.
 * 
 * Weather data is fetched from the backend API which proxies AccuWeather.
 * Rain probability values are REAL data from AccuWeather's PrecipitationProbability field.
 * 
 * Layout:
 * - Top-right: Current temperature + rain alert
 * - Bottom-left: Time and date
 * - Bottom-right: 5-day forecast strip
 */
export default function Clock() {
    const [time, setTime] = useState(new Date());
    const [weather, setWeather] = useState(null);
    const [weatherError, setWeatherError] = useState(null);

    // Slideshow state
    const [photos, setPhotos] = useState([]);
    const [currentPhotoIndex, setCurrentPhotoIndex] = useState(0);
    const [isTransitioning, setIsTransitioning] = useState(false);
    const preloadRef = useRef(null);
    const slideshowTimerRef = useRef(null);

    /**
     * Skip to next photo (used for tap-to-skip).
     */
    const skipToNextPhoto = useCallback(() => {
        if (photos.length <= 1 || isTransitioning) return;

        // Clear existing timer to reset the 30s countdown
        if (slideshowTimerRef.current) {
            clearInterval(slideshowTimerRef.current);
        }

        // Preload and transition to next photo
        const nextIndex = (currentPhotoIndex + 1) % photos.length;
        const nextPhoto = photos[nextIndex];
        const img = new Image();
        img.src = `http://${window.location.hostname}:8000/api/slideshow/photo/${nextPhoto}`;
        preloadRef.current = img;

        setIsTransitioning(true);
        setTimeout(() => {
            setCurrentPhotoIndex(nextIndex);
            setIsTransitioning(false);
        }, SLIDESHOW_TRANSITION_DURATION);
    }, [photos, currentPhotoIndex, isTransitioning]);

    /**
     * Fetch slideshow photos from backend API.
     * Returns a shuffled list that's consistent for the day.
     */
    const fetchPhotos = useCallback(async () => {
        try {
            const response = await fetch(
                `http://${window.location.hostname}:8000/api/slideshow/photos?daily_seed=true`
            );
            if (!response.ok) {
                console.warn('Slideshow photos not available');
                return;
            }
            const data = await response.json();
            if (data.photos && data.photos.length > 0) {
                setPhotos(data.photos);
                console.log(`Loaded ${data.photos.length} slideshow photos`);
            }
        } catch (err) {
            console.warn('Failed to fetch slideshow photos:', err);
        }
    }, []);

    // Fetch photos on mount and periodically refresh
    useEffect(() => {
        fetchPhotos();
        const photosTimer = setInterval(fetchPhotos, SLIDESHOW_REFRESH_INTERVAL);
        return () => clearInterval(photosTimer);
    }, [fetchPhotos]);

    // Slideshow rotation (auto-advance every 30 seconds)
    useEffect(() => {
        if (photos.length <= 1) return;

        const rotatePhoto = () => {
            // Preload next image before transition
            const nextIndex = (currentPhotoIndex + 1) % photos.length;
            const nextPhoto = photos[nextIndex];
            const img = new Image();
            img.src = `http://${window.location.hostname}:8000/api/slideshow/photo/${nextPhoto}`;
            preloadRef.current = img;

            // Start transition
            setIsTransitioning(true);

            // After transition completes, update index
            setTimeout(() => {
                setCurrentPhotoIndex(nextIndex);
                setIsTransitioning(false);
            }, SLIDESHOW_TRANSITION_DURATION);
        };

        slideshowTimerRef.current = setInterval(rotatePhoto, SLIDESHOW_INTERVAL);
        return () => {
            if (slideshowTimerRef.current) {
                clearInterval(slideshowTimerRef.current);
            }
        };
    }, [photos, currentPhotoIndex]);

    // Get photo URLs
    const currentPhotoUrl = photos.length > 0
        ? `http://${window.location.hostname}:8000/api/slideshow/photo/${photos[currentPhotoIndex]}`
        : null;
    const nextPhotoIndex = (currentPhotoIndex + 1) % Math.max(photos.length, 1);
    const nextPhotoUrl = photos.length > 1
        ? `http://${window.location.hostname}:8000/api/slideshow/photo/${photos[nextPhotoIndex]}`
        : null;

    /**
     * Fetch weather data from backend API.
     * Backend caches data server-side (15 min default) to respect AccuWeather limits.
     */
    const fetchWeather = useCallback(async () => {
        try {
            const response = await fetch(`http://${window.location.hostname}:8000/api/weather`);
            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(errorData.detail?.detail || errorData.detail || 'Weather unavailable');
            }
            const data = await response.json();
            setWeather(data);
            setWeatherError(null);
            console.log('Weather data updated:', data.fetched_at);
        } catch (err) {
            console.error('Failed to fetch weather:', err);
            setWeatherError(err.message);
            // Don't clear existing weather data on error - keep showing stale data
        }
    }, []);

    // Fetch weather on mount and every 15 minutes
    useEffect(() => {
        fetchWeather();
        const weatherTimer = setInterval(fetchWeather, WEATHER_REFRESH_INTERVAL);
        return () => clearInterval(weatherTimer);
    }, [fetchWeather]);

    // Analyze hourly forecast for rain alerts (uses real API data)
    const rainAlert = weather?.hourly ? analyzeRainForecast(weather.hourly) : null;

    // Clock update every second
    useEffect(() => {
        const timer = setInterval(() => setTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    const formatTime = (date) => {
        const hours = date.getHours();
        const minutes = date.getMinutes();
        const hour12 = hours % 12 || 12;
        const ampm = hours >= 12 ? 'PM' : 'AM';
        const paddedMinutes = minutes.toString().padStart(2, '0');
        return { time: `${hour12}:${paddedMinutes}`, ampm };
    };

    const formatDate = (date) => {
        return date.toLocaleDateString('en-US', {
            weekday: 'long',
            month: 'long',
            day: 'numeric',
        });
    };

    const { time: timeStr, ampm } = formatTime(time);

    // Get severity-based styling for rain alert
    const getAlertStyle = (severity) => {
        switch (severity) {
            case 'high':
                return 'text-blue-300 bg-blue-500/20 border-blue-400/30';
            case 'medium':
                return 'text-blue-200 bg-blue-500/10 border-blue-400/20';
            default:
                return 'text-white/70 bg-white/5 border-white/10';
        }
    };

    return (
        <div 
            className="h-full w-full relative bg-black cursor-pointer"
            onClick={skipToNextPhoto}
        >
            {/* Slideshow background - tap anywhere to skip */}
            {photos.length > 0 ? (
                <>
                    {/* Current photo */}
                    <div
                        className="absolute inset-0 bg-cover bg-center transition-opacity"
                        style={{
                            backgroundImage: `url(${currentPhotoUrl})`,
                            opacity: isTransitioning ? 0 : 1,
                            transitionDuration: `${SLIDESHOW_TRANSITION_DURATION}ms`,
                        }}
                    />
                    {/* Next photo (fades in during transition) */}
                    {nextPhotoUrl && (
                        <div
                            className="absolute inset-0 bg-cover bg-center transition-opacity"
                            style={{
                                backgroundImage: `url(${nextPhotoUrl})`,
                                opacity: isTransitioning ? 1 : 0,
                                transitionDuration: `${SLIDESHOW_TRANSITION_DURATION}ms`,
                            }}
                        />
                    )}
                </>
            ) : (
                /* Fallback gradient when no photos available */
                <div className="absolute inset-0 bg-gradient-to-br from-gray-900 via-gray-800 to-black" />
            )}

            {/* Top gradient overlay for weather legibility */}
            <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-black/50 to-transparent pointer-events-none" />

            {/* Bottom gradient overlay for text legibility */}
            <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-black/80 via-black/40 to-transparent pointer-events-none" />

            {/* Current Weather + Rain Alert - Top Right */}
            <div className="absolute top-4 right-5 z-10 flex items-start gap-4">
                {/* Rain Alert - Smart hourly analysis (uses real PrecipitationProbability from API) */}
                {rainAlert && (
                    <div className={`
                        flex items-center gap-2 px-3 py-1.5 rounded-full
                        border backdrop-blur-sm drop-shadow-lg
                        ${getAlertStyle(rainAlert.severity)}
                    `}>
                        <span className="text-base">{rainAlert.icon}</span>
                        <span className="text-sm font-medium">{rainAlert.text}</span>
                    </div>
                )}

                {/* Current conditions */}
                {weather?.current && (
                    <div className="text-right">
                        <div className="flex items-center justify-end gap-2">
                            <span className="text-4xl drop-shadow-lg">
                                {getWeatherIcon(weather.current.icon)}
                            </span>
                            <span className="text-4xl font-light text-white drop-shadow-lg">
                                {weather.current.temp}°
                            </span>
                        </div>
                        <div className="text-sm text-white/70 mt-0.5 drop-shadow">
                            {weather.current.phrase}
                        </div>
                    </div>
                )}
            </div>

            {/* Clock overlay - Bottom Left */}
            <div className="absolute bottom-5 left-5 z-10">
                {/* Time display */}
                <div className="flex items-baseline gap-2">
                    <span className="text-6xl font-light tracking-tight text-white drop-shadow-lg">
                        {timeStr}
                    </span>
                    <span className="text-xl font-light text-white/80 drop-shadow-lg">
                        {ampm}
                    </span>
                </div>

                {/* Date display */}
                <div className="text-lg font-light text-white/70 tracking-wide mt-1 drop-shadow-lg">
                    {formatDate(time)}
                </div>
            </div>

            {/* 5-Day Forecast Strip - Bottom Right */}
            {weather?.daily && (
                <div className="absolute bottom-5 right-5 z-10">
                    <div className="flex gap-3">
                        {weather.daily.map((day, idx) => (
                            <div key={idx} className="text-center min-w-[44px]">
                                {/* Day name */}
                                <div className="text-[10px] font-medium text-white/60 uppercase tracking-wider drop-shadow">
                                    {day.day}
                                </div>
                                
                                {/* Weather icon */}
                                <div className="text-xl my-0.5 drop-shadow-lg">
                                    {getWeatherIcon(day.icon)}
                                </div>
                                
                                {/* Rain probability - highlighted if > 30% (from API PrecipitationProbability) */}
                                <div className={`text-xs font-medium drop-shadow ${
                                    day.rain_chance > 30 
                                        ? 'text-blue-300' 
                                        : 'text-white/40'
                                }`}>
                                    {day.rain_chance}%
                                </div>
                                
                                {/* High/Low temps */}
                                <div className="text-[10px] text-white/50 drop-shadow">
                                    {day.high}°/{day.low}°
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Weather Error Indicator (subtle, bottom-left corner) */}
            {weatherError && !weather && (
                <div className="absolute top-4 right-5 z-10 text-white/50 text-sm">
                    Weather unavailable
                </div>
            )}
        </div>
    );
}
