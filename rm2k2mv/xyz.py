"""Read RPG Maker's own XYZ image format.

XYZ was the Maker's way of keeping artwork out of an image viewer.  It is not
encryption, just a thin container:

===========  ====================================================
``XYZ1``     4 byte magic
``uint16``   width, little endian
``uint16``   height, little endian
zlib data    768 bytes of palette (256 entries of R, G, B) followed by
             ``width * height`` bytes, one palette index per pixel
===========  ====================================================

The result is an 8-bit paletted image, exactly like the PNGs the Maker also
accepts - including the convention that palette index 0 is transparent.
"""

from __future__ import annotations

import os
import struct
import zlib

MAGIC = b"XYZ1"
PALETTE_BYTES = 768
IMAGE_EXTENSIONS = (".png", ".bmp", ".xyz")


class XyzError(Exception):
    pass


def is_xyz(path: str) -> bool:
    return os.path.splitext(path)[1].lower() == ".xyz"


def load(path: str):
    """Return the XYZ file at ``path`` as a paletted PIL image."""
    from PIL import Image

    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:4] != MAGIC:
        raise XyzError(f"{os.path.basename(path)} does not start with XYZ1")
    width, height = struct.unpack("<HH", raw[4:8])
    try:
        body = zlib.decompress(raw[8:])
    except zlib.error as exc:
        raise XyzError(f"{os.path.basename(path)}: {exc}") from exc

    expected = PALETTE_BYTES + width * height
    if len(body) < expected:
        raise XyzError(
            f"{os.path.basename(path)}: {len(body)} bytes after unpacking, "
            f"expected {expected} for {width}x{height}")

    image = Image.frombytes("P", (width, height),
                            body[PALETTE_BYTES:PALETTE_BYTES + width * height])
    image.putpalette(body[:PALETTE_BYTES])
    return image


def open_image(path: str):
    """Open a Maker image, whatever container it happens to use."""
    from PIL import Image

    if is_xyz(path):
        return load(path)
    return Image.open(path)
