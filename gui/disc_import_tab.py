import os
import pycdlib
import shutil
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
                             QFileDialog, QLabel, QComboBox, QGroupBox, QProgressBar, 
                             QPlainTextEdit, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject

class DiscImportWorker(QObject):
    """Worker to scan a directory or ISO for media files in a background thread."""
    finished = pyqtSignal(list, str)  # Emits list of found entries (dicts) and the source type ('dir' or 'iso')
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, source_path, supported_formats):
        super().__init__()
        self._source_path = source_path
        self._supported_formats = [f.lower() for f in supported_formats]
        self._is_running = True

    def run(self):
        """Scan for video files and emit the list."""
        self.log_message.emit(f"Scanning '{self._source_path}' for media files...")
        found_entries = []
        source_type = ''

        try:
            if self._source_path.lower().endswith('.iso'):
                source_type = 'iso'
                found_entries = self._scan_iso()
            elif os.path.isdir(self._source_path):
                source_type = 'dir'
                found_entries = self._scan_directory()
            else:
                self.error.emit("Selected path is not a valid directory or ISO file.")
                return

            if self._is_running:
                self.log_message.emit(f"Scan complete. Found {len(found_entries)} media file(s).")
                self.finished.emit(found_entries, source_type)
            else:
                self.log_message.emit("Scan canceled.")
                self.finished.emit([], '')

        except Exception as e:
            self.error.emit(f"An error occurred during scan: {e}")

    def _scan_directory(self):
        """Walk a directory and find matching files. Returns list[str]."""
        found_files = []
        total_dirs = sum(1 for _ in os.walk(self._source_path)) or 1
        i = 0
        for root, _, files in os.walk(self._source_path):
            if not self._is_running:
                break
            i += 1
            self.progress.emit(int((i / total_dirs) * 100))
            for file in files:
                if not self._is_running:
                    break
                if os.path.splitext(file)[1].lower() in self._supported_formats:
                    full_path = os.path.join(root, file)
                    found_files.append(full_path)
                    self.log_message.emit(f"Found: {full_path}")
        return found_files

    def _scan_iso(self):
        """
        Walk an ISO filesystem and find matching files.
        Try different path namespaces (Rock Ridge, Joliet, ISO-9660) using iso.walk
        and return entries as dicts: {'path_type': <one of 'rr_path','joliet_path','iso_path'>, 'path': '<absolute path>'}
        """
        entries = []
        iso = pycdlib.PyCdlib()
        try:
            iso.open(self._source_path)
        except Exception as e:
            self.error.emit(f"Failed to open ISO file: {e}")
            return []

        try:
            path_types = [('rr_path', 'Rock Ridge'), ('joliet_path', 'Joliet'), ('iso_path', 'ISO-9660')]
            for key, label in path_types:
                if not self._is_running:
                    break
                self.log_message.emit(f"Attempting walk using {label} namespace...")
                try:
                    found = []
                    for root, _, files in iso.walk(**{key: '/'}):
                        if not self._is_running:
                            break
                        for name in files:
                            # Split off any version like ;1 for ISO-9660 when evaluating extension
                            name_no_ver = name.split(';')[0]
                            if os.path.splitext(name_no_ver)[1].lower() in self._supported_formats:
                                path = os.path.join(root, name).replace('\\', '/')
                                found.append({'path_type': key, 'path': path})
                                self.log_message.emit(f"Found ({label}): {path}")
                    if found:
                        entries.extend(found)
                        # Prefer first successful namespace with results
                        return entries
                except Exception as e:
                    self.log_message.emit(f"Walk using {label} failed: {e}")

            # As a last resort, try record iteration with ISO-9660 identifiers only
            if not entries:
                self.log_message.emit("No files via walk; trying record iteration (ISO-9660 identifiers)...")
                try:
                    for rec in iso.list_children(iso_path='/', recursive=True):
                        if not self._is_running:
                            break
                        if rec.is_file():
                            filename = rec.file_identifier().decode('utf-8', errors='ignore').split(';')[0]
                            if os.path.splitext(filename)[1].lower() in self._supported_formats:
                                # Build path by traversing parents using ISO identifiers
                                path = self._build_iso9660_path(rec)
                                entries.append({'path_type': 'iso_path', 'path': path})
                                self.log_message.emit(f"Found (record iter): {path}")
                except Exception as e:
                    self.log_message.emit(f"Record iteration failed: {e}")
        finally:
            try:
                iso.close()
            except Exception:
                pass
        return entries

    def _build_iso9660_path(self, rec):
        parts = []
        cur = rec
        while cur and not cur.is_root():
            try:
                name = cur.file_identifier().decode('utf-8', errors='ignore')
            except Exception:
                name = ''
            name = name.split(';')[0]
            if name and name != '\x00':
                parts.append(name)
                cur = getattr(cur, 'parent', None)
        parts.reverse()
        return '/' + '/'.join(parts)

    def stop(self):
        self._is_running = False

