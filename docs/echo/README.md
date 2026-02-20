# Echo Show Kiosk Documentation

Documentation for setting up and maintaining Amazon Echo Show 5 devices (974 MB RAM, 960×480 display) as memory-optimized kiosks running LineageOS with Fully Kiosk Browser.

Kiosks connect directly to the backend on LAN (`https://192.168.1.111:8000/kiosk/`) — no Cloudflare or public internet required. A development mode with ADB reverse port forwarding is available for local testing.

## Documentation Guide

### For New Device Setup

1. **[ECHO_KIOSK_SETUP.md](ECHO_KIOSK_SETUP.md)** - Initial one-time setup
   - Production vs development mode
   - Boot configuration and recovery
   - ADB-over-WiFi setup (production) / port forwarding (dev)
   - Bloatware removal
   - TTS segmentation settings

2. **[ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md)** - Memory optimization (run after setup and each reboot)
   - Kernel parameters and developer options
   - Fully Kiosk Browser configuration
   - Slideshow photo configuration and daily sync cron
   - Monitoring tools and troubleshooting

### For Development

3. **[ALARM_MEMORY_CONSTRAINTS.md](ALARM_MEMORY_CONSTRAINTS.md)** - Building alarm features
   - Component lifecycle and unmounting patterns
   - Memory constraints and failed approaches
   - Backend API integration

4. **[ECHO_MEMORY_NEXT_STEPS.md](ECHO_MEMORY_NEXT_STEPS.md)** - Experimental optimizations
   - Photo resolution tuning
   - WebView cache strategies
   - Future performance improvements

## Related Documentation

- [../DEVELOPMENT_ENVIRONMENT.md](../DEVELOPMENT_ENVIRONMENT.md) - Network setup and frontend deployment
- [../TIME_MANAGEMENT_ARCHITECTURE.md](../TIME_MANAGEMENT_ARCHITECTURE.md) - Timezone and time context
