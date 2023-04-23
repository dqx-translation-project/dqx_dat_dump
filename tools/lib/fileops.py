from struct import unpack, pack



def unpack_ushort(buf: bytes) -> int:
    return unpack("<H", buf)[0]


def unpack_uint(buf: bytes) -> int:
    return unpack("<I", buf)[0]


def pack_ushort(val: int) -> bytes:
    return pack("<H", val)


def pack_uint(val: int) -> bytes:
    return pack("<I", val)


def write_foot(file_obj: object):
    foot = b"\x46\x4F\x4F\x54\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    return file_obj.write(foot)


def write_text(file_obj: object):
    text = b"\x54\x45\x58\x54\x10\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    return file_obj.write(text)


def read_cstr(f: object) -> str:
    buf = bytearray()
    while True:
        char = f.read(1)
        if char != b"\x00":
            buf.extend(char)
        else:
            return buf.decode(encoding="utf-8")