class DiscExtractWorker(QObject):
    """Worker to extract files from an ISO in a background thread."""
    finished = pyqtSignal(list) # Emits list of LOCAL paths of extracted files
    progress = pyqtSignal(int)
    log_message = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, iso_path, files_to_extract, dest_path):
        super().__init__()
        self._iso_path = iso_path
        self._files_to_extract = files_to_extract # can be list[str] (dir source) or list[dict] (iso source)
        self._dest_path = dest_path
        self._is_running = True

    def run(self):
        self.log_message.emit(f"Starting extraction from '{self._iso_path}' to '{self._dest_path}'...")
        extracted_paths = []
        iso = pycdlib.PyCdlib()
        try:
            iso.open(self._iso_path)
            total_files = len(self._files_to_extract) or 1
            for i, entry in enumerate(self._files_to_extract):
                if not self._is_running:
                    self.log_message.emit("Extraction canceled.")
                    break
                self.progress.emit(int(((i + 1) / total_files) * 100))

                # Normalize entry
                if isinstance(entry, dict):
                    path_type = entry.get('path_type', 'iso_path')
                    iso_path_val = entry.get('path', '')
                    base_name = os.path.basename(iso_path_val).split(';')[0]
                    kwargs = {path_type: iso_path_val}
                else:
                    iso_path_val = str(entry)
                    base_name = os.path.basename(iso_path_val).split(';')[0]
                    kwargs = {'iso_path': iso_path_val}

                local_dest_path = os.path.join(self._dest_path, base_name)
                self.log_message.emit(f"Extracting '{iso_path_val}' to '{local_dest_path}'...")
                
                # Extract using the appropriate namespace
                iso.get_file_from_iso(local_path=local_dest_path, **kwargs)
                
                extracted_paths.append(local_dest_path)
                self.log_message.emit(f"Successfully extracted {base_name}.")

            if self._is_running:
                self.finished.emit(extracted_paths)
            else:
                self.finished.emit([])

        except Exception as e:
            self.error.emit(f"An error occurred during extraction: {e}")
        finally:
            try:
                iso.close()
            except Exception:
                pass

    def stop(self):
        self._is_running = False

