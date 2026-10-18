"""One-line explanations and icons for ring slices.

Shown under the ring while hovering, so nobody has to guess what "AVIF" means.
Keys are action ids first, then lower-case labels.
"""

HINTS = {
    # formats
    "jpg": "Photo format that opens everywhere. Small file size",
    "png": "Sharp images with transparency. Best for screenshots",
    "webp": "Modern web format. Much smaller than JPG, same quality",
    "avif": "Newest format. The smallest files at high quality",
    "heic": "iPhone photo format. Very small files",
    "tiff": "Lossless format for printing and scanning",
    "bmp": "Uncompressed bitmap for old software",
    "pdf": "Turn it into a PDF document anyone can open",
    "ico": "Icon file for websites (favicon) and apps",
    "gif": "Animated GIF that plays anywhere",
    "txt": "Pull out just the plain text",
    "docx": "Editable Microsoft Word document",
    "odt": "Editable LibreOffice document",
    "mp4": "The video format every phone and site plays",
    "webm": "Open web video format. Small and good quality",
    "mov": "Apple QuickTime video",
    "mkv": "Keeps every track. Fast, no quality loss",
    "mp3": "Music format that plays on anything",
    "wav": "Uncompressed studio-quality audio",
    "ogg": "Open audio format. Small files",
    "flac": "Lossless audio. Perfect quality",
    "m4a": "Apple / AAC audio. Great for phones",
    "opus": "Best quality at tiny sizes. Great for voice",
    "zip": "Pack into one ZIP file for sending",
    # tools
    "image.compress": "Shrink the file size so it's easy to send",
    "image.crop": "Cut out just the part you want",
    "image.add_bg": "Put it on a pretty background with shadow",
    "image.edit": "Brightness, contrast, colour, rotate and flip",
    "image.metadata": "Remove hidden info like location and camera",
    "image.rotate": "Turn it 90° clockwise",
    "image.resize": "Make it half the width and height",
    "image.grayscale": "Black and white version",
    "image.combine_pdf": "Put all these images into one PDF",
    "pdf.compress": "Make the PDF smaller for email",
    "pdf.split": "One PDF file per page",
    "pdf.rotate": "Turn every page 90°",
    "pdf.images": "Save every picture inside the PDF",
    "pdf.merge": "Join these PDFs into one",
    "pdf.to_jpg": "Every page becomes a JPG picture",
    "pdf.to_png": "Every page becomes a sharp PNG picture",
    "video.trim": "Cut the start and end, mute or speed up",
    "video.compress": "Smaller video for WhatsApp and email",
    "video.mute": "Remove the sound",
    "video.frame": "Save the first frame as a picture",
    "video.to_mp3": "Keep only the sound as MP3",
    "audio.normalize": "Even out the volume level",
}

# Symbolic icons from the Adwaita theme (shipped with Ubuntu).
ICONS = {
    "compress": "zoom-out-symbolic",
    "crop": "edit-cut-symbolic",
    "add bg": "insert-image-symbolic",
    "edit": "preferences-color-symbolic",
    "trim": "edit-cut-symbolic",
    "metadata": "view-conceal-symbolic",
    "rotate": "object-rotate-right-symbolic",
    "half size": "view-restore-symbolic",
    "grayscale": "display-brightness-symbolic",
    "zip": "package-x-generic-symbolic",
    "split pages": "view-paged-symbolic",
    "extract images": "image-x-generic-symbolic",
    "merge": "view-dual-symbolic",
    "one pdf": "emblem-documents-symbolic",
    "mute": "audio-volume-muted-symbolic",
    "first frame": "camera-photo-symbolic",
    "normalize": "audio-volume-high-symbolic",
}


def hint_for(action_id: str, label: str) -> str:
    return HINTS.get(action_id) or HINTS.get(label.lower(), "")


def icon_for(label: str) -> str:
    return ICONS.get(label.lower(), "")
