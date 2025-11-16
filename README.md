# Vion Pulse Video Converter

A powerful and user-friendly video conversion application built with Python and PyQt6, leveraging FFmpeg for high-quality video processing.

## Features

- 🎥 **Batch Processing**: Convert multiple videos at once
- ⚡ **Hardware Acceleration**: Supports NVIDIA, AMD, and Intel hardware acceleration
- 🎨 **Video Settings**:
  - Multiple video codecs (H.264, HEVC, AV1, VP9, etc.)
  - Quality presets and custom bitrate/CRF controls
  - Resolution scaling and aspect ratio adjustments
  - Deinterlacing options
  - Frame rate conversion
- 🔊 **Audio Controls**:
  - Multiple audio tracks support
  - Volume normalization (peak and EBU R128)
  - Audio codec selection
- 🖼️ **Subtitle Support**:
  - Subtitle extraction and burning
  - Multiple subtitle tracks handling
- 🖥️ **Modern UI**:
  - Dark/Light theme support
  - Progress tracking with time remaining
  - Detailed logging
- 🛠️ **Advanced Features**:
  - Two-pass encoding
  - Multi-threading support
  - Custom FFmpeg parameters

## Requirements

- Python 3.8+
- FFmpeg (must be installed and in system PATH)
- PyQt6
- Other dependencies listed in `requirements.txt`

## Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/yourusername/video-converter.git
   cd video-converter
   ```

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Make sure FFmpeg is installed and available in your system PATH.

## Usage

Run the application with:

```bash
python main.py
```

### Basic Workflow

1. Add video files using the "Add Files" button
2. Select output directory
3. Configure your desired video/audio settings
4. Click "Start" to begin conversion

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
