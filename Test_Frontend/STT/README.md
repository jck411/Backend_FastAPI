# Wake Word Detection (No Access Keys Required)

A working implementation of wake word detection using Porcupine v1.9.0 that **does not require any access keys or API tokens**.

## Features

- ✅ **No access keys needed** - Uses older Porcupine version that works without authentication
- ✅ **"Computer" wake word** - Custom trained keyword included
- ✅ **Cross-platform** - Works on Linux, macOS, Windows
- ✅ **Real-time detection** - Live microphone monitoring
- ✅ **Multiple keywords available** - Built-in and custom options

## Quick Start

1. **Install JavaScript dependencies:**
   ```bash
   npm install
   ```

2. **Run the wake word listener:**
   ```bash
   node wakewords/wakeword_listiner_no_key.cjs
   ```

3. **Say "computer"** and watch for detection messages!

4. **Press Ctrl+C** to stop

**Note:** This wake word detection is implemented in JavaScript/Node.js using Porcupine bindings. No Python required.

## System Requirements

### Linux (Ubuntu/Debian)
```bash
# Install audio system dependencies
sudo apt update && sudo apt install -y sox

# Add user to audio group for microphone access
sudo usermod -a -G audio $USER

# Log out and log back in (or restart) for group changes to take effect
```

### macOS
```bash
# Install Node.js if not already installed
brew install node
```

### Windows
- Install Node.js from [nodejs.org](https://nodejs.org/)
- No additional audio setup typically needed

## Package Versions (Important!)

This setup uses specific versions that work without access keys:

```json
{
  "@picovoice/porcupine-node": "1.9.2",
  "@picovoice/pvrecorder-node": "1.2.8",
  "minimist": "1.2.8"
}
```

**DO NOT** upgrade these packages - newer versions require access keys!

## Files Structure

```
wakewords/
├── computer_linux_v1.9.0.ppn          # Wake word model (compatible with v1.9.0)
└── wakeword_listiner_no_key.cjs       # Main listener script
```

## Usage Options

### Basic Usage
```bash
node wakewords/wakeword_listiner_no_key.cjs
```

### With Custom Settings
```bash
# Adjust sensitivity (0.0 to 1.0, default 0.6)
node wakewords/wakeword_listiner_no_key.cjs --sensitivity 0.8

# Use specific audio device
node wakewords/wakeword_listiner_no_key.cjs --device_index 0

# Use built-in "porcupine" keyword instead
node wakewords/wakeword_listiner_no_key.cjs --use_builtin
```

## Available Built-in Keywords

The Porcupine v1.9.0 engine includes these built-in wake words (no custom files needed):

- "porcupine" (keyword 0)
- "picovoice" (keyword 1)
- "grasshopper" (keyword 2)
- "bumblebee" (keyword 3)
- And others (0-7)

## Adding More Custom Keywords

You can find additional v1.9.0 compatible keyword files in:
```
node_modules/@picovoice/porcupine-node/resources/keyword_files/linux/
```

Available keywords include:
- alexa, americano, blueberry, bumblebee, computer
- grapefruit, grasshopper, hey google, hey siri, jarvis
- ok google, picovoice, porcupine, terminator

Copy any of these to your `wakewords/` directory and update the `DEFAULT_PPN` path in the script.

## Troubleshooting

### "PvRecorder failed to initialize"
- **Linux**: Make sure you're in the `audio` group and have restarted your session
- **All platforms**: Try different device indices (0, 1, 2) or use -1 for default

### "Keyword file belongs to different version"
- Make sure you're using v1.9.0 compatible `.ppn` files
- Don't mix v3.x keyword files with v1.9.0 engine

### Audio Permissions
```bash
# Check if you're in audio group
groups

# Add yourself to audio group (Linux)
sudo usermod -a -G audio $USER

# Then restart your session
```

### No Keyword Detection
- Speak clearly and at normal volume
- Try adjusting sensitivity (0.4-0.8 range)
- Test with built-in keywords first: `--use_builtin`

## Architecture

- **Porcupine Engine v1.9.0**: Core wake word detection (no access keys)
- **PvRecorder v1.2.8**: Audio capture (compatible with modern Linux audio)
- **Custom Models**: Pre-trained v1.9.0 compatible keyword files

## Development Notes

This setup intentionally uses older package versions to avoid the access key requirement introduced in later versions. The specific combination of:

- `@picovoice/porcupine-node@1.9.2` (engine v1.9.0)
- `@picovoice/pvrecorder-node@1.2.8` (modern audio support)

...provides the best compatibility between no-access-key functionality and modern system audio support.

## License

Uses Porcupine by Picovoice. Check their licensing terms for commercial use.
