import subprocess
import json
from typing import List, Dict, Any, Callable
import os

def build_ffmpeg_command(
    input_file: str,
    output_file: str,
    format_combo_text: str,
    video_codec_text: str,
    preset_text: str,
    quality_mode_text: str,
    crf_value: int,
    adv_bitrate_value: int,
    framerate_mode_text: str,
    framerate_text: str,
    hw_accel_combo_text: str,
    hw_decode_checkbox_checked: bool,
    hw_scale_checkbox_checked: bool,
    preserve_cover_art_checkbox_checked: bool,
    audio_track_combo_data,
    subtitle_plan: List[Dict[str, Any]], # [{'original_index': int, 'method': 'Copy'|'Burn-in'|'Convert to SRT'}]
    subtitle_meta: list,
    audio_meta: list,
    threads_value: int,
    extra_params_text: str,
    log_fn: Callable[[str], None],
    probe_attached_pictures_fn: Callable[[str], List[int]],
    get_ffmpeg_hw_accel_args_fn: Callable[[str], Dict],
    escape_path_fn: Callable[[str], str],
    resolution_text: str,
    deinterlace_checkbox_checked: bool,
    deinterlace_auto_checkbox_checked: bool,
    detect_interlacing_fn: Callable[[str], str],
    audio_codec_text: str,
    vbr_target_value: int,
    vbr_max_value: int,
    vbr_min_value: int,
    crop_filter: str = None,
    scale_filter: str = None,
    volume: float = 1.0,
    normalize: bool = False,
    normalize_ebu: bool = False,
    ebu_target_loudness: int = -23,
    pass_num: int = 0
) -> List[str]:
    """
    Builds the full FFmpeg command as a list of strings.
    This function now centralizes command construction logic.
    """
    if not input_file or not output_file:
        raise ValueError("Invalid input or output file.")

    # Probe streams
    has_video = False
    has_audio = False
    video_streams = []
    audio_count =0
    try:
        probe_cmd = ['ffprobe','-v','error','-show_entries','stream=index,codec_type,codec_name,disposition','-of','json', input_file]
        probe_res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        pdata = json.loads(probe_res.stdout or '{}')
        for s in pdata.get('streams', []):
            ctype = s.get('codec_type')
            if ctype == 'video':
                disp = s.get('disposition') or {}
                video_streams.append({'attached_pic': bool(disp.get('attached_pic'))})
            elif ctype == 'audio':
                has_audio = True
                audio_count +=1
        usable_video_indices = [i for i,v in enumerate(video_streams) if not v.get('attached_pic')]
        video_map_index = usable_video_indices[0] if usable_video_indices else None
        has_video = video_map_index is not None
    except Exception:
        video_map_index =0
        has_video = True

    # Hardware accel args
    hw_accel_args = get_ffmpeg_hw_accel_args_fn(hw_accel_combo_text)
    if 'preset_info' in hw_accel_args:
        log_fn(hw_accel_args['preset_info'])

    # Container constraints / encoder corrections
    output_ext = output_file.split('.')[-1].lower()
    if output_ext == 'webm':
        if 'av1' in video_codec_text.lower():
            hw_accel_args['encoder'] = 'libaom-av1'
        elif 'vp9' in video_codec_text.lower():
            hw_accel_args['encoder'] = 'libvpx-vp9'
        else:
            hw_accel_args['encoder'] = 'libvpx-vp9'
    elif output_ext in ['avi','mov']:
        enc = hw_accel_args.get('encoder','')
        if any(x in enc for x in ['hevc','av1','vp9','libvpx','libaom']):
            if 'nvenc' in enc:
                hw_accel_args['encoder'] = 'h264_nvenc'
            elif 'qsv' in enc:
                hw_accel_args['encoder'] = 'h264_qsv'
            elif 'amf' in enc:
                hw_accel_args['encoder'] = 'h264_amf'
            else:
                hw_accel_args['encoder'] = 'libx264'

    # Base command sections
    cmd = ['ffmpeg','-y']
    if hw_decode_checkbox_checked and hw_accel_args.get('decode_hwaccel'):
        cmd.extend(['-hwaccel', hw_accel_args['decode_hwaccel']])
    cmd.extend(['-i', input_file, '-loglevel','warning','-nostats','-progress','pipe:1'])

    # Determine burn-in target (first stream with method Burn-in)
    burn_in_entry = next((e for e in subtitle_plan if e.get('method') == 'Burn-in'), None)
    if burn_in_entry and not has_video:
        log_fn("Cannot burn-in subtitles: no primary video stream available.")
        burn_in_entry = None
    if burn_in_entry:
        # Warn if multiple burn-in selections
        extra_burns = [e for e in subtitle_plan if e.get('method') == 'Burn-in' and e is not burn_in_entry]
        if extra_burns:
            log_fn(f"Multiple burn-in selections detected; only stream {burn_in_entry['original_index']} will be burned in.")

    # Build video filter chain
    vf_chain = []
    # Auto / manual deinterlace
    deint_active = deinterlace_checkbox_checked
    if deinterlace_auto_checkbox_checked:
        det = detect_interlacing_fn(input_file)
        log_fn(f"Auto interlace detection: {det}")
        if det == 'interlaced':
            deint_active = True
    if deint_active:
        vf_chain.append('bwdif=0:-1:0')
    # Crop & scale filters from managers
    if crop_filter:
        vf_chain.append(crop_filter)
    if scale_filter:
        vf_chain.append(scale_filter)

    # Resolution override (if scaling manager not handling it already)
    res_map = {'4k (2160p)':2160,'1440p':1440,'1080p':1080,'720p':720,'480p':480}
    if resolution_text.lower() in res_map and has_video:
        target_h = res_map[resolution_text.lower()]
        # Only add if not already scaled via scale_filter
        if not any('scale' in f for f in vf_chain):
            vf_chain.append(f'scale=-2:{target_h}')

    # Burn-in textual or image subtitles
    if burn_in_entry:
        orig_idx = burn_in_entry['original_index']
        meta = next((m for m in subtitle_meta if m.get('original_index') == orig_idx), None)
        if meta:
            codec_name = (meta.get('codec_name') or '').lower()
            text_codecs = {'subrip','ass','ssa','webvtt','mov_text'}
            if codec_name in text_codecs:
                escaped_path = escape_path_fn(input_file)
                vf_chain.append(f"subtitles='{escaped_path}':si={orig_idx}")
                log_fn(f"Burn-in textual subtitles stream {orig_idx}")
            else:
                # Image-based (e.g. pgs, dvd_sub). Use overlay via filter_complex.
                # Build filter_complex including existing vf_chain applied to video before overlay.
                base_video_chain = ','.join(vf_chain) if vf_chain else 'null'
                overlay_filter = f"[0:v]{base_video_CHAIN}[vpre];[vpre][0:s:{meta.get('pos')}]overlay[vout]"
                cmd.extend(['-filter_complex', overlay_filter, '-map','[vout]'])
                vf_chain = [] # Handled in complex chain
                log_fn(f"Burn-in image subtitles stream pos {meta.get('pos')} (original {orig_idx})")
        else:
            log_fn(f"Burn-in selection original_index {orig_idx} not found in metadata; skipping burn-in.")

    # Apply video filters if any remain and not consumed by filter_complex
    if vf_chain:
        cmd.extend(['-vf', ','.join(vf_chain)])

    # Map video streams (primary + attached pictures)
    attached_pic_indices = [i for i,v in enumerate(video_streams) if v.get('attached_pic')]
    if not preserve_cover_art_checkbox_checked:
        attached_pic_indices = []
    if has_video and video_map_index is not None:
        cmd.extend(['-map', f'0:v:{video_map_index}'])
    for idx in attached_pic_indices:
        cmd.extend(['-map', f'0:v:{idx}'])

    # Video codec (first real video output index is0)
    if has_video and video_map_index is not None:
        cmd.extend(['-c:v:0', hw_accel_args.get('encoder','libx264')])
        if 'pix_fmt' in hw_accel_args:
            cmd.extend(['-pix_fmt', hw_accel_args['pix_fmt']])
        extra_v = hw_accel_args.get('extra', [])
        if extra_v:
            cmd.extend(extra_v)
    # Quality / rate control
    mode = quality_mode_text
    is_software = hw_accel_combo_text.lower().startswith('software')
    if mode == 'Constant Quality (CRF)' and is_software:
        cmd.extend(['-crf', str(crf_value)])
    elif mode == 'Average Bitrate (kbps)':
        cmd.extend(['-b:v', f'{adv_bitrate_value}k'])
    elif mode == 'Variable Bitrate (VBR)':
        cmd.extend(['-b:v', f'{vbr_target_value}k', '-maxrate', f'{vbr_max_value}k', '-minrate', f'{vbr_min_value}k'])
    
    # Handle two-pass encoding flags
    if pass_num == 1:
        cmd.extend(['-pass', '1', '-an', '-f', 'null']) # No audio, null output
        # On Windows, NUL is the null device. On Unix-like systems, it's /dev/null.
        cmd.append('NUL' if os.name == 'nt' else '/dev/null')
        return cmd # First pass command is complete
    elif pass_num == 2:
        cmd.extend(['-pass', '2'])

    if framerate_mode_text == 'Constant' and framerate_text != 'Original':
        cmd.extend(['-r', framerate_text])

    # Audio mapping
    if has_audio and audio_count >0:
        sel = audio_track_combo_data
        if sel == 'all':
            for pos in range(audio_count):
                cmd.extend(['-map', f'0:a:{pos}'])
        elif isinstance(sel, int) and 0 <= sel < audio_count:
            cmd.extend(['-map', f'0:a:{sel}'])
        else:
            cmd.extend(['-map', '0:a:0'])

    # --- Audio Filters ---
    audio_filters = []
    if normalize:
        audio_filters.append("dynaudnorm")
    if normalize_ebu:
        # EBU R128 normalization using loudnorm filter
        # This is a two-pass filter, but we can do a single pass for simplicity.
        # For true compliance, a two-pass approach is better.
        loudnorm_filter = f"loudnorm=I={ebu_target_loudness}:LRA=11:TP=-1.5"
        audio_filters.append(loudnorm_filter)
    if volume != 1.0:
        audio_filters.append(f"volume={volume}")

    if audio_filters:
        cmd.extend(['-af', ",".join(audio_filters)])

    # --- Subtitle Handling ---
    subtitle_maps = []
    subtitle_stream_count = len(subtitle_meta)
    if subtitle_stream_count > 0:
        # Filter out Burn-in method since it's already handled by the video filter logic
        non_burnin_subtitles = [entry for entry in subtitle_plan if entry.get('method') != 'Burn-in']
        subtitle_output_index = 0 # This tracks the output subtitle stream index
        for entry in non_burnin_subtitles:
            orig_idx = entry['original_index']
            meta = next((m for m in subtitle_meta if m.get('original_index') == orig_idx), None)
            if not meta:
                log_fn(f"Subtitle original_index {orig_idx} not found; skipping.")
                continue
            
            pos = meta.get('pos')
            cmd.extend(['-map', f'0:s:{pos}'])
            
            method = entry.get('method')
            codec_name = (meta.get('codec_name') or '').lower()

            # Handle container compatibility
            if method == 'Copy' and output_ext == 'mp4' and codec_name in ['subrip', 'srt']:
                log_fn(f"Subtitle stream {orig_idx} is SubRip; converting to mov_text for MP4 container.")
                cmd.extend([f'-c:s:{subtitle_output_index}', 'mov_text'])
            elif method == 'Copy':
                cmd.extend([f'-c:s:{subtitle_output_index}', 'copy'])
            elif method == 'Convert to SRT':
                # If the target is MP4, this should also be mov_text.
                if output_ext == 'mp4':
                    cmd.extend([f'-c:s:{subtitle_output_index}', 'mov_text'])
                else:
                    cmd.extend([f'-c:s:{subtitle_output_index}', 'srt'])
            
            subtitle_output_index += 1

    # Threads & extra params (simple append)
    if threads_value and threads_value >0:
        cmd.extend(['-threads', str(threads_value)])
    if extra_params_text.strip():
        # naive split by space; advanced parsing could be added later
        cmd.extend(extra_params_text.strip().split())

    cmd.append(output_file)
    return cmd

    # --- Audio Only Mode ---
    if format_combo_text.startswith("Audio Only"):
        # Determine output extension and codec
        if "MP3" in format_combo_text:
            output_ext = "mp3"
            audio_codec = "libmp3lame"
        elif "AAC" in format_combo_text:
            output_ext = "aac"
            audio_codec = "aac"
        else:
            output_ext = "mp3"
            audio_codec = "libmp3lame"
        # Force output file extension
        if not output_file.lower().endswith(f".{output_ext}"):
            output_file = os.path.splitext(output_file)[0] + f".{output_ext}"
        cmd = ["ffmpeg", "-y", "-i", input_file, "-vn", "-acodec", audio_codec]
        # Audio filters
        audio_filters = []
        if normalize:
            audio_filters.append("dynaudnorm")
        if normalize_ebu:
            loudnorm_filter = f"loudnorm=I={ebu_target_loudness}:LRA=11:TP=-1.5"
            audio_filters.append(loudnorm_filter)
        if volume !=1.0:
            audio_filters.append(f"volume={volume}")
        if audio_filters:
            cmd.extend(["-af", ",".join(audio_filters)])
        # Bitrate
        if adv_bitrate_value:
            cmd.extend(["-b:a", f"{adv_bitrate_value}k"])
        # Threads
        if threads_value and threads_value >0:
            cmd.extend(["-threads", str(threads_value)])
        if extra_params_text.strip():
            cmd.extend(extra_params_text.strip().split())
        cmd.append(output_file)
        return cmd