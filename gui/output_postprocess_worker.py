from PyQt6.QtCore import QObject, pyqtSignal
import os
import subprocess

class OutputPostProcessWorker(QObject):
    postprocessed = pyqtSignal(bool, str, list) # success, log_text, attached_pics
    error = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, input_file, output_file):
        super().__init__()
        self.input_file = input_file
        self.output_file = output_file
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        logs = []
        attached_pics = []
        try:
            if not self.output_file or not os.path.exists(self.output_file):
                self.error.emit("Output file does not exist for post-processing.")
                self.finished.emit()
                return
            output_size = os.path.getsize(self.output_file)
            if output_size <=0:
                self.error.emit("Output file is empty after conversion.")
                self.finished.emit()
                return
            # Probe cover art presence in output
            try:
                from gui.probe import probe_attached_pictures
                out_attached = probe_attached_pictures(self.output_file, logs.append)
                attached_pics = out_attached or []
                if attached_pics:
                    logs.append(f"Output cover art streams present: {attached_pics}")
                else:
                    logs.append("Output cover art not detected in container.")
            except Exception as e:
                logs.append(f"Output cover art probe error: {e}")
            # Log full stream list of output for debugging
            try:
                probe_cmd = ['ffprobe','-v','error','-show_entries','stream=index,codec_type,codec_name,disposition','-of','json', self.output_file]
                pr = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                logs.append('Output ffprobe stream summary:')
                logs.append(pr.stdout.strip()[:4000])
            except Exception as e:
                logs.append(f"Failed to probe output streams: {e}")
            # Cover Art Application Integration
            try:
                from gui.cover_art_transfer import apply_cover_art_to_output
                cover_applied = apply_cover_art_to_output(self.input_file, self.output_file)
                if cover_applied:
                    logs.append("Cover art reapplied to output file.")
                else:
                    logs.append("No cover art found to apply, or cover art application failed.")
            except Exception as e:
                logs.append(f"Cover art application error: {e}")
            self.postprocessed.emit(True, '\n'.join(logs), attached_pics)
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished.emit()
