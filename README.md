![Vion Pulse Splash](https://cdn.nostrcheck.me/46025249f65d47dddb0f17d93eb8b0a32d97fe3189c6684bbd33136a0a7e0424/4d688e75d51a67328c0945f0851d30ec1f8692f874aa3caaf12895392a1fe236.webp)

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

## Launch

Run the application with:

```bash
python main.py
```

---

## Quick start (2 minutes)

1) Add input files
- Click “Add Files” (left panel) or drag & drop videos into the window.
- Optional: Use the “Disc / ISO Import” tab to scan a folder or ISO and add found media.

2) Choose output folder
- Click “Select Output Directory”, confirm a writable folder.

3) Pick a container and basic settings
- “Output Format” (MP4/MKV/…)
- “Video” tab: choose codec (H.264/HEVC/AV1/VP9), preset speed, resolution/framerate.
- “Audio” tab: choose codec/bitrate, track selection, optional normalization.

4) Optional preview
- On the right, click “Update Preview” to see how output will look with your current settings.

5) Start
- Click “Start”. Progress, time remaining, and logs are displayed.

---

## UI tour and where features live

Left panel (main workflow)
- Input / Output
 - Input list: add/remove/clear files; per‑file settings can be saved with “Save Settings for Selected”.
 - Output Directory: shows the currently selected folder.
 - File info: duration, size, bitrate, resolution, codec (auto‑probed).
- Output Format
 - Container selector (MP4, MKV, AVI, MOV, WebM, …). Sensible defaults are applied when you change formats.
- Settings tabs
 - Video
 - Video Codec: H.264, H.265 (HEVC), VP9, AV1
 - Conversion Speed (preset): Ultrafast … Veryslow (speed vs quality)
 - Resolution: Original or common targets
 - Frame Rate: Original or specific values (and Framerate Mode: Same as source, Constant, Peak variable)
 - Deinterlace (bwdif) and Auto‑detect toggle
 - Audio
 - Codec (AAC/MP3/Opus/Vorbis/Copy), channels, bitrate, sample rate
 - Track selection: Auto (first) or All tracks
 - Volume slider and Loudnorm (normalization)
 - Advanced (sub‑tabs)
 - Hardware: pick encoder (Software CPU, NVIDIA NVENC, Intel QSV, AMD AMF), optional hardware decode/scale
 - Encoding: Quality Mode (CRF / Average Bitrate / VBR), CRF value, bitrate fields, Two‑Pass toggle, Threads, Extra FFmpeg params
 - Size & Misc: Desired output size estimator (suggests video bitrate) and “Preserve cover art / attached pictures”
 - Subtitles
 - Lists detected subtitle streams. For each stream you can include it and choose a method: Copy, Burn‑in, Convert to SRT.

Right panel (tools and diagnostics)
- Output Preview (top): click “Update Preview” to render a quick still reflecting crop/scale/deinterlace settings.
- Tool tabs
 - Cropping: Auto/Custom cropping to remove black bars; detected values appear and can be edited.
 - Scaling: Resolution limit (Original/Custom/4K/1440p/1080p/720p/480p), anamorphic options, allow upscaling.
 - Audio Analysis: Generate waveform and EBU R128 stats; optional EBU normalization target.
- Log Output (bottom): detailed FFmpeg/log messages.

Top tabs
- Video Converter: main workflow shown above.
- Disc / ISO Import: scan a folder or ISO for media, optionally extract to a destination, then add to queue.

---

## What features do

- Video codec & preset
 - Preset controls speed/quality trade‑off. Faster = lower quality/efficiency, slower = better quality/efficiency.
- Resolution/Framerate
 - Downscale to a target height or keep Original; set constant framerate if needed (e.g.,30 fps for compatibility).
- Deinterlacing
 - Uses high‑quality `bwdif`. Enable manually or let the app auto‑detect interlaced content.
