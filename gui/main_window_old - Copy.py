from PyQt6.QtWidgets import (QMainWindow, QVBoxLayout, QHBoxLayout, QGridLayout, QWidget, QPushButton,
                             QFileDialog, QLabel, QTabWidget, QComboBox, QSpinBox,
                             QCheckBox, QGroupBox, QProgressBar, QMessageBox, QLineEdit, QPlainTextEdit)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
import os
import subprocess
from PyQt6.QtCore import QThread, pyqtSignal

# Add this class before the MainWindow class
class ConversionThread(QThread):
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    output_received = pyqtSignal(str)  # For debugging
    
    def __init__(self, command):
        super().__init__()
        self.command = command
        self.is_running = True
        self.process = None
        
    def run(self):
        try:
            self.output_received.emit(f"Executing command: {' '.join(self.command)}\n")
            
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0),
                bufsize=1
            )
            
            # Read output in real-time
            while True:
                if not self.is_running:
                    self.process.terminate()
                    break
                    
                output = self.process.stdout.readline()
                if output == '' and self.process.poll() is not None:
                    break
                if output:
                    self.output_received.emit(output.strip())
                    
            # Get any remaining output
            remaining_output = self.process.communicate()[0]
            if remaining_output:
                self.output_received.emit(remaining_output.strip())
                
            return_code = self.process.returncode
            success = (return_code ==0)
            error_msg = f"FFmpeg returned code: {return_code}" if not success else ""
            
            self.finished.emit(success, error_msg)
            
        except Exception as e:
            error_msg = f"Error during conversion: {str(e)}"
            self.output_received.emit(error_msg)
            self.finished.emit(False, error_msg)
            
    def stop(self):
        self.is_running = False
        if self.process:
            self.process.terminate()

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Video Transcoder")
        self.setMinimumSize(800,600)
        # Initialize variables
        self.input_file = ""
        self.output_file = ""
        self._last_warnings = [] # store auto-adjust warnings
        self._input_attached_pics = []
        self.setup_ui()
        self.setup_menu()

    def log(self, msg: str):
        """Append a line to the in-GUI log window and also print to console."""
        try:
            if hasattr(self, 'log_view') and self.log_view is not None:
                self.log_view.appendPlainText(msg)
                print(msg, flush=True)
        except Exception:
            pass

    def probe_attached_pictures(self, file_path: str):
        """Return a list of video stream indices that are flagged as attached_pic for the given file."""
        indices = []
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'stream=index,codec_type,disposition,codec_name', '-of', 'json', file_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0))
            import json
            data = json.loads(res.stdout or '{}')
            for s in data.get('streams', []):
                if s.get('codec_type') == 'video':
                    disp = s.get('disposition') or {}
                    if int(disp.get('attached_pic') or 0) == 1:
                        indices.append(int(s.get('index')))
        except Exception as e:
            self.log(f"probe_attached_pictures error: {e}")
        return indices

    def _escape_path_for_subtitles_filter(self, path: str) -> str:
        """Escape a filesystem path for use inside ffmpeg subtitles filter argument.
        - Double backslashes
        - Escape single quotes
        Returned string is intended to be wrapped in single quotes in the filter expression.
        """
        if not path:
            return path
        escaped = path.replace('\\', '\\\\') # \ -> \\
        escaped = escaped.replace("'", r"\'") # ' -> \'
        return escaped

    def get_available_hw_accels(self):
        """Detect available hardware acceleration options"""
        hw_accels = [('Software (CPU)', 'software')]  # Always include software fallback
        
        try:
            # Check for NVIDIA NVENC
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0)
            )
            out = (result.stdout or '') + (result.stderr or '')
            low = out.lower()
            if 'nvenc' in low:
                hw_accels.append(('NVIDIA NVENC', 'nvenc'))
            # Check for Intel Quick Sync
            if ' qsv' in low:
                hw_accels.append(('Intel Quick Sync', 'qsv'))
            # Check for AMD AMF
            if ' amf' in low:
                hw_accels.append(('AMD AMF', 'amf'))
                
        except Exception as e:
            print(f"Error detecting hardware acceleration: {e}")
        
        return hw_accels

    def get_ffmpeg_hw_accel_args(self, hw_accel_name):
        """Get FFmpeg arguments for the selected hardware acceleration (encode) and potential decode accel"""
        hw_accels = dict(self.get_available_hw_accels())
        hw_accel_type = hw_accels.get(hw_accel_name, 'software')
        is_h264 = 'h264' in self.video_codec.currentText().lower()
        if hw_accel_type == 'nvenc':
            return {
                'encoder': 'h264_nvenc' if is_h264 else 'hevc_nvenc',
                'decode_hwaccel': 'cuda', # available hardware decoding
                'extra': ['-preset', 'p4', '-rc', 'vbr']
            }
        elif hw_accel_type == 'qsv':
            return {
                'encoder': 'h264_qsv' if is_h264 else 'hevc_qsv',
                'decode_hwaccel': 'qsv',
                'extra': ['-preset', 'balanced']
            }
        elif hw_accel_type == 'amf':
            return {
                'encoder': 'h264_amf' if is_h264 else 'hevc_amf',
                'decode_hwaccel': 'd3d11va', # Windows DX hardware decode
                'extra': ['-usage', 'transcoding', '-quality', 'speed']
            }
        else: # software
            return {
                'encoder': 'libx264' if is_h264 else 'libx265',
                'decode_hwaccel': None,
                'pix_fmt': 'yuv420p',
                'extra': ['-preset', self.preset.currentText().lower(), '-movflags', '+faststart']
            }
        
    def setup_ui(self):
        """Set up the main UI components"""
        # Main widget and layout
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        
        # Input/Output section
        io_group = QGroupBox("Input / Output")
        io_layout = QVBoxLayout()
        
        # Input file selection
        input_layout = QHBoxLayout()
        self.input_label = QLabel("No file selected")
        input_btn = QPushButton("Select Input File")
        input_btn.clicked.connect(self.select_input_file)
        input_layout.addWidget(QLabel("Input File:"))
        input_layout.addWidget(self.input_label, 1)
        input_layout.addWidget(input_btn)
        
        # Output file selection
        output_layout = QHBoxLayout()
        self.output_label = QLabel("No output file selected")
        output_btn = QPushButton("Select Output File")
        output_btn.clicked.connect(self.select_output_file)
        output_layout.addWidget(QLabel("Output File:"))
        output_layout.addWidget(self.output_label, 1)
        output_layout.addWidget(output_btn)
        
        io_layout.addLayout(input_layout)
        io_layout.addLayout(output_layout)
        io_group.setLayout(io_layout)
        
        # Format selection
        format_group = QGroupBox("Output Format")
        format_layout = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["MP4", "MKV", "AVI", "MOV", "WebM"])
        format_layout.addWidget(QLabel("Format:"))
        format_layout.addWidget(self.format_combo, 1)
        format_group.setLayout(format_layout)
        
        # Tabs
        self.tabs = QTabWidget()
        self.setup_video_tab()
        self.setup_audio_tab()
        self.setup_advanced_tab()
        self.setup_subtitles_tab()
        
        # Progress bar
        self.progress_bar = QProgressBar(); self.progress_bar.setValue(0)
        
        # Control buttons
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self.start_conversion)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel_conversion)
        control_layout.addStretch(); control_layout.addWidget(self.cancel_btn); control_layout.addWidget(self.start_btn)
        
        # Add all to main layout
        layout.addWidget(io_group)
        layout.addWidget(format_group)
        layout.addWidget(self.tabs,1)
        layout.addWidget(self.progress_bar)
        
        # Log panel
        log_group = QGroupBox("Log Output")
        log_layout = QVBoxLayout()
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(5000) # prevent unlimited growth
        log_layout.addWidget(self.log_view)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group,2)

        layout.addLayout(control_layout)
        
        # Connect format change for sensible defaults
        self.format_combo.currentTextChanged.connect(self.handle_format_changed)

    def handle_format_changed(self):
        """Apply sensible default codecs when container changes without overriding deliberate user choices too aggressively."""
        fmt = self.format_combo.currentText().lower()
        v = self.video_codec.currentText().lower()
        a = self.audio_codec.currentText().lower()
        changed = False
        # WebM defaults
        if fmt == 'webm':
            if v not in ['vp9', 'av1']:
                self.video_codec.setCurrentText('VP9'); changed = True
            if a not in ['opus', 'vorbis']:
                # Prefer Opus
                self.audio_codec.setCurrentText('Opus'); changed = True
        elif fmt == 'mp4':
            if v in ['vp9', 'av1']: # discourage exotic combos in MP4
                self.video_codec.setCurrentText('H.264'); changed = True
            if a in ['opus', 'vorbis']:
                self.audio_codec.setCurrentText('AAC'); changed = True
        elif fmt in ['avi', 'mov']:
            if v in ['hevc (hevc)', 'h.265 (hevc)', 'vp9', 'av1', 'h.265', 'hevc', 'av1'] or '265' in v or 'hevc' in v or 'vp9' in v or 'av1' in v:
                # Force safer H.264 for legacy containers
                self.video_codec.setCurrentText('H.264'); changed = True
            # Audio: MP3 okay for AVI, but MOV prefers AAC
            if fmt == 'mov' and a in ['mp3', 'vorbis']: # Opus also uncommon in mov
                self.audio_codec.setCurrentText('AAC'); changed = True
        # Provide subtle notice if auto-adjusted
        if changed:
            self._last_warnings.append(f"Adjusted codecs to match {self.format_combo.currentText()} container requirements.")

    def adjust_and_warn_container_codec(self):
        """Validate container/codec pairings before building command; auto-correct invalid combos and collect warnings."""
        self._last_warnings = []
        fmt = self.format_combo.currentText().lower()
        v = self.video_codec.currentText().lower()
        a = self.audio_codec.currentText().lower()
        # Rules
        if fmt == 'webm':
            if v not in ['vp9', 'av1']:
                self.video_codec.setCurrentText('VP9'); self._last_warnings.append('WebM requires VP9 or AV1 video; switched to VP9.')
            if a not in ['opus', 'vorbis'] or a == 'copy original':
                self.audio_codec.setCurrentText('Opus'); self._last_warnings.append('WebM requires Opus or Vorbis audio; switched to Opus.')
        elif fmt == 'mp4':
            if v in ['vp9', 'av1']:
                self.video_codec.setCurrentText('H.264'); self._last_warnings.append('MP4 typically does not support VP9/AV1 broadly; switched to H.264.')
            if a in ['opus', 'vorbis']:
                self.audio_codec.setCurrentText('AAC'); self._last_warnings.append('MP4 prefers AAC (or MP3); switched to AAC.')
        elif fmt in ['avi', 'mov']:
            if any(c in v for c in ['hevc', '265', 'vp9', 'av1']):
                self.video_codec.setCurrentText('H.264'); self._last_warnings.append(f"{self.format_combo.currentText()} container unsuitable for {self.video_codec.currentText()} chosen; switched to H.264.")
            if fmt == 'mov' and a in ['mp3', 'vorbis']:
                self.audio_codec.setCurrentText('AAC'); self._last_warnings.append('MOV prefers AAC; switched audio to AAC.')
        # MKV no restrictions

    def setup_video_tab(self):
        """Set up the video settings tab with both Frame Rate and Framerate Mode, no Bitrate"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        video_group = QGroupBox("Video Settings")
        grid = QGridLayout()

        # Video codec
        grid.addWidget(QLabel("Video Codec:"),0,0)
        self.video_codec = QComboBox()
        self.video_codec.addItems(["H.264", "H.265 (HEVC)", "VP9", "AV1"])
        grid.addWidget(self.video_codec,0,1)

        # Quality preset
        grid.addWidget(QLabel("Preset:"),1,0)
        self.preset = QComboBox()
        self.preset.addItems(["Ultrafast", "Superfast", "Veryfast", "Faster", "Fast", 
                            "Medium", "Slow", "Slower", "Veryslow"])
        grid.addWidget(self.preset,1,1)

        # Resolution
        grid.addWidget(QLabel("Resolution:"),2,0)
        self.resolution = QComboBox()
        self.resolution.addItems(["Original", "4K (2160p)", "1440p", "1080p", "720p", "480p"])
        grid.addWidget(self.resolution,2,1)

        # Frame Rate
        grid.addWidget(QLabel("Frame Rate:"),3,0)
        self.framerate = QComboBox()
        self.framerate.addItems(["Original", "60", "59.94", "50", "30", "29.97", "25", "24"])
        grid.addWidget(self.framerate,3,1)

        # Framerate mode
        grid.addWidget(QLabel("Framerate Mode:"),4,0)
        self.framerate_mode = QComboBox()
        self.framerate_mode.addItems(["Same as source", "Constant", "Peak (variable)"])
        grid.addWidget(self.framerate_mode,4,1)

        # Deinterlace option
        self.deinterlace_checkbox = QCheckBox("Deinterlace video (bwdif)")
        self.deinterlace_checkbox.setToolTip("Use high-quality bwdif deinterlacing to remove horizontal combing lines from interlaced sources.")
        grid.addWidget(self.deinterlace_checkbox,5,0,1,2)
        # Auto-detect toggle
        self.deinterlace_auto_checkbox = QCheckBox("Auto-detect when needed")
        self.deinterlace_auto_checkbox.setToolTip("Detect interlacing via ffprobe/idet and enable deinterlace only if needed.")
        grid.addWidget(self.deinterlace_auto_checkbox,6,0,1,2)

        video_group.setLayout(grid)
        layout.addWidget(video_group)
        layout.addStretch()

        self.tabs.addTab(tab, "Video")
    
    def setup_audio_tab(self):
        """Set up the audio settings tab with optimized layout"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        audio_group = QGroupBox("Audio Settings")
        grid = QGridLayout()

        # Audio codec
        grid.addWidget(QLabel("Audio Codec:"),0,0)
        self.audio_codec = QComboBox()
        self.audio_codec.addItems(["AAC", "MP3", "Opus", "Vorbis", "Copy Original"])
        grid.addWidget(self.audio_codec,0,1)

        # Audio channels
        grid.addWidget(QLabel("Channels:"),1,0)
        self.channels = QComboBox()
        self.channels.addItems(["Original", "Mono (1.0)", "Stereo (2.0)", "5.1", "7.1"])
        grid.addWidget(self.channels,1,1)

        # Audio bitrate
        grid.addWidget(QLabel("Audio Bitrate:"),2,0)
        self.audio_bitrate = QComboBox()
        self.audio_bitrate.addItems(["64k", "96k", "128k", "160k", "192k", "256k", "320k"])
        self.audio_bitrate.setCurrentText("160k")
        grid.addWidget(self.audio_bitrate,2,1)

        # Audio sample rate
        grid.addWidget(QLabel("Sample Rate:"),3,0)
        self.samplerate = QComboBox()
        self.samplerate.addItems(["Original", "44100 Hz", "48000 Hz", "96000 Hz"])
        grid.addWidget(self.samplerate,3,1)

        # Audio tracks selection (for multi-audio inputs)
        grid.addWidget(QLabel("Audio Track(s):"),4,0)
        self.audio_track_combo = QComboBox()
        # Default entries; will be populated after selecting input
        self.audio_track_combo.addItem("Auto (first)", userData='auto')
        self.audio_track_combo.addItem("All tracks", userData='all')
        grid.addWidget(self.audio_track_combo,4,1)

        audio_group.setLayout(grid)
        layout.addWidget(audio_group)
        layout.addStretch()

        self.tabs.addTab(tab, "Audio")
    
    def setup_advanced_tab(self):
        """Set up the advanced settings tab with optimized layout and quality mode"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Hardware Acceleration group
        hw_group = QGroupBox("Hardware Acceleration")
        hw_layout = QHBoxLayout()
        self.hw_accel_combo = QComboBox()
        for name, _ in self.get_available_hw_accels():
            self.hw_accel_combo.addItem(name)
        hw_layout.addWidget(QLabel("Hardware Encoder:"))
        hw_layout.addWidget(self.hw_accel_combo)
        hw_group.setLayout(hw_layout)
        layout.addWidget(hw_group)
        
        # Hardware decode toggle
        self.hw_decode_checkbox = QCheckBox("Use hardware decoding (if available)")
        self.hw_decode_checkbox.setChecked(False)
        layout.addWidget(self.hw_decode_checkbox)
        
        # GPU accelerated scaling toggle
        self.hw_scale_checkbox = QCheckBox("Use GPU-accelerated scaling (if available)")
        self.hw_scale_checkbox.setToolTip("Uses scale_npp (CUDA) or scale_qsv when compatible. Not used with burn-in subtitles or deinterlacing.")
        self.hw_scale_checkbox.setChecked(False)
        layout.addWidget(self.hw_scale_checkbox)

        # Cover art preservation toggle
        self.preserve_cover_art_checkbox = QCheckBox("Preserve cover art / attached pictures")
        self.preserve_cover_art_checkbox.setChecked(True)
        self.preserve_cover_art_checkbox.setToolTip("If unchecked, attached cover art images will be discarded from output container.")
        layout.addWidget(self.preserve_cover_art_checkbox)

        # Advanced Options group
        options_group = QGroupBox("Advanced Options")
        grid = QGridLayout()
        grid.addWidget(QLabel("Quality Mode:"),0,0)
        self.quality_mode = QComboBox(); self.quality_mode.addItems(["Constant Quality (CRF)", "Average Bitrate (kbps)"]); grid.addWidget(self.quality_mode,0,1)
        grid.addWidget(QLabel("CRF (0-51, lower=better quality):"),1,0)
        self.crf = QSpinBox(); self.crf.setRange(0,51); self.crf.setValue(23); grid.addWidget(self.crf,1,1)
        grid.addWidget(QLabel("Video Bitrate (kbps):"),2,0)
        self.adv_bitrate = QSpinBox(); self.adv_bitrate.setRange(100,100000); self.adv_bitrate.setValue(5000); grid.addWidget(self.adv_bitrate,2,1)
        grid.addWidget(QLabel("Threads (0=auto):"),3,0)
        self.threads = QSpinBox(); self.threads.setRange(0,64); self.threads.setValue(0); grid.addWidget(self.threads,3,1)
        grid.addWidget(QLabel("Extra FFmpeg parameters:"),4,0)
        self.extra_params = QLineEdit(); grid.addWidget(self.extra_params,4,1)
        options_group.setLayout(grid)
        layout.addWidget(options_group)

        # Size / Bitrate Estimator
        size_group = QGroupBox("Target Size Estimator")
        size_layout = QGridLayout()
        size_layout.addWidget(QLabel("Desired Output Size (MB):"),0,0)
        self.target_size_mb = QSpinBox(); self.target_size_mb.setRange(10,100000); self.target_size_mb.setValue(1000); size_layout.addWidget(self.target_size_mb,0,1)
        self.estimate_btn = QPushButton("Estimate Video Bitrate")
        size_layout.addWidget(self.estimate_btn,1,0,1,2)
        self.estimate_result_label = QLabel("Suggestion: (press button)")
        size_layout.addWidget(self.estimate_result_label,2,0,1,2)
        size_group.setLayout(size_layout)
        layout.addWidget(size_group)
        layout.addStretch()

        # Connect estimator
        self.estimate_btn.clicked.connect(self.estimate_video_bitrate_from_size)

        self.tabs.addTab(tab, "Advanced")
    
        def update_quality_fields():
            hw_name = self.hw_accel_combo.currentText()
            is_software = hw_name.lower().startswith("software")
            mode = self.quality_mode.currentText()
            # Preset (in Video tab)
            self.preset.setEnabled(is_software)
            # CRF only for software
            self.crf.setEnabled(is_software and mode == "Constant Quality (CRF)")
            # Bitrate only for hardware, or for software+bitrate mode
            self.adv_bitrate.setEnabled((not is_software) or (is_software and mode == "Average Bitrate (kbps)"))
            self.estimate_btn.setEnabled(mode == "Average Bitrate (kbps)")
            self.target_size_mb.setEnabled(mode == "Average Bitrate (kbps)")
        self.quality_mode.currentTextChanged.connect(update_quality_fields)
        self.hw_accel_combo.currentTextChanged.connect(update_quality_fields)
        update_quality_fields()
    
    def estimate_video_bitrate_from_size(self):
        """Estimate required video bitrate (kbps) to reach target size considering audio bitrate."""
        if not self.input_file or not os.path.exists(self.input_file):
            QMessageBox.warning(self, "No Input", "Select an input file first for duration.")
            return
        duration = self.get_video_duration(self.input_file)
        if duration <=0:
            QMessageBox.warning(self, "Unknown Duration", "Could not determine input duration.")
            return
        target_mb = self.target_size_mb.value()
        total_bits = target_mb *1024 *1024 *8
        total_kbps = total_bits / duration /1000
        # Parse selected audio bitrate numeric value
        audio_bitrate_text = self.audio_bitrate.currentText().lower().replace('k','') if hasattr(self,'audio_bitrate') else '160'
        try:
            audio_kbps = int(audio_bitrate_text)
        except ValueError:
            audio_kbps =160
        # Reserve audio bitrate, leave rest for video
        video_kbps = max(100, int(total_kbps - audio_kbps))
        self.adv_bitrate.setValue(video_kbps)
        self.estimate_result_label.setText(f"Suggestion: Video {video_kbps} kbps (Audio {audio_kbps} kbps, Total ~{int(video_kbps+audio_kbps)} kbps)")
        self.log(f"Estimator set video bitrate to {video_kbps} kbps for target {target_mb} MB over {duration:.2f} s")
    
    def setup_subtitles_tab(self):
        """Set up the subtitles settings tab"""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        subtitle_group = QGroupBox("Subtitle Streams")
        vbox = QVBoxLayout()
        self.subtitle_streams_combo = QComboBox()
        self.subtitle_streams_combo.addItem("No subtitles detected")
        vbox.addWidget(QLabel("Select subtitle stream:"))
        vbox.addWidget(self.subtitle_streams_combo)
        subtitle_group.setLayout(vbox)
        layout.addWidget(subtitle_group)

        # Subtitle handling method
        method_group = QGroupBox("Subtitle Handling")
        method_layout = QVBoxLayout()
        self.subtitle_method_combo = QComboBox()
        self.subtitle_method_combo.addItems(["None", "Copy", "Burn-in", "Convert to SRT"])
        method_layout.addWidget(QLabel("Method:"))
        method_layout.addWidget(self.subtitle_method_combo)
        method_group.setLayout(method_layout)
        layout.addWidget(method_group)
        layout.addStretch()

        self.tabs.addTab(tab, "Subtitles")
    
    def setup_menu(self):
        """Set up the menu bar"""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("&File")
        
        open_action = QAction("&Open...", self)
        open_action.triggered.connect(self.select_input_file)
        file_menu.addAction(open_action)
        
        save_preset_action = QAction("&Save Preset...", self)
        save_preset_action.triggered.connect(self.save_preset)
        file_menu.addAction(save_preset_action)
        
        load_preset_action = QAction("&Load Preset...", self)
        load_preset_action.triggered.connect(self.load_preset)
        file_menu.addAction(load_preset_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("E&xit", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Help menu
        help_menu = menubar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def quick_probe_field_order(self, file_path: str):
        """Quickly probe the first video stream's field_order using ffprobe. Returns a lowercase string or None."""
        try:
            cmd = ['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=field_order','-of','default=noprint_wrappers=1:nokey=1', file_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0))
            val = (res.stdout or '').strip().lower()
            return val if val else None
        except Exception as e:
            self.log(f"quick_probe_field_order error: {e}")
            return None

    def detect_interlacing(self, file_path: str) -> str:
        """Detect whether the source appears interlaced.
        Returns 'interlaced', 'progressive', or 'unknown'. Uses ffprobe field_order then idet as fallback."""
        #1) ffprobe field_order hint
        fo = self.quick_probe_field_order(file_path)
        if fo:
            if fo in {'tt','bb','tb','bt','tff','bff','interlaced'}:
                return 'interlaced'
            if fo == 'progressive':
                return 'progressive'
        #2) Fallback to idet over a sample of frames
        try:
            # Analyze first ~300 frames; idet writes to stderr
            cmd = ['ffmpeg','-hide_banner','-loglevel','info','-nostdin','-i', file_path,
                   '-filter:v','idet','-frames:v','300','-an','-f','null','-']
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0))
            txt = (proc.stderr or '') + (proc.stdout or '')
            import re
            # Prefer multi-frame detection summary if present
            m = re.search(r"Multi frame detection:\s*TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)\s*Undetermined:\s*(\d+)", txt)
            if not m:
                m = re.search(r"Single frame detection:\s*TFF:\s*(\d+)\s*BFF:\s*(\d+)\s*Progressive:\s*(\d+)\s*Undetermined:\s*(\d+)", txt)
            if m:
                tff = int(m.group(1)); bff = int(m.group(2)); prog = int(m.group(3))
                interlaced_hits = tff + bff
                # Heuristic: interlaced if interlaced hits dominate or exceed a floor
                if interlaced_hits >= max(30, prog //2):
                    return 'interlaced'
                if prog > interlaced_hits:
                    return 'progressive'
            return 'unknown'
        except Exception as e:
            self.log(f"idet detection error: {e}")
            return 'unknown'

    def select_input_file(self):
        """Open a file dialog to select input video file"""
        file_name, _ = QFileDialog.getOpenFileName(
            self, "Select Video File", "", 
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm *.flv *.wmv *.m4v);;All Files (*)")
            
        if file_name:
            self.input_file = file_name
            self.input_label.setText(os.path.basename(file_name))
            # Log and store attached pictures on input
            self._input_attached_pics = self.probe_attached_pictures(file_name)
            if self._input_attached_pics:
                self.log(f"Input cover art streams detected (global stream indexes): {self._input_attached_pics}")
            else:
                self.log("Input cover art streams detected: none")
            
            # Quick field_order hint
            fo = self.quick_probe_field_order(file_name)
            if fo:
                hint = 'interlaced' if fo not in ['progressive','unknown'] else 'progressive'
                self.log(f"ffprobe field_order: {fo} (hint: {hint})")
            
            # Auto-set output filename
            if not self.output_file:
                base_name = os.path.splitext(file_name)[0]
                output_ext = self.format_combo.currentText().lower()
                self.output_file = f"{base_name}_converted.{output_ext}"
                self.output_label.setText(os.path.basename(self.output_file))
            
            # Update subtitle streams
            subtitle_streams = self.get_subtitle_streams(file_name)
            self.subtitle_streams_combo.clear()
            if subtitle_streams:
                for s in subtitle_streams:
                    self.subtitle_streams_combo.addItem(s)
            else:
                self.subtitle_streams_combo.addItem("No subtitles detected")

            # Update audio tracks list
            audio_streams = self.get_audio_streams(file_name)
            self.audio_track_combo.clear()
            self.audio_track_combo.addItem("Auto (first)", userData='auto')
            self.audio_track_combo.addItem("All tracks", userData='all')
            if audio_streams:
                for a in audio_streams:
                    pos = a.get('pos',0)
                    lang = a.get('lang', 'und')
                    desc = f"Track {pos} ({lang})"
                    self.audio_track_combo.addItem(desc, userData=pos)
            else:
                # No audio streams; keep defaults
                pass

    def select_output_file(self):
        """Open a file dialog to select output video file"""
        if not self.input_file:
            QMessageBox.warning(self, "No Input File", "Please select an input file first.")
            return
            
        default_dir = os.path.dirname(self.input_file) if self.input_file else ""
        base_name = os.path.splitext(os.path.basename(self.input_file))[0] if self.input_file else "output"
        default_name = f"{base_name}_converted.{self.format_combo.currentText().lower()}"
        
        file_name, _ = QFileDialog.getSaveFileName(
            self, "Save Video As", 
            os.path.join(default_dir, default_name),
            f"{self.format_combo.currentText()} (*.{self.format_combo.currentText().lower()});;All Files (*)")
            
        if file_name:
            self.output_file = file_name
            self.output_label.setText(os.path.basename(file_name))
    
    def save_preset(self):
        """Save current settings as a preset"""
        # TODO: Implement preset saving
        QMessageBox.information(self, "Save Preset", "Preset saving will be implemented in a future version.")
    
    def load_preset(self):
        """Load settings from a preset"""
        # TODO: Implement preset loading
        QMessageBox.information(self, "Load Preset", "Preset loading will be implemented in a future version.")
    
    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(self, "About Video Transcoder",
                         "<h2>Video Transcoder</h2>"
                         "<p>A simple video transcoding application built with Python and FFmpeg.</p>"
                         "<p>Version1.0.0</p>"
                         "<p>©2025 Video Transcoder</p>")
    
    def build_ffmpeg_command(self):
        """Build FFmpeg command from a clean model based on current UI state.
        Returns list[str] or raises Exception on validation issues."""
        if not self.input_file or not os.path.exists(self.input_file):
            raise ValueError("Invalid input file.")
        if not self.output_file:
            raise ValueError("No output file selected.")

        # Probe streams (include disposition for attached_pic detection)
        has_video = False
        has_audio = False
        video_count =0
        audio_count =0
        subtitle_count =0
        video_streams = [] # list of dicts with pos, attached_pic flag
        try:
            probe_cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'stream=index,codec_type,codec_name,disposition',
                '-of', 'json', self.input_file
            ]
            probe_res = subprocess.run(
                probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0)
            )
            import json
            pdata = json.loads(probe_res.stdout or '{}')
            for s in pdata.get('streams', []):
                ctype = s.get('codec_type')
                if ctype == 'video':
                    attached = False
                    disp = s.get('disposition') or {}
                    attached = bool(disp.get('attached_pic'))
                    video_streams.append({'attached_pic': attached})
                    video_count +=1
                elif ctype == 'audio':
                    has_audio = True
                    audio_count +=1
                elif ctype == 'subtitle':
                    subtitle_count +=1
            # Determine usable (non-attached) video streams
            usable_video_indices = [i for i, v in enumerate(video_streams) if not v.get('attached_pic')]
            if usable_video_indices:
                has_video = True
                video_map_index = usable_video_indices[0]
            else:
                video_map_index = None
        except Exception:
            # Fallback: map first video stream if present under naive assumption
            video_map_index =0
            has_video = True # let ffmpeg decide; may error if only attached_pic
        # Gather subtitle meta (already populated when selecting file)
        subtitle_method = self.subtitle_method_combo.currentText()
        subtitle_index = self.subtitle_streams_combo.currentIndex()
        subtitle_stream_type = None
        if subtitle_method == 'Burn-in' and hasattr(self, '_subtitle_meta') and 0 <= subtitle_index < len(self._subtitle_meta):
            subtitle_stream_type = (self._subtitle_meta[subtitle_index].get('codec_name') or '').lower()

        # Hardware acceleration args
        hw_accel_args = self.get_ffmpeg_hw_accel_args(self.hw_accel_combo.currentText())

        # Container constraints
        output_ext = os.path.splitext(self.output_file)[1].lower()
        video_sel = self.video_codec.currentText().lower()
        forced_audio_codec = None
        if output_ext == '.webm':
            if 'av1' in video_sel:
                hw_accel_args['encoder'] = 'libaom-av1'
            elif 'vp9' in video_sel:
                hw_accel_args['encoder'] = 'libvpx-vp9'
            else:
                hw_accel_args['encoder'] = 'libvpx-vp9'
            ac_ui = self.audio_codec.currentText().lower()
            forced_audio_codec = 'libvorbis' if 'vorbis' in ac_ui else 'libopus'
        elif output_ext in ['.avi', '.mov']:
            enc = hw_accel_args.get('encoder', '')
            if any(x in enc for x in ['hevc', 'av1', 'vp9', 'libvpx', 'libaom']):
                if 'nvenc' in enc:
                    hw_accel_args['encoder'] = 'h264_nvenc'
                elif 'qsv' in enc:
                    hw_accel_args['encoder'] = 'h264_qsv'
                elif 'amf' in enc:
                    hw_accel_args['encoder'] = 'h264_amf'
                else:
                    hw_accel_args['encoder'] = 'libx264'

        # Command model sections
        cmd_global = ['ffmpeg', '-y']
        cmd_pre_input = []
        cmd_input = ['-i', self.input_file]
        cmd_filters = []
        cmd_video = []
        cmd_audio = []
        cmd_subtitle = []
        cmd_maps = []
        cmd_output_opts = []

        # Hardware decode (pre-input)
        if self.hw_decode_checkbox.isChecked() and hw_accel_args.get('decode_hwaccel'):
            cmd_pre_input.extend(['-hwaccel', hw_accel_args['decode_hwaccel']])

        # Logging / progress reporting: use -progress for structured output
        cmd_input.extend(['-loglevel', 'warning', '-nostats', '-progress', 'pipe:1'])

        # Subtitle codec classification
        text_sub_codecs = {'subrip', 'ass', 'ssa', 'webvtt'}
        bitmap_sub_codecs = {'hdmv_pgs_subtitle', 'dvd_subtitle', 'xsub', 'dvb_subtitle'}
        burn_in_active = False
        subtitle_fallback = None # 'copy' or 'srt'
        if subtitle_method == 'Burn-in':
            if subtitle_stream_type in text_sub_codecs and has_video:
                burn_in_active = True
            else:
                # Unsupported burn-in (likely bitmap). Fallback: copy if user wants burn-in on bitmap
                subtitle_fallback = 'copy'
        # Deinterlace option (manual or auto)
        deint_active = False
        if has_video:
            if self.deinterlace_checkbox.isChecked():
                deint_active = True
            elif getattr(self, 'deinterlace_auto_checkbox', None) and self.deinterlace_auto_checkbox.isChecked():
                det = self.detect_interlacing(self.input_file)
                self.log(f"Auto interlace detection: {det}")
                deint_active = (det == 'interlaced')
        if deint_active:
            # High-quality CPU deinterlacer; kept first so it runs before scaling/subtitles
            cmd_filters.append('bwdif=0:-1:0')
        # Filters: burn-in + scaling
        res_sel = self.resolution.currentText().lower()
        res_map = {
            '4k (2160p)':2160,
            '1440p':1440,
            '1080p':1080,
            '720p':720,
            '480p':480,
        }
        if burn_in_active:
            sub_path = self._escape_path_for_subtitles_filter(self.input_file)
            cmd_filters.append(f"subtitles='{sub_path}':si={subtitle_index}")
        if res_sel in res_map and has_video:
            target_h = res_map[res_sel]
            enc_name = hw_accel_args.get('encoder', '')
            # Disable GPU scaling when burning subtitles or deinterlacing to avoid filter graph incompatibilities
            if self.hw_scale_checkbox.isChecked() and not burn_in_active and not deint_active:
                if 'nvenc' in enc_name:
                    cmd_filters.append(f'scale_npp=-2:{target_h}')
                elif 'qsv' in enc_name and self.hw_decode_checkbox.isChecked() and hw_accel_args.get('decode_hwaccel') == 'qsv':
                    cmd_filters.append(f'scale_qsv=w=-2:h={target_h}')
                else:
                    cmd_filters.append(f'scale=-2:{target_h}')
            else:
                cmd_filters.append(f'scale=-2:{target_h}')
        if cmd_filters:
            cmd_filters = ['-vf', ','.join(cmd_filters)]

        # Determine attached picture video stream indices (relative among video streams)
        attached_pic_indices = [i for i, v in enumerate(video_streams) if v.get('attached_pic')]
        # Respect user preference for cover art preservation
        if not getattr(self, 'preserve_cover_art_checkbox', None) or not self.preserve_cover_art_checkbox.isChecked():
            attached_pic_indices = []

        only_cover_art = (video_map_index is None and attached_pic_indices and not has_video)

        # Build mapped video list in output order: primary video first (if any), then attached pictures
        mapped_video_inputs = [] # list of tuples: ('video'|'cover', input_index)
        if has_video and video_map_index is not None:
            mapped_video_inputs.append(('video', video_map_index))
        # For MP4 output, skip mapping cover art streams here (handled by transfer script)
        if output_ext not in ['.mp4']:
            if attached_pic_indices:
                for idx in attached_pic_indices:
                    mapped_video_inputs.append(('cover', idx))
            elif only_cover_art:
                for idx in attached_pic_indices:
                    mapped_video_inputs.append(('cover', idx))
        # Treat as having video for mapping purposes below
        has_video = True

        # Video codec section (apply per output index based on mapped_video_inputs)
        if mapped_video_inputs:
            # Primary encoder options target out_v_index0 when first is real video
            for out_v_index, (kind, _) in enumerate(mapped_video_inputs):
                if kind == 'video':
                    # Encoder and common options
                    cmd_video.extend([f'-c:v:{out_v_index}', hw_accel_args['encoder']])
                    if 'pix_fmt' in hw_accel_args:
                        # pix_fmt is safe to set generally; stream-specifier for clarity
                        cmd_video.extend(['-pix_fmt', hw_accel_args['pix_fmt']])
                    cmd_video.extend(hw_accel_args.get('extra', []))
                else:
                    # For MP4 output, skip cover art mapping here
                    if output_ext not in ['.mp4']:
                        cmd_video.extend([f'-c:v:{out_v_index}', 'copy'])
                        cmd_output_opts.extend([f'-disposition:v:{out_v_index}', 'attached_pic'])

        # Quality and frame rate only for primary encoded stream when present and not cover-only
        mode = self.quality_mode.currentText()
        is_software = self.hw_accel_combo.currentText().lower().startswith('software')
        if mapped_video_inputs and mapped_video_inputs[0][0] == 'video':
            if mode == 'Constant Quality (CRF)' and is_software:
                cmd_video.extend(['-crf:v:0', str(self.crf.value())])
            elif mode == 'Average Bitrate (kbps)':
                cmd_video.extend(['-b:v:0', f"{self.adv_bitrate.value()}k"])
            if self.framerate_mode.currentText() == 'Constant' and self.framerate.currentText() != 'Original':
                cmd_video.extend(['-r:v:0', self.framerate.currentText()])

        # Maps: map primary/attached from input0, then optional external cover from input1
        if mapped_video_inputs:
            for _, src_idx in mapped_video_inputs:
                cmd_maps.extend(['-map', f'0:v:{src_idx}'])
        # no extra_cover_input_index logic

        if has_audio and audio_count >0:
            audio_sel = self.audio_track_combo.currentData()
            if audio_sel == 'all':
                for pos in range(audio_count):
                    cmd_maps.extend(['-map', f'0:a:{pos}'])
            elif isinstance(audio_sel, int) and 0 <= audio_sel < audio_count:
                cmd_maps.extend(['-map', f'0:a:{audio_sel}'])
            else:
                cmd_maps.extend(['-map', '0:a:0'])

        # Subtitle mapping (Copy / Convert) and fallback for unsupported burn-in)
        if subtitle_count >0 and hasattr(self, '_subtitle_meta'):
            if subtitle_method in ['Copy', 'Convert to SRT']:
                if 0 <= subtitle_index < subtitle_count:
                    st_codec = (self._subtitle_meta[subtitle_index].get('codec_name') or '').lower()
                    if subtitle_method == 'Copy':
                        cmd_subtitle.extend(['-map', f'0:s:{subtitle_index}', '-c:s', 'copy'])
                    elif subtitle_method == 'Convert to SRT' and st_codec in text_sub_codecs:
                        cmd_subtitle.extend(['-map', f'0:s:{subtitle_index}', '-c:s', 'srt'])
            elif subtitle_method == 'Burn-in' and subtitle_fallback:
                if 0 <= subtitle_index < subtitle_count:
                    cmd_subtitle.extend(['-map', f'0:s:{subtitle_index}', '-c:s', subtitle_fallback])

        # Threads
        if self.threads.value() >0:
            cmd_output_opts.extend(['-threads', str(self.threads.value())])

        # Ensure faststart for MP4/MOV to help with thumbnails/streaming
        if output_ext in ['.mp4', '.mov'] and '+faststart' not in ' '.join(cmd_output_opts):
            cmd_output_opts.extend(['-movflags', '+faststart'])

        # Copy global metadata (helps retain cover art and tags)
        if '-map_metadata' not in cmd_output_opts:
            cmd_output_opts.extend(['-map_metadata', '0'])
            self.log('Adding -map_metadata0 to preserve tags and cover art')

        # User extra params
        extra = self.extra_params.text().strip()
        if extra:
            cmd_output_opts.extend(extra.split())

        final_cmd = (
            cmd_global +
            cmd_pre_input +
            cmd_input +
            cmd_filters +
            cmd_video +
            cmd_audio +
            cmd_maps +
            cmd_subtitle +
            cmd_output_opts +
            [self.output_file]
        )
        return final_cmd

    def start_conversion(self):
        """Start the video conversion process"""
        try:
            # Check ffmpeg availability early
            try:
                subprocess.run(['ffmpeg','-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except FileNotFoundError:
                QMessageBox.critical(self, "FFmpeg Not Found", "FFmpeg is not installed or not in PATH.")
                return

            # Ensure output directory writable
            if not self.output_file:
                QMessageBox.critical(self, "Error", "Please select an output file.")
                return
            out_dir = os.path.dirname(self.output_file)
            if out_dir and not os.path.exists(out_dir):
                os.makedirs(out_dir, exist_ok=True)
            if out_dir and not os.access(out_dir, os.W_OK):
                QMessageBox.critical(self, "Permission Denied", f"Cannot write to: {out_dir}")
                return

            # Apply container validation + warnings before building command
            self.adjust_and_warn_container_codec()
            cmd = self.build_ffmpeg_command()
        except Exception as e:
            QMessageBox.critical(self, "Error Building Command", f"Failed to prepare conversion command:\n{e}")
            self.log(f"Error building command: {e}")
            return
        # Inform user of auto-adjustments
        if self._last_warnings:
            warn_text = "\n".join(self._last_warnings)
            QMessageBox.information(self, "Adjusted Settings", warn_text)
            self.log("Adjustments applied:\n" + warn_text)
        # Launch conversion
        self.progress_bar.setValue(0)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.log("Starting conversion...")
        self.conversion_thread = ConversionThread(cmd)
        self.conversion_thread.finished.connect(self.conversion_finished)
        self.conversion_thread.output_received.connect(self.handle_ffmpeg_output)
        self.conversion_thread.start()
        import time
        time.sleep(0.1)
        if not self.conversion_thread.isRunning():
            self.progress_bar.setValue(0)
            QMessageBox.critical(self, "Conversion Error", "Failed to start conversion.")
            self.log("Failed to start conversion thread.")
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            return
        
    def handle_ffmpeg_output(self, output):
        """Handle FFmpeg output for debugging and progress (now using -progress key=value lines)"""
        try:
            self.log(output)
            # Initialize duration if absent
            if not hasattr(self, '_input_duration'):
                self._input_duration = self.get_video_duration(self.input_file)

            # Parse progress key=value lines
            if '=' in output and not output.startswith(' '):
                parts = output.strip().split('=',1)
                if len(parts) ==2:
                    key, val = parts[0].strip(), parts[1].strip()
                    if key == 'out_time_ms' and val.isdigit() and self._input_duration >0:
                        # out_time_ms is in microseconds per ffmpeg progress documentation
                        micro = int(val)
                        seconds = micro /1_000_000.0
                        pct = int(min((seconds / self._input_duration) *100,99))
                        self.progress_bar.setValue(pct)
                    elif key == 'out_time' and self._input_duration >0 and val:
                        # Format HH:MM:SS.microseconds
                        try:
                            time_part = val.split('.')[0] # discard microseconds for simplicity
                            h, m, s = time_part.split(':')
                            seconds = int(h) *3600 + int(m) *60 + int(s)
                            pct = int(min((seconds / self._input_duration) *100,99))
                            self.progress_bar.setValue(pct)
                        except Exception:
                            pass
                    elif key == 'progress' and val == 'end':
                        # Mark completion
                        self.progress_bar.setValue(100)
            # Fallback legacy parsing (if progress flags not used for some reason)
            elif output.strip().startswith('frame=') and 'time=' in output:
                try:
                    time_part = output.split('time=')[1].split()[0]
                    if time_part != 'N/A' and time_part.count(':') ==2:
                        h, m, s = time_part.split(':')
                        total_seconds = int(h) *3600 + int(m) *60 + float(s)
                        if self._input_duration >0:
                            progress = min(int((total_seconds / self._input_duration) *100),99)
                            self.progress_bar.setValue(progress)
                except Exception:
                    pass

            # Basic error detection
            if any(err in output.lower() for err in ['error', 'failed', 'invalid', 'not found']):
                self.log("Potential ffmpeg error detected: " + output)
        except Exception as e:
            self.log(f"Error in handle_ffmpeg_output: {e}")

    def get_video_duration(self, file_path):
        """Get video duration in seconds using FFprobe"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0))
            if result.returncode ==0:
                return float(result.stdout.strip())
        except Exception as e:
            print(f"Error getting video duration: {e}", flush=True)
        return 0  # Return 0 if duration can't be determined
    
    def get_subtitle_streams(self, file_path):
        """Get subtitle streams from a video file using ffprobe"""
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 's', '-show_entries', 'stream=index,codec_name:stream_tags=language', '-of', 'json', file_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0))
            import json
            data = json.loads(result.stdout)
            streams = data.get('streams', [])
            subtitle_list = []
            # Store meta aligned with combo order
            self._subtitle_meta = []
            for stream in streams:
                idx = stream.get('index')
                codec = (stream.get('codec_name') or '').lower()
                lang = stream.get('tags', {}).get('language', 'und')
                subtitle_list.append(f"Stream {idx} ({lang})")
                self._subtitle_meta.append({'index': idx, 'codec_name': codec})
            return subtitle_list
        except Exception as e:
            print(f"Error getting subtitle streams: {e}", flush=True)
            # Ensure meta exists to avoid attribute errors
            self._subtitle_meta = []
        return []

    def get_audio_streams(self, file_path):
        """Get audio streams with order position and language"""
        meta = []
        try:
            cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries', 'stream=index:stream_tags=language', '-of', 'json', file_path]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0))
            import json
            data = json.loads(result.stdout or '{}')
            streams = data.get('streams', [])
            for pos, s in enumerate(streams):
                idx = s.get('index')
                lang = (s.get('tags', {}) or {}).get('language', 'und')
                meta.append({'pos': pos, 'index': idx, 'lang': lang})
        except Exception as e:
            print(f"Error getting audio streams: {e}", flush=True)
        self._audio_meta = meta
        return meta

    def conversion_finished(self, success, error_msg):
        """Handle conversion completion"""
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
    
        if success and os.path.exists(self.output_file):
            output_size = os.path.getsize(self.output_file)
            if output_size > 0:
                self.progress_bar.setValue(100)
                # Verify cover art presence in output
                out_attached = self.probe_attached_pictures(self.output_file)
                if out_attached:
                    self.log(f"Output cover art streams present: {out_attached}")
                else:
                    self.log("Output cover art not detected in container.")
                # Log full stream list of output for debugging
                try:
                    probe_cmd = ['ffprobe','-v','error','-show_entries','stream=index,codec_type,codec_name,disposition','-of','json', self.output_file]
                    pr = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                    self.log('Output ffprobe stream summary:')
                    self.log(pr.stdout.strip()[:4000])
                except Exception as e:
                    self.log(f"Failed to probe output streams: {e}")

                # --- Cover Art Application Integration ---
                try:
                    from gui.cover_art_transfer import apply_cover_art_to_output
                    cover_applied = apply_cover_art_to_output(self.input_file, self.output_file)
                    if cover_applied:
                        self.log("Cover art reapplied to output file.")
                    else:
                        self.log("No cover art found to apply, or cover art application failed.")
                except Exception as e:
                    self.log(f"Cover art application error: {e}")
                # --- End Cover Art Application Integration ---

                QMessageBox.information(self, "Success",
                    f"Video conversion completed successfully!\n\n"
                    f"Output file: {self.output_file}\n"
                    f"Size: {output_size / (1024*1024):.2f} MB")
                return
        
        # If we get here, something went wrong
        self.progress_bar.setValue(0)
        self.log(f"Conversion failed. {error_msg}")
        error_details = ["Conversion failed!", ""]
        if error_msg:
            error_details.append(f"Error: {error_msg}")
        if os.path.exists(self.output_file):
            try:
                os.remove(self.output_file)
                self.log("Partial output file removed.")
            except Exception:
                self.log("Failed to remove partial output file.")
    
        QMessageBox.critical(self, "Error", "\n".join(error_details))
        
    def cancel_conversion(self):
        """Cancel the ongoing conversion"""
        if hasattr(self, 'conversion_thread') and self.conversion_thread.isRunning():
            self.log("Cancel requested; stopping conversion thread...")
            self.conversion_thread.stop()
            self.conversion_thread.wait()
            self.progress_bar.setValue(0)
            self.start_btn.setEnabled(True)
            self.cancel_btn.setEnabled(False)
            self.log("Conversion canceled.")

    def closeEvent(self, event):
        """Handle window close event - ensure any active conversion is stopped gracefully"""
        try:
            if hasattr(self, 'conversion_thread') and self.conversion_thread.isRunning():
                self.log("Graceful shutdown: stopping active conversion...")
                self.conversion_thread.stop()
                self.conversion_thread.wait(3000)
        except Exception:
            pass
        event.accept()
