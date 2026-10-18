"""Interactive explorer: dump the raw chunk tree of an LCF file.

Used to verify chunk ids and payload shapes against a real project instead of
trusting memory.  Not part of the conversion pipeline.
"""
from __future__ import annotations

import sys, os, struct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from makerbridge.lcf.reader import (
    Reader, read_signature, probe_struct, probe_array, as_ber_array,
)

ENC = "cp1252"
MAXDEPTH = int(os.environ.get("MAXDEPTH", "3"))
MAXENTRIES = int(os.environ.get("MAXENTRIES", "3"))


def printable(raw: bytes) -> str | None:
    if not raw:
        return None
    s = raw.split(b"\x00", 1)[0]
    if not s:
        return None
    try:
        t = s.decode(ENC)
    except Exception:
        return None
    if all(c.isprintable() or c in "\n\r\t" for c in t) and len(t) == len(s):
        return t
    return None


def describe(payload: bytes) -> str:
    bits = [f"{len(payload)}B"]
    txt = printable(payload)
    if txt is not None:
        bits.append(f"str={txt!r}")
    if 0 < len(payload) <= 5:
        try:
            bits.append(f"ber={Reader(payload).ber()}")
        except Exception:
            pass
    if len(payload) <= 24:
        bits.append("hex=" + payload.hex(" "))
    elif len(payload) % 2 == 0 and len(payload) <= 64:
        bits.append("i16=" + str(list(struct.unpack(f"<{len(payload)//2}h", payload))))
    return "  ".join(bits)


def dump_chunks(chunks: dict[int, bytes], depth: int, path: str) -> None:
    pad = "  " * depth
    for cid, payload in sorted(chunks.items()):
        print(f"{pad}[0x{cid:02X}] {describe(payload)}")
        if depth >= MAXDEPTH or len(payload) < 3:
            continue
        arr = probe_array(payload)
        if arr is not None and len(arr) > 0:
            print(f"{pad}  -> ARRAY n={len(arr)} ids={[e[0] for e in arr[:8]]}")
            for entry_id, sub in arr[:MAXENTRIES]:
                print(f"{pad}  #{entry_id}")
                dump_chunks(sub, depth + 2, f"{path}/{cid:02X}")
            continue
        st = probe_struct(payload)
        if st is not None:
            print(f"{pad}  -> STRUCT ids={[hex(k) for k in sorted(st)]}")
            dump_chunks(st, depth + 2, f"{path}/{cid:02X}")


def main(path: str) -> None:
    buf = open(path, "rb").read()
    sig, off = read_signature(buf)
    print(f"=== {os.path.basename(path)}  sig={sig!r}  size={len(buf)} ===")
    r = Reader(buf, off)
    if sig == "LcfMapTree":
        arr = r.array()
        print(f"MapInfo array n={len(arr)} ids={[e[0] for e in arr]}")
        for entry_id, sub in arr[:MAXENTRIES]:
            print(f"#{entry_id}")
            dump_chunks(sub, 1, "mapinfo")
        print(f"-- after array, {r.remaining()} bytes left --")
        tail = buf[r.pos:]
        print("tail hex:", tail[:80].hex(" "))
        # tree order: BER array, then active node, then start-location chunks
        try:
            order = [r.ber() for _ in range(len(arr))]
            print("tree order:", order)
            print("active node:", r.ber())
            print("start chunks:")
            dump_chunks(r.struct_chunks(), 1, "start")
            print(f"remaining after start: {r.remaining()}")
        except Exception as exc:
            print("tail parse failed:", exc)
        return
    dump_chunks(r.struct_chunks(), 0, sig)


if __name__ == "__main__":
    main(sys.argv[1])
