from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot, QThread
import subprocess
import os
import re
from typing import List, Dict, Callable
import time
from gui.conversion_thread import ConversionThread
from gui.cover_art_transfer import apply_cover_art_to_output # <-- Import cover art logic

class TimeRemainingManager:
    """Calculates and formats the estimated time remaining for a conversion."""
    def __init__(self, total_duration: float):
        self.total_duration = total_duration
        self.start_time = time.time()
        self.last_timestamp = 0.0

    def update_progress(self, current_timestamp: float) -> str:
        """Update progress and return formatted time remaining string."""
        if current_timestamp <= self.last_timestamp or self.total_duration <= 0:
            return "" # Avoid division by zero or stale data

        elapsed_time = time.time() - self.start_time
        # Use the timestamp from ffmpeg's output as progress
        progress = current_timestamp / self.total_duration
        
        if progress > 0:
            total_estimated_time = elapsed_time / progress
            remaining_time = total_estimated_time - elapsed_time
            
            if remaining_time > 0:
                return self.format_time(remaining_time)
        
        return ""

    @staticmethod
    def format_time(seconds: float) -> str:
        """Formats seconds into HH:MM:SS."""
        seconds = int(seconds)
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        return f"{h:02d}:{m:02d}:{s:02d} remaining"

class BatchConversionManager(QObject):
    """Manages the batch conversion of multiple files."""
    log_message = pyqtSignal(str)
    batch_finished = pyqtSignal(str)
    file_progress = pyqtSignal(int)
    batch_progress = pyqtSignal(int, int, str) # current_file_num, total_files, filename
    time_remaining_updated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._file_queue = []
        self._output_directory = ""
        self._build_command_fn = None
        self._get_duration_fn = None
        self._get_output_format_fn = None
        self._preserve_cover_art_fn = None # <-- Add callback for cover art checkbox
        self._current_conversion_thread = None
        self._is_running = False
        self._is_cancelled = False
        self._current_file_index = 0
        self._success_count = 0
        self._fail_count = 0
        self.current_process = None
        self.is_stopping = False
        self.time_manager = None

    def set_queue(self, file_dicts):
        self._file_queue = list(file_dicts)

    def set_output_directory(self, directory):
        self._output_directory = directory

    def set_command_builder(self, build_command_fn):
        self._build_command_fn = build_command_fn
    
    def set_duration_getter(self, get_duration_fn):
        self._get_duration_fn = get_duration_fn

    def set_output_format_getter(self, get_output_format_fn):
        self._get_output_format_fn = get_output_format_fn

    def set_preserve_cover_art_getter(self, preserve_cover_art_fn):
        self._preserve_cover_art_fn = preserve_cover_art_fn

    def set_two_pass_getter(self, two_pass_fn):
        self._two_pass_fn = two_pass_fn

    @pyqtSlot()
    def start_batch(self):
        if not self._file_queue:
            self.log_message.emit("No files in the queue.")
            self.batch_finished.emit("Batch finished: No files to process.")
            return
        if not self._output_directory:
            self.log_message.emit("Output directory not set.")
            self.batch_finished.emit("Batch finished: Output directory not set.")
            return
        if not self._build_command_fn or not self._get_duration_fn:
            self.log_message.emit("Internal error: Command builder or duration getter not set.")
            self.batch_finished.emit("Batch finished: Internal error.")
            return

        self._is_running = True
        self._is_cancelled = False
        self._current_file_index = 0
        self._success_count = 0
        self._fail_count = 0
        self.log_message.emit(f"Starting batch conversion for {len(self._file_queue)} files.")
        self._start_next_conversion()

    def stop_batch(self):
        self.log_message.emit("Cancellation requested. Finishing current file...")
        self._is_cancelled = True
        # If a conversion is running, its completion will trigger the next step
        # If not, we should manually stop
        if self._current_conversion_thread and self._current_conversion_thread.isRunning():
            self._current_conversion_thread.stop()
        else:
            self._is_running = False
            self.batch_finished.emit("Batch cancelled by user.")

    def _start_next_conversion(self):
        if self._is_cancelled:
            self.log_message.emit("Batch conversion cancelled.")
            self.batch_finished.emit(f"Batch cancelled. Completed: {self._success_count}, Failed: {self._fail_count}.")
            self._is_running = False
            return

        if self._current_file_index >= len(self._file_queue):
            self.log_message.emit("Batch conversion finished.")
            self.batch_finished.emit(f"Batch finished. Completed: {self._success_count}, Failed: {self._fail_count}.")
            self._is_running = False
            return

        input_file_dict = self._file_queue[self._current_file_index]
        input_file = input_file_dict['path']
        base_name = os.path.basename(input_file)
        settings_override = input_file_dict.get('settings', {})
        self.batch_progress.emit(self._current_file_index + 1, len(self._file_queue), base_name)

        try:
            output_file = self._get_output_path(input_file)
            
            # Check if two-pass is enabled
            is_two_pass = self._two_pass_fn and self._two_pass_fn()

            if is_two_pass:
                # --- Two-Pass Encoding ---
                self.log_message.emit("Starting two-pass encoding...")
                
                # --- First Pass ---
                self.log_message.emit("Pass 1 of 2...")
                pass1_cmd = self._build_command_fn(input_file, output_file, settings_override, pass_num=1)
                self.log_message.emit(f"FFmpeg command (pass 1): {' '.join(pass1_cmd)}")
                try:
                    self.current_process = subprocess.Popen(pass1_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except Exception as e:
                    self.log_message.emit(f"Error launching FFmpeg (pass 1): {e}")
                    self._fail_count += 1
                    self._current_file_index += 1
                    self._start_next_conversion()
                    return
                
                for line in iter(self.current_process.stdout.readline, ''):
                    self.log_message.emit(line.strip())
                
                self.current_process.wait()
                self.log_message.emit(f"FFmpeg exited with code {self.current_process.returncode} (pass 1)")
                if self.current_process.returncode != 0:
                    raise Exception("Two-pass encoding failed on pass 1.")
                
                if self.is_stopping:
                    self.log_message.emit("Conversion cancelled during pass 1.")
                    return

                # --- Second Pass ---
                self.log_message.emit("Pass 2 of 2...")
                pass2_cmd = self._build_command_fn(input_file, output_file, settings_override, pass_num=2)
                self.log_message.emit(f"FFmpeg command (pass 2): {' '.join(pass2_cmd)}")
                try:
                    self.current_process = subprocess.Popen(pass2_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except Exception as e:
                    self.log_message.emit(f"Error launching FFmpeg (pass 2): {e}")
                    self._fail_count += 1
                    self._current_file_index += 1
                    self._start_next_conversion()
                    return
            else:
                # --- Single-Pass Encoding ---
                cmd = self._build_command_fn(input_file, output_file, settings_override)
                self.log_message.emit(f"FFmpeg command: {' '.join(cmd)}")
                try:
                    self.current_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                except Exception as e:
                    self.log_message.emit(f"Error launching FFmpeg: {e}")
                    self._fail_count += 1
                    self._current_file_index += 1
                    self._start_next_conversion()
                    return

            duration = self._get_duration_fn(input_file)
            self.time_manager = TimeRemainingManager(duration)

            # Real-time processing of ffmpeg output
            for line in iter(self.current_process.stdout.readline, ''):
                if self.is_stopping:
                    break
                self.log_message.emit(line.strip())
                
                # Update progress bar
                if duration > 0:
                    match = re.search(r"out_time_ms=(\d+)", line)
                    if match:
                        processed_us = int(match.group(1))
                        progress = (processed_us / (duration * 1000000)) * 100
                        self.file_progress.emit(int(progress))
                        
                        # Update time remaining
                        processed_s = processed_us / 1000000
                        time_str = self.time_manager.update_progress(processed_s)
                        if time_str:
                            self.time_remaining_updated.emit(time_str)

            self.current_process.wait()
            self.log_message.emit(f"FFmpeg exited with code {self.current_process.returncode}")
            if self.is_stopping:
                self.log_message.emit(f"Conversion canceled for: {base_name}")
            else:
                self.log_message.emit(f"Successfully converted: {base_name}")
                # Cover art logic
                apply_cover = False
                if self._get_output_format_fn and self._preserve_cover_art_fn:
                    fmt = self._get_output_format_fn().lower()
                    preserve = self._preserve_cover_art_fn()
                    if fmt == "mp4" and preserve:
                        apply_cover = True
                if apply_cover:
                    try:
                        result = apply_cover_art_to_output(input_file, output_file)
                        if result:
                            self.log_message.emit(f"Cover art applied to {os.path.basename(output_file)}.")
                        else:
                            self.log_message.emit(f"No cover art applied to {os.path.basename(output_file)}.")
                    except Exception as e:
                        self.log_message.emit(f"Error applying cover art: {e}")
                self._success_count += 1
        except Exception as e:
            self.log_message.emit(f"Error processing file {input_file}: {e}")
            self._fail_count += 1

        self._current_file_index += 1
        self._start_next_conversion()

    def _get_output_path(self, input_file):
        """Generates the output path for a given input file."""
        base_name = os.path.splitext(os.path.basename(input_file))[0]
        
        output_format = "mkv" # Default
        if self._get_output_format_fn:
            output_format = self._get_output_format_fn().lower()

        return os.path.join(self._output_directory, f"{base_name}_converted.{output_format}")

    def is_running(self):
        return self._is_running
