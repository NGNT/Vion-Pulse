def handle_format_changed(format_text: str, video_codec_getter, video_codec_setter, audio_codec_getter, audio_codec_setter, warnings_list):
    """Apply sensible default codecs when container changes."""
    fmt = format_text.lower()
    v = video_codec_getter().lower()
    a = audio_codec_getter().lower()
    changed = False
    # WebM defaults
    if fmt == 'webm':
        if v not in ['vp9', 'av1']:
            video_codec_setter('VP9')
            changed = True
        if a not in ['opus', 'vorbis']:
            audio_codec_setter('Opus')
            changed = True
    elif fmt == 'mp4':
        if v in ['vp9', 'av1']:
            video_codec_setter('H.264')
            changed = True
        if a in ['opus', 'vorbis']:
            audio_codec_setter('AAC')
            changed = True
    elif fmt in ['avi', 'mov']:
        if v in ['hevc (hevc)', 'h.265 (hevc)', 'vp9', 'av1', 'h.265', 'hevc', 'av1'] or '265' in v or 'hevc' in v or 'vp9' in v or 'av1' in v:
            video_codec_setter('H.264')
            changed = True
        if fmt == 'mov' and a in ['mp3', 'vorbis']:
            audio_codec_setter('AAC')
            changed = True
    if changed:
        warnings_list.append(f"Adjusted codecs to match {format_text} container requirements.")

def adjust_and_warn_container_codec(format_text: str, video_codec_getter, video_codec_setter, audio_codec_getter, audio_codec_setter, warnings_list):
    """Validate container/codec pairings and auto-correct invalid combos."""
    warnings_list.clear()
    fmt = format_text.lower()
    v = video_codec_getter().lower()
    a = audio_codec_getter().lower()
    # Rules
    if fmt == 'webm':
        if v not in ['vp9', 'av1']:
            video_codec_setter('VP9')
            warnings_list.append('WebM requires VP9 or AV1 video; switched to VP9.')
        if a not in ['opus', 'vorbis'] or a == 'copy original':
            audio_codec_setter('Opus')
            warnings_list.append('WebM requires Opus or Vorbis audio; switched to Opus.')
    elif fmt == 'mp4':
        if v in ['vp9', 'av1']:
            video_codec_setter('H.264')
            warnings_list.append('MP4 typically does not support VP9/AV1 broadly; switched to H.264.')
        if a in ['opus', 'vorbis']:
            audio_codec_setter('AAC')
            warnings_list.append('MP4 prefers AAC (or MP3); switched to AAC.')
    elif fmt in ['avi', 'mov']:
        if any(c in v for c in ['hevc', '265', 'vp9', 'av1']):
            video_codec_setter('H.264')
            warnings_list.append(f"{format_text} container unsuitable for chosen codec; switched to H.264.")
        if fmt == 'mov' and a in ['mp3', 'vorbis']:
            audio_codec_setter('AAC')
            warnings_list.append('MOV prefers AAC; switched audio to AAC.')