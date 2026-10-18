"""Probe the event-command encoding: count, then (code, indent, string, params)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from makerbridge.lcf.reader import Reader, read_signature, probe_array, probe_struct

ENC = "cp1252"

def parse_commands(payload, limit=18):
    r = Reader(payload)
    count = r.ber()
    print(f"    command count = {count} (payload {len(payload)}B)")
    for i in range(min(count, limit)):
        code = r.ber(); indent = r.ber()
        slen = r.ber(); s = r.bytes(slen).decode(ENC, "replace")
        n = r.ber(); params = [r.ber() for _ in range(n)]
        print(f"    {i:>3} code={code:<6} ind={indent} str={s!r} params={params}")
    print(f"    -> consumed {r.pos}/{len(payload)}, remaining {r.remaining()}")

path = sys.argv[1]
buf = open(path, "rb").read()
sig, off = read_signature(buf)
print(f"=== {os.path.basename(path)} {sig} ===")
if sig == "LcfDataBase":
    for cid, payload in Reader(buf, off).chunks():
        if cid != 0x19:   # CommonEvent
            continue
        arr = probe_array(payload)
        for entry_id, ch in arr[:2]:
            print(f"  CommonEvent #{entry_id} chunks={sorted(hex(k) for k in ch)}")
            print(f"    name={ch.get(0x01, b'').decode(ENC, 'replace')!r}")
            for k in (0x0B, 0x0C, 0x0D, 0x15):
                if k in ch:
                    print(f"    [0x{k:02X}] = {Reader(ch[k]).ber()}  ({len(ch[k])}B)")
            if 0x16 in ch:
                parse_commands(ch[0x16])
else:
    for cid, payload in Reader(buf, off).chunks():
        if cid != 0x51:   # events
            continue
        arr = probe_array(payload)
        print(f"  events n={len(arr)}")
        for entry_id, ch in arr[:2]:
            print(f"  Event #{entry_id} chunks={sorted(hex(k) for k in ch)}")
            print(f"    name={ch.get(0x01, b'').decode(ENC, 'replace')!r}")
            for k in (0x02, 0x03, 0x04):
                if k in ch:
                    print(f"    [0x{k:02X}] = {Reader(ch[k]).ber()}")
            pages = probe_array(ch.get(0x05, b"")) if 0x05 in ch else None
            print(f"    pages chunk 0x05 present={0x05 in ch} parsed={pages is not None}")
            if pages:
                for pid, pch in pages[:2]:
                    print(f"    Page #{pid} chunks={sorted(hex(k) for k in pch)}")
                    for k in (0x0B, 0x0C):
                        if k in pch:
                            print(f"      [0x{k:02X}] = {Reader(pch[k]).ber()} ({len(pch[k])}B)")
                    if 0x0D in pch:
                        parse_commands(pch[0x0D])