class DiscImportTab(QWidget):
    """A widget for the Disc/ISO Import tab."""
    files_extracted = pyqtSignal(list)
    log_message = pyqtSignal(str)

    def __init__(self, supported_formats, parent=None):
        super().__init__(parent)
        # Use a stricter set of extensions for disc/ISO scanning to avoid false positives like .dat
        ambiguous_exts = {'.dat'}
        self._supported_formats = [ext.lower() for ext in supported_formats if ext.lower() not in ambiguous_exts]
        self._scan_worker = None
        self._scan_thread = None
        self._extract_worker = None
        self._extract_thread = None
        self._found_files_cache = []
        self._source_type = '' # 'dir' or 'iso'
        self.setupUi()

    def setupUi(self):
        layout = QVBoxLayout(self)

        # Source selection
        source_group = QGroupBox("Source")
        source_layout = QGridLayout()
        self.source_combo = QComboBox()
        self.source_combo.setEditable(True)
        self.source_combo.addItem("Select a folder or ISO...")
        source_layout.addWidget(QLabel("Source:"), 0, 0)
        source_layout.addWidget(self.source_combo, 0, 1, 1, 3)
        
        browse_folder_btn = QPushButton("Browse Folder...")
        browse_folder_btn.clicked.connect(self.browse_source_folder)
        source_layout.addWidget(browse_folder_btn, 1, 1)
        
        browse_iso_btn = QPushButton("Browse ISO...")
        browse_iso_btn.clicked.connect(self.browse_iso_file)
        source_layout.addWidget(browse_iso_btn, 1, 2)
        
        source_group.setLayout(source_layout)
        layout.addWidget(source_group)

        # Destination
        dest_group = QGroupBox("Destination for Extraction")
        dest_layout = QHBoxLayout()
        self.dest_label = QLabel("No output directory selected.")
        browse_dest_btn = QPushButton("Select Destination")
        browse_dest_btn.clicked.connect(self.browse_destination_folder)
        dest_layout.addWidget(QLabel("Output Folder:"))
        dest_layout.addWidget(self.dest_label, 1)
        dest_layout.addWidget(browse_dest_btn)
        dest_group.setLayout(dest_layout)
        layout.addWidget(dest_group)

        # Controls
        control_layout = QHBoxLayout()
        self.scan_btn = QPushButton("Scan Source")
        self.scan_btn.clicked.connect(self.start_scan)
        self.extract_btn = QPushButton("Extract & Add to Queue")
        self.extract_btn.setEnabled(False) # Enabled after scan
        self.extract_btn.clicked.connect(self.extract_files)
        control_layout.addStretch()
        control_layout.addWidget(self.scan_btn)
        control_layout.addWidget(self.extract_btn)
        layout.addLayout(control_layout)

        # Progress and Log
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        # Connect internal log to the view
        self.log_message.connect(self.log_view.appendPlainText)

    def browse_source_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if directory:
            self.source_combo.setCurrentText(directory)
            self.log_message.emit(f"Source folder set to: {directory}")

    def browse_iso_file(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select ISO File", "", "ISO Files (*.iso)")
        if filename:
            self.source_combo.setCurrentText(filename)
            self.log_message.emit(f"Source ISO set to: {filename}")

    def browse_destination_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if directory:
            self.dest_label.setText(directory)
            self.log_message.emit(f"Destination folder set to: {directory}")

    def start_scan(self):
        source_path = self.source_combo.currentText()
        if not source_path or source_path == "Select a folder or ISO...":
            QMessageBox.warning(self, "No Source", "Please select a source folder or ISO to scan.")
            return

        if self._scan_thread and self._scan_thread.isRunning():
            self.log_message.emit("A scan is already in progress.")
            return

        self.scan_btn.setEnabled(False)
        self.extract_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.log_view.clear()
        self._found_files_cache = []

        self._scan_thread = QThread()
        self._scan_worker = DiscImportWorker(source_path, self._supported_formats)
        self._scan_worker.moveToThread(self._scan_thread)

        self._scan_worker.finished.connect(self.on_scan_finished)
        self._scan_worker.progress.connect(self.progress_bar.setValue)
        self._scan_worker.log_message.connect(self.log_message.emit)
        self._scan_worker.error.connect(self.on_scan_error)

        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_thread.finished.connect(self.cleanup_scan_worker)
        self._scan_thread.start()

    def on_scan_finished(self, files, source_type):
        self.scan_btn.setEnabled(True)
        if files:
            self.extract_btn.setEnabled(True)
            self._found_files_cache = files
            self._source_type = source_type
        else:
            self.log_message.emit("No supported media files found in the selected source.")
        
        if self._scan_thread:
            self._scan_thread.quit()

    def on_scan_error(self, message):
        QMessageBox.critical(self, "Scan Error", message)
        self.log_message.emit(f"ERROR: {message}")
        self.scan_btn.setEnabled(True)
        if self._scan_thread:
            self._scan_thread.quit()

    def extract_files(self):
        if not self._found_files_cache:
            self.log_message.emit("No files to add. Please scan a source first.")
            return

        # If the source was a directory, the files are already accessible.
        if self._source_type == 'dir':
            self.log_message.emit("Adding found files to the converter queue...")
            self.files_extracted.emit(self._found_files_cache)
            self.extract_btn.setEnabled(False)
            return

        # If the source was an ISO, we need to extract the files.
        if self._source_type == 'iso':
            dest_path = self.dest_label.text()
            if not dest_path or dest_path == "No output directory selected.":
                QMessageBox.warning(self, "No Destination", "Please select a destination folder for extraction.")
                return
            
            if self._extract_thread and self._extract_thread.isRunning():
                self.log_message.emit("An extraction is already in progress.")
                return

            self.scan_btn.setEnabled(False)
            self.extract_btn.setEnabled(False)
            self.progress_bar.setValue(0)

            iso_path = self.source_combo.currentText()
            self._extract_thread = QThread()
            self._extract_worker = DiscExtractWorker(iso_path, self._found_files_cache, dest_path)
            self._extract_worker.moveToThread(self._extract_thread)

            self._extract_worker.finished.connect(self.on_extract_finished)
            self._extract_worker.progress.connect(self.progress_bar.setValue)
            self._extract_worker.log_message.connect(self.log_message.emit)
            self._extract_worker.error.connect(self.on_extract_error)

            self._extract_thread.started.connect(self._extract_worker.run)
            self._extract_thread.finished.connect(self.cleanup_extract_worker)
            self._extract_thread.start()

    def on_extract_finished(self, extracted_files):
        self.log_message.emit("Extraction complete.")
        self.files_extracted.emit(extracted_files)
        if self._extract_thread:
            self._extract_thread.quit()

    def on_extract_error(self, message):
        QMessageBox.critical(self, "Extraction Error", message)
        self.log_message.emit(f"ERROR: {message}")
        if self._extract_thread:
            self._extract_thread.quit()

    def cleanup_scan_worker(self):
        if self._scan_worker:
            self._scan_worker.stop()
        if self._scan_thread:
            self._scan_thread.wait(1000)
        self._scan_worker = None
        self._scan_thread = None
        self.scan_btn.setEnabled(True)

    def cleanup_extract_worker(self):
        if self._extract_worker:
            self._extract_worker.stop()
        if self._extract_thread:
            self._extract_thread.wait(1000)
        self._extract_worker = None
        self._extract_thread = None
        self.scan_btn.setEnabled(True)
        self.extract_btn.setEnabled(False) # Disable until next scan

    def closeEvent(self, event):
        self.cleanup_scan_worker()
        self.cleanup_extract_worker()
        if event:
            super().closeEvent(event)
