import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from makerbridge.lcf.reader import Reader, read_signature, probe_array, probe_struct

buf = open(sys.argv[1], "rb").read()
sig, off = read_signature(buf)
names = {0x0B:"Actor",0x0C:"Skill",0x0D:"Item",0x0E:"Enemy",0x0F:"Troop",0x10:"Terrain",
         0x11:"Attribute",0x12:"State",0x13:"Animation",0x14:"Chipset",0x15:"Terms",
         0x16:"System",0x17:"Switches",0x18:"Variables",0x19:"CommonEvent"}
for cid, payload in Reader(buf, off).chunks():
    label = names.get(cid, "?")
    arr = probe_array(payload)
    st = probe_struct(payload)
    if arr is not None:
        print(f"[0x{cid:02X}] {label:<12} ARRAY n={len(arr):<4} entry_ids={[e[0] for e in arr[:5]]} "
              f"chunk_ids_of_#1={sorted(hex(k) for k in arr[0][1])}")
    elif st is not None:
        print(f"[0x{cid:02X}] {label:<12} STRUCT ids={[hex(k) for k in sorted(st)]}")
    else:
        print(f"[0x{cid:02X}] {label:<12} RAW {len(payload)}B")
