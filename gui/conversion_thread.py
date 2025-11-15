from PyQt6.QtCore import QThread, pyqtSignal
from typing import List, Optional
import subprocess
import re

class ConversionThread(QThread):
    progress_updated = pyqtSignal(int)
    finished = pyqtSignal(bool, str)
    output_received = pyqtSignal(str) # For debugging

    def __init__(self, command: List[str], input_duration: Optional[float] = None):
        super().__init__()
        self.command = command
        self._should_stop = False
        self.input_duration = input_duration or 0.0

    def run(self):
        try:
            self.output_received.emit(f"Executing command: {' '.join(self.command)}\n")

            proc = None
            try:
                proc = subprocess.Popen(
                    self.command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW',0),
                    bufsize=1,
                )

                # Read output lines and stream them
                while True:
                    if self._should_stop:
                        try:
                            proc.terminate()
                        except Exception:
                            pass
                        break

                    line = proc.stdout.readline()
                    if line == '' and proc.poll() is not None:
                        break
                    if line:
                        self.output_received.emit(line.rstrip())
                        self._parse_progress(line.rstrip())

                # Collect any remaining output
                try:
                    remaining = proc.communicate()[0]
                    if remaining:
                        self.output_received.emit(remaining.strip())
                        self._parse_progress(remaining.strip())
                except Exception:
                    pass

                return_code = proc.returncode if proc is not None else -1
                success = (return_code ==0)
                error_msg = f"FFmpeg returned code: {return_code}" if not success else ""
                self.finished.emit(success, error_msg)
                return
            except Exception as e:
                self.output_received.emit(f"FFmpeg runner error: {e}")
                try:
                    if proc:
                        proc.kill()
                except Exception:
                    pass
                self.finished.emit(False, f"Runner exception: {e}")
                return
        except Exception as e:
            error_msg = f"Error during conversion: {str(e)}"
            self.output_received.emit(error_msg)
            self.finished.emit(False, error_msg)

    def stop(self):
        self._should_stop = True

    def _parse_progress(self, output: str):
        """Parse FFmpeg output for progress and emit percent complete."""
        if self.input_duration and self.input_duration > 0:
            # Key=value progress lines
            if '=' in output and not output.startswith(' '):
                parts = output.strip().split('=', 1)
                if len(parts) == 2:
                    key, val = parts[0].strip(), parts[1].strip()
                    if key == 'out_time_ms' and val.isdigit():
                        micro = int(val)
                        seconds = micro / 1_000_000.0
                        raw_pct = (seconds / self.input_duration) * 100.0
                        pct = 99 if raw_pct >= 99.5 else max(0, int(raw_pct))
                        self.progress_updated.emit(pct)
                    elif key == 'out_time' and val:
                        try:
                            time_str = val.strip()
                            if '.' in time_str:
                                t_main, t_frac = time_str.split('.', 1)
                                frac = float('0.' + t_frac)
                            else:
                                t_main = time_str
                                frac = 0.0
                            h, m, s = t_main.split(':')
                            seconds = int(h) * 3600 + int(m) * 60 + int(s) + frac
                            raw_pct = (seconds / self.input_duration) * 100.0
                            pct = 99 if raw_pct >= 99.5 else max(0, int(raw_pct))
                            self.progress_updated.emit(pct)
                        except Exception:
                            pass
                    elif key == 'progress' and val == 'end':
                        self.progress_updated.emit(100)
            # Legacy frame=... time=... lines
            elif output.strip().startswith('frame=') and 'time=' in output:
                try:
                    time_part = output.split('time=')[1].split()[0]
                    if time_part != 'N/A' and time_part.count(':') == 2:
                        h, m, s = time_part.split(':')
                        total_seconds = int(h) * 3600 + int(m) * 60 + float(s)
                        raw_pct = (total_seconds / self.input_duration) * 100.0
                        pct = 99 if raw_pct >= 99.5 else max(0, int(raw_pct))
                        self.progress_updated.emit(pct)
                except Exception:
                    pass
