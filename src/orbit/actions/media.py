"""Audio and video (ffmpeg)."""

from ..core.actions import TOOLS, action
from ..core.filetypes import Kind
from ..core.naming import output_path
from . import need, run

VID, AUD = [Kind.VIDEO], [Kind.AUDIO]
HINT = "Install it with: sudo apt install ffmpeg"


def ffmpeg(src, out, *args):
    run([need("ffmpeg", HINT), "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), *args, str(out)],
        timeout=3600)
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
    @action(f"video.to_{fmt}", fmt.upper(), VID, skip_ext={fmt}, order=order)
    def convert(paths):
        return [ffmpeg(p, output_path(p, fmt), *_VIDEO_ARGS[fmt]) for p in paths]


def _audio(fmt, order, kinds):
    @action(f"{kinds[0].value}.to_{fmt}", fmt.upper(), kinds, skip_ext={fmt}, order=order)
    def convert(paths):
        return [ffmpeg(p, output_path(p, fmt), *_AUDIO_ARGS[fmt]) for p in paths]


for i, f in enumerate(["mp4", "webm", "mov", "mkv"]):
    _video(f, i)
_audio("mp3", 10, VID)  # extract the soundtrack
for i, f in enumerate(_AUDIO_ARGS):
    _audio(f, i, AUD)


@action("video.gif", "GIF", VID, order=5)
def to_gif(paths):
    vf = "fps=12,scale=480:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse"
    return [ffmpeg(p, output_path(p, "gif"), "-vf", vf) for p in paths]


@action("video.compress", "Compress", VID, page=TOOLS, icon="compress", order=0)
def compress_video(paths):
    return [ffmpeg(p, output_path(p, "mp4", "Compressed"), "-vf", "scale='min(1280,iw)':-2",
                   "-c:v", "libx264", "-crf", "28", "-preset", "slow", "-c:a", "aac", "-b:a", "96k") for p in paths]


@action("video.mute", "Mute", VID, page=TOOLS, icon="mute", order=1)
def mute(paths):
    return [ffmpeg(p, output_path(p, p.suffix.lstrip("."), "Muted"), "-c:v", "copy", "-an") for p in paths]


@action("video.frame", "First Frame", VID, page=TOOLS, icon="images", order=2)
def frame(paths):
    return [ffmpeg(p, output_path(p, "jpg", "Frame"), "-frames:v", "1", "-q:v", "2") for p in paths]


@action("audio.normalize", "Normalize", AUD, page=TOOLS, icon="volume", order=0)
def normalize(paths):
    return [ffmpeg(p, output_path(p, p.suffix.lstrip("."), "Normalized"), "-af", "loudnorm") for p in paths]
