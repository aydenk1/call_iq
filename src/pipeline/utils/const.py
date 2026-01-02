from itertools import islice
from typing import Sequence

AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")

def chunked(seq: Sequence, n: int):
    it = iter(seq)
    while True:
        chunk = list(islice(it, n))
        if not chunk:
            return
        yield chunk