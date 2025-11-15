"""
FFmpeg Process Runner

This utility provides a standardized, interruptible way to run FFmpeg subprocesses,
handling process lifetime, cancellation, and output collection. This avoids issues
with hanging threads and ensures FFmpeg processes are terminated cleanly.
"""

import subprocess
import time
from typing import Optional, Tuple

def run_ffmpeg_interruptible(
    cmd: list,
    stop_event,
    log_callback,
    timeout_seconds: int = 20
) -> Optional[Tuple[str, str]]:
    """
    Run an FFmpeg command as an interruptible subprocess.

    Args:
        cmd: The FFmpeg command list to execute.
        stop_event: A threading.Event or similar object with an `is_set()` method.
                    If it's set, the process will be terminated.
        log_callback: A function to call for logging messages.
        timeout_seconds: How long to wait for the process to complete.

    Returns:
        A tuple of (stdout, stderr) if successful, or None if cancelled or failed.
    """
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
    except Exception as e:
        log_callback(f"Failed to start ffmpeg: {e}")
        return None

    # Poll process and allow early termination
    start_time = time.time()
    while proc.poll() is None:
        if stop_event.is_set():
            log_callback("ffmpeg_runner: Stop event received, terminating process.")
            try:
                proc.kill()
            except Exception:
                pass
            return None  # Cancelled

        if time.time() - start_time > timeout_seconds:
            log_callback(f"ffmpeg_runner: Process timed out after {timeout_seconds}s, terminating.")
            try:
                proc.kill()
            except Exception:
                pass
            return None # Timed out

        time.sleep(0.05)

    # Collect final output
    try:
        stdout, stderr = proc.communicate(timeout=2)
        return stdout, stderr
    except Exception as e:
        log_callback(f"ffmpeg_runner: Error collecting output: {e}")
        try:
            proc.kill()
        except Exception:
            pass
        return None
