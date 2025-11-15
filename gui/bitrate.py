def estimate_video_bitrate_from_size(input_file: str, get_duration_fn, target_size_mb: int, audio_bitrate_text: str, log_fn) -> tuple[int, int]:
    """Estimate video bitrate (kbps) to reach target size, considering audio bitrate.
    Returns (video_kbps, audio_kbps)."""
    duration = get_duration_fn(input_file)
    if duration <= 0:
        return 0, 0
    total_bits = target_size_mb * 1024 * 1024 * 8
    total_kbps = total_bits / duration / 1000
    try:
        audio_kbps = int(audio_bitrate_text.lower().replace('k', ''))
    except ValueError:
        audio_kbps = 160
    video_kbps = max(100, int(total_kbps - audio_kbps))
    log_fn(f"Estimator calculated video bitrate {video_kbps} kbps for target {target_size_mb} MB over {duration:.2f} s")
    return video_kbps, audio_kbps