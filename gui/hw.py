import subprocess
from typing import List, Tuple

def get_available_hw_accels() -> List[Tuple[str, str]]:
    """Detect available hardware acceleration options."""
    hw_accels = [('Software (CPU)', 'software')]
    try:
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        out = (result.stdout or '') + (result.stderr or '')
        low = out.lower()
        if 'nvenc' in low:
            hw_accels.append(('NVIDIA NVENC', 'nvenc'))
        if ' qsv' in low:
            hw_accels.append(('Intel Quick Sync', 'qsv'))
        if ' amf' in low:
            hw_accels.append(('AMD AMF', 'amf'))
    except Exception:
        pass
    return hw_accels

def _map_preset_to_hardware(preset_text: str, hw_type: str) -> str:
    """Map software presets to hardware-specific preset equivalents."""
    preset_lower = preset_text.lower()
    
    # Map software presets to NVENC presets (p1-p7, performance to quality)
    software_to_nvenc = {
        'ultrafast': 'p1',   # Fastest encoding
        'superfast': 'p1', 
        'veryfast': 'p2',
        'faster': 'p3',
        'fast': 'p3',
        'medium': 'p4',      # Balanced (default)
        'slow': 'p5',
        'slower': 'p6',
        'veryslow': 'p7'     # Best quality
    }
    
    # Map software presets to QSV presets
    software_to_qsv = {
        'ultrafast': 'veryfast',
        'superfast': 'veryfast', 
        'veryfast': 'veryfast',
        'faster': 'faster',
        'fast': 'fast',
        'medium': 'medium',
        'slow': 'slow',
        'slower': 'slower',
        'veryslow': 'veryslow'
    }
    
    # Map software presets to AMF quality settings
    software_to_amf_quality = {
        'ultrafast': 'speed',
        'superfast': 'speed',
        'veryfast': 'speed', 
        'faster': 'speed',
        'fast': 'balanced',
        'medium': 'balanced',
        'slow': 'quality',
        'slower': 'quality',
        'veryslow': 'quality'
    }
    
    if hw_type == 'nvenc':
        return software_to_nvenc.get(preset_lower, 'p4')  # Default to p4 (medium)
    elif hw_type == 'qsv':
        return software_to_qsv.get(preset_lower, 'medium')
    elif hw_type == 'amf':
        return software_to_amf_quality.get(preset_lower, 'balanced')
    
    return 'medium'  # Fallback

def get_ffmpeg_hw_accel_args(hw_accel_name: str, video_codec_text: str, preset_text: str) -> dict:
    """Get FFmpeg arguments for the selected hardware acceleration (encode) and potential decode accel."""
    hw_accels = dict(get_available_hw_accels())
    hw_accel_type = hw_accels.get(hw_accel_name, 'software')
    is_h264 = 'h264' in video_codec_text.lower()
    
    if hw_accel_type == 'nvenc':
        mapped_preset = _map_preset_to_hardware(preset_text, 'nvenc')
        return {
            'encoder': 'h264_nvenc' if is_h264 else 'hevc_nvenc',
            'decode_hwaccel': 'cuda',
            'extra': ['-preset', mapped_preset, '-rc', 'vbr'],
            'preset_info': f"Software preset '{preset_text}' mapped to NVENC preset '{mapped_preset}'"
        }
    elif hw_accel_type == 'qsv':
        mapped_preset = _map_preset_to_hardware(preset_text, 'qsv')
        return {
            'encoder': 'h264_qsv' if is_h264 else 'hevc_qsv',
            'decode_hwaccel': 'qsv',
            'extra': ['-preset', mapped_preset],
            'preset_info': f"Software preset '{preset_text}' mapped to QSV preset '{mapped_preset}'"
        }
    elif hw_accel_type == 'amf':
        mapped_quality = _map_preset_to_hardware(preset_text, 'amf')
        return {
            'encoder': 'h264_amf' if is_h264 else 'hevc_amf',
            'decode_hwaccel': 'd3d11va',
            'extra': ['-usage', 'transcoding', '-quality', mapped_quality],
            'preset_info': f"Software preset '{preset_text}' mapped to AMF quality '{mapped_quality}'"
        }
    else:
     # Software encoding - use preset directly
        return {
            'encoder': 'libx264' if is_h264 else 'libx265',
            'decode_hwaccel': None,
            'pix_fmt': 'yuv420p',
            'extra': ['-preset', preset_text.lower(), '-movflags', '+faststart'],
            'preset_info': f"Using software preset '{preset_text}' directly"
        }
