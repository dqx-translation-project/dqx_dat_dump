import functools
import itertools
from struct import unpack, pack
import zlib


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
    """
    Reads a null-terminated C string from the current file pointer.
    # https://stackoverflow.com/a/32775270

    :param f: File handle.
    :returns: Decoded string.
    """
    toeof = iter(functools.partial(f.read, 1), '')
    return ''.join(itertools.takewhile('\0'.__ne__, toeof))


def compute_crc32(path_name: str):
    """
    Computes a file or folder path into a CRC-32/JAMCRC dec/hex tuple.
    This is primarily used when interacting with IDX files.

    :param path_name: Path of the file name or folder path.
    """
    # path cannot have a forward slash at the end of the path
    # and must also be fully lowercase for accurate result.
    new_path_name = path_name.rstrip('/').lower().encode()
    crc32_jamcrc = int('0b' + '1' * 32, 2) - zlib.crc32(new_path_name)

    return (crc32_jamcrc, hex(crc32_jamcrc))


def compute_crc32_full(folder_path: str, filename: str):
    """
    Computes the full path of a file into a CRC-32/JAMCRC dec/hex tuple.
    This is primarily used when interacting with IDX files.

    :param folder_path: Path to the folder.
    :param filename: Name of the file.
    """
    folder_crc, file_crc = compute_crc32(folder_path), compute_crc32(filename)
    calculated_crc = folder_crc[0] << 32 | file_crc[0]

    return (calculated_crc, hex(calculated_crc))