- Quality modes
 - Constant Quality (CRF): best for software encoders (`libx264`/`libx265`). Lower CRF = higher quality (larger files). Typical H.264 CRF18–23.
 - Average Bitrate (kbps): target average bitrate.
 - Variable Bitrate (VBR): target/max/min control.
- Two‑Pass
 - Improves quality predictability for bitrate‑based modes (ABR/VBR). Slower; not needed for CRF.
- Audio
 - Choose codec/bitrate/channels; normalize with `loudnorm` or basic volume; select tracks (auto/all).
- Subtitles
 - Copy: remuxes existing subtitles when container supports it.
 - Convert to SRT: re‑encodes text subs to SRT (or `mov_text` for MP4 automatically).
 - Burn‑in: renders text onto video; slows encode; not removable.
- Preserve cover art
 - When enabled and using MP4, tries to apply cover art from the source (or a fallback still) to the output.
- Threads & Extra FFmpeg params
 - Leave Threads =0 for auto. Extra params are appended as‑is for advanced users.

---

## Greyed‑out and auto‑adjust behaviors

- CRF controls are disabled when a hardware encoder (NVENC/QSV/AMF) is selected (most HW encoders don’t use CRF).
- Two‑Pass is only enabled for bitrate‑based modes (Average Bitrate or VBR). It’s auto‑unchecked when not applicable.
- When you change container, invalid codec combinations are auto‑corrected and warnings are logged (e.g., MP4 prefers H.264/AAC; WebM requires VP9/AV1 with Opus/Vorbis).
- For MP4, SubRip/SRT subtitles are converted to `mov_text` automatically if you choose Copy/Convert.

---

## Best practices and recipes

Fastest conversion (good quality, hardware accelerated)
- Format: MP4
- Hardware tab: NVIDIA NVENC (or Intel QSV / AMD AMF)
- Video tab: H.264, Preset: Fast/Medium (mapped to HW preset), Resolution: Original, Framerate: Original
- Advanced > Encoding: Quality Mode = VBR or Average Bitrate, Single‑pass (Two‑Pass off)
- Audio: Codec = AAC, keep original bitrate/channels, avoid normalization
- Subtitles: Prefer Copy or none (avoid Burn‑in)

Smallest size with good quality (software x264/x265)
- Hardware = Software (CPU)
- Quality Mode = Constant Quality (CRF)
 - H.264 CRF ~20–23; H.265 CRF ~22–28
- Preset = Slow/Slower for better efficiency (slower)
- Optional downscale (e.g.,1080p →720p) to reduce size

Target a specific size
- Advanced > Size & Misc: set Desired Output Size (MB) and click “Estimate Video Bitrate”.
- Switch to Average Bitrate (kbps) and use the suggested value; consider enabling Two‑Pass for more consistent results.

When to enable deinterlacing
- Only for interlaced sources (broadcast/DVD). Keep “Auto‑detect” on; manual “Deinterlace” forces it for all inputs.

Subtitles guidance
- Burn‑in makes text part of the video (always visible, slows encoding).
- Copy preserves switchable subs when container supports it. For MP4, SRT → `mov_text` automatically.

General tips
- Leave Threads at0 (auto). Avoid unnecessary filters for speed.
- Use “Update Preview” to validate crop/scale/deinterlace before running a long encode.
- Logs may include absolute file paths—redact before sharing publicly.

---

## Disc / ISO Import

- Source: choose a folder or `.iso` and click “Scan Source”.
- ISO: select a destination folder, click “Extract & Add to Queue”.
- The files will be added to the main queue for conversion.

---

## Troubleshooting

- “FFmpeg Not Found”: install FFmpeg and ensure `ffmpeg`/`ffprobe` are on PATH.
- “Permission Denied”: choose a writable output folder.
- No progress/time remaining: ensure input probes succeeded; see logs for errors.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open issues/PRs with clear steps or proposed changes.
