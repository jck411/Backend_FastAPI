# Echo Show Kiosk Documentation

Documentation for setting up and maintaining Amazon Echo Show 5 devices (974 MB RAM, 960×480 display) as memory-optimized kiosks running LineageOS with Fully Kiosk Browser.

## Documentation Guide

### For New Device Setup

1. **[ECHO_KIOSK_SETUP.md](ECHO_KIOSK_SETUP.md)** - Initial one-time setup
   - Boot configuration and recovery
   - Port forwarding setup
   - Bloatware removal
   - TTS segmentation settings

2. **[ECHO_DEVICE_SETUP.md](ECHO_DEVICE_SETUP.md)** - Memory optimization (run after setup and each reboot)
   - Kernel parameters and developer options
   - Fully Kiosk Browser configuration
   - Slideshow photo configuration
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
