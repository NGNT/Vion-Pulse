def _escape_path_for_subtitles_filter(path: str) -> str:
    """Escape path for FFmpeg subtitles filter (handles backslashes and single quotes)."""
    if not path:
        return path
    escaped = path.replace('\\', '\\\\')  # \ -> \\
    escaped = escaped.replace("'", r"\'")  # ' -> \'
    return escaped