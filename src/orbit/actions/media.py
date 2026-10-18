"""Audio and video (ffmpeg)."""

import subprocess

from ..core import progress
from ..core.actions import TOOLS, action
from ..core.filetypes import Kind
from ..core.naming import output_path
from . import ActionError, need

VID, AUD = [Kind.VIDEO], [Kind.AUDIO]
FF = ("!ffmpeg",)
HINT = "Install it with: sudo apt install ffmpeg"


def duration(src) -> float:
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=nw=1:nk=1", str(src)], capture_output=True, text=True, timeout=30)
        return float(res.stdout.strip())
    except (ValueError, OSError, subprocess.TimeoutExpired):
        return 0.0


def ffmpeg(src, out, *args, pre=(), length=None):
    """Run ffmpeg and report real progress from its -progress output."""
    total = length or duration(src)
    cmd = [need("ffmpeg", HINT), "-hide_banner", "-loglevel", "error", "-nostats", "-progress", "pipe:1",
           "-y", *pre, "-i", str(src), *args, str(out)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for line in proc.stdout:
        if line.startswith("out_time_us=") and total:
            try:
                progress.report(int(line.split("=")[1]) / 1e6 / total)
            except ValueError:
                pass
    err = proc.stderr.read()
    if proc.wait() != 0:
        raise ActionError("ffmpeg failed: " + " ".join(err.strip().splitlines()[-2:]))
    return out


_VIDEO_ARGS = {
    "mp4": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-movflags", "+faststart"],
    "webm": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"],
    "mov": ["-c:v", "libx264", "-crf", "20", "-c:a", "aac"],
    "mkv": ["-c", "copy"],
}
_AUDIO_ARGS = {
    "mp3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
    "wav": ["-vn", "-c:a", "pcm_s16le"],
    "ogg": ["-vn", "-c:a", "libvorbis", "-q:a", "5"],
    "flac": ["-vn", "-c:a", "flac"],
    "m4a": ["-vn", "-c:a", "aac", "-b:a", "192k"],
    "opus": ["-vn", "-c:a", "libopus", "-b:a", "128k"],
}


def _video(fmt, order):
    @action(f"video.to_{fmt}", fmt.upper(), VID, skip_ext={fmt}, order=order, requires=FF)
    def convert(paths):
        return [ffmpeg(p, output_path(p, fmt), *_VIDEO_ARGS[fmt]) for p in paths]


def _audio(fmt, order, kinds):
    @action(f"{kinds[0].value}.to_{fmt}", fmt.upper(), kinds, skip_ext={fmt}, order=order, requires=FF)
    def convert(paths):
        return [ffmpeg(p, output_path(p, fmt), *_AUDIO_ARGS[fmt]) for p in paths]


for i, f in enumerate(["mp4", "webm", "mov", "mkv"]):
    _video(f, i)
_audio("mp3", 10, VID)  # extract the soundtrack
for i, f in enumerate(_AUDIO_ARGS):
    _audio(f, i, AUD)


@action("video.gif", "GIF", VID, order=5, requires=FF)
def to_gif(paths):
    vf = "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
    return [ffmpeg(p, output_path(p, "gif"), "-vf", vf) for p in paths]


@action("video.trim", "Trim", VID, page=TOOLS, dialog="trim", order=-1, requires=FF)
def trim(paths):  # handled by the trim editor
    return []


def export_clip(src, start: float, end: float, mute=False, speed=1.0):
    """Cut [start, end] seconds, optionally muted and/or sped up."""
    suffix = "Trimmed" if speed == 1 else f"Trimmed {speed:g}x"
    out = output_path(src, "mp4", suffix)
    vf = [f"setpts=PTS/{speed}"] if speed != 1 else []
    args = ["-c:v", "libx264", "-preset", "fast", "-crf", "21",
            "-movflags", "+faststart"]
    if vf:
        args += ["-vf", ",".join(vf)]
    if mute:
        args += ["-an"]
    else:
        args += ["-c:a", "aac"] + (["-af", f"atempo={speed}"] if speed != 1 else [])
    return ffmpeg(src, out, *args, pre=["-ss", f"{start:.3f}", "-t", f"{end - start:.3f}"], length=(end - start) / speed)


@action("video.compress", "Compress", VID, page=TOOLS, icon="compress", order=0, requires=FF)
def compress_video(paths):
    return [ffmpeg(p, output_path(p, "mp4", "Compressed"), "-vf", "scale='min(1280,iw)':-2",
                   "-c:v", "libx264", "-crf", "28", "-preset", "slow", "-c:a", "aac", "-b:a", "96k") for p in paths]


@action("video.mute", "Mute", VID, page=TOOLS, icon="mute", order=1, requires=FF)
def mute(paths):
    return [ffmpeg(p, output_path(p, p.suffix.lstrip("."), "Muted"), "-c:v", "copy", "-an") for p in paths]


@action("video.frame", "First Frame", VID, page=TOOLS, icon="images", order=2, requires=FF)
def frame(paths):
    return [ffmpeg(p, output_path(p, "jpg", "Frame"), "-frames:v", "1", "-q:v", "2") for p in paths]


@action("audio.normalize", "Normalize", AUD, page=TOOLS, icon="volume", order=0, requires=FF)
def normalize(paths):
    return [ffmpeg(p, output_path(p, p.suffix.lstrip("."), "Normalized"), "-af", "loudnorm") for p in paths]
