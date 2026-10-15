"""Low-level reader for liblcf binary containers (RPG Maker 2000/2003).

Format recap (as implemented by liblcf):

* Integers are "compressed" / BER-style: 7 payload bits per byte, big-endian,
  the high bit marks "another byte follows".
* A file begins with a length-prefixed ASCII signature, e.g. ``\x0bLcfDataBase``.
* A *struct* is a flat sequence of ``(id, size, payload)`` chunks terminated by
  a chunk id of 0.  Writers emit chunk ids in ascending order, which gives us a
  cheap validity check when probing unknown payloads.
* An *array of structs* is a count, then for each entry an id followed by that
  entry's chunk sequence.
"""

from __future__ import annotations

import struct
from typing import Dict, Iterator, List, Tuple


class LcfError(Exception):
    pass


class Reader:
    """Cursor over a bytes buffer with liblcf primitives."""

    __slots__ = ("buf", "pos")

    def __init__(self, buf: bytes, pos: int = 0) -> None:
        self.buf = buf
        self.pos = pos

    # -- primitives ----------------------------------------------------------
    def eof(self) -> bool:
        return self.pos >= len(self.buf)

    def remaining(self) -> int:
        return len(self.buf) - self.pos

    def byte(self) -> int:
        if self.pos >= len(self.buf):
            raise LcfError("unexpected end of buffer")
        b = self.buf[self.pos]
        self.pos += 1
        return b

    def ber(self) -> int:
        """Read a compressed integer."""
        value = 0
        for _ in range(8):
            b = self.byte()
            value = (value << 7) | (b & 0x7F)
            if not b & 0x80:
                return value
        raise LcfError("compressed integer too long")

    def bytes(self, n: int) -> bytes:
        if n < 0 or self.pos + n > len(self.buf):
            raise LcfError(f"read of {n} bytes past end of buffer")
        out = self.buf[self.pos:self.pos + n]
        self.pos += n
        return out

    def string(self, n: int, encoding: str) -> str:
        return decode_string(self.bytes(n), encoding)

    # -- composites ----------------------------------------------------------
    def chunks(self) -> Iterator[Tuple[int, bytes]]:
        """Yield ``(chunk_id, payload)`` until the terminating 0 id or EOF."""
        while not self.eof():
            cid = self.ber()
            if cid == 0:
                return
            size = self.ber()
            yield cid, self.bytes(size)

    def struct_chunks(self) -> Dict[int, bytes]:
        out: Dict[int, bytes] = {}
        for cid, payload in self.chunks():
            out[cid] = payload
        return out

    def array(self) -> List[Tuple[int, Dict[int, bytes]]]:
        """Read a counted array of structs: ``[(entry_id, chunks), ...]``."""
        count = self.ber()
        out: List[Tuple[int, Dict[int, bytes]]] = []
        for _ in range(count):
            entry_id = self.ber()
            out.append((entry_id, self.struct_chunks()))
        return out


def decode_string(raw: bytes, encoding: str) -> str:
    raw = raw.split(b"\x00", 1)[0]
    return raw.decode(encoding, errors="replace")


def read_signature(buf: bytes) -> Tuple[str, int]:
    """Return ``(signature, offset_after_signature)``."""
    r = Reader(buf)
    n = r.ber()
    sig = r.bytes(n).decode("ascii", errors="replace")
    return sig, r.pos


# -- payload decoders --------------------------------------------------------

def as_int(payload: bytes) -> int:
    """Chunk payloads holding a single integer are BER-encoded."""
    return Reader(payload).ber()


def as_bool(payload: bytes) -> bool:
    return bool(as_int(payload))


def as_int16_array(payload: bytes) -> List[int]:
    if len(payload) % 2:
        raise LcfError("int16 array with odd length")
    return list(struct.unpack(f"<{len(payload) // 2}h", payload))


def as_uint8_array(payload: bytes) -> List[int]:
    return list(payload)


def as_int32_array(payload: bytes) -> List[int]:
    if len(payload) % 4:
        raise LcfError("int32 array with odd length")
    return list(struct.unpack(f"<{len(payload) // 4}i", payload))


def as_ber_array(payload: bytes) -> List[int]:
    """A run of compressed integers filling the whole chunk."""
    r = Reader(payload)
    out: List[int] = []
    while not r.eof():
        out.append(r.ber())
    return out


def probe_struct(payload: bytes) -> Dict[int, bytes] | None:
    """Try to read ``payload`` as a chunk sequence; ``None`` if implausible.

    Used by the dumper to explore unknown chunks.  Requires that the payload is
    consumed exactly and that chunk ids ascend, which real liblcf output does.
    """
    if not payload:
        return None
    r = Reader(payload)
    out: Dict[int, bytes] = {}
    last = 0
    try:
        while not r.eof():
            cid = r.ber()
            if cid == 0:
                break
            if cid <= last:
                return None
            size = r.ber()
            out[cid] = r.bytes(size)
            last = cid
    except LcfError:
        return None
    if not r.eof() or not out:
        return None
    return out


def probe_array(payload: bytes) -> List[Tuple[int, Dict[int, bytes]]] | None:
    """Try to read ``payload`` as a counted array of structs."""
    if not payload:
        return None
    r = Reader(payload)
    try:
        count = r.ber()
        if count == 0 or count > 100000:
            return None
        out: List[Tuple[int, Dict[int, bytes]]] = []
        for _ in range(count):
            entry_id = r.ber()
            chunks: Dict[int, bytes] = {}
            last = 0
            while True:
                if r.eof():
                    raise LcfError("array entry not terminated")
                cid = r.ber()
                if cid == 0:
                    break
                if cid <= last:
                    raise LcfError("non-ascending chunk id")
                size = r.ber()
                chunks[cid] = r.bytes(size)
                last = cid
            out.append((entry_id, chunks))
    except LcfError:
        return None
    if not r.eof():
        return None
    return out
