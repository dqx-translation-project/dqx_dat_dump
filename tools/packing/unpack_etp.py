import argparse
import glob
import json
import os
import sys
from struct import iter_unpack, unpack

sys.path.append("../../")  # hack to use tools
from tools.lib.fileops import read_cstr, unpack_uint, unpack_ushort


def write_to_json(orig_filename: str, data: list, locale: str):
    os.makedirs(f"json/{locale}", exist_ok=True)
    file = os.path.split(orig_filename)[1].split(".etp")[0] + ".json"
    with open(f"json/{locale}/{file}", "w+", encoding="utf-8", newline="\n") as f:
        to_write = json.dumps(data, ensure_ascii=False, indent=2)
        f.write(to_write)
        f.write("\n")  # weblate adds a newline to EOF, so we should to prevent diffs.


def _parse_etp_event_text(f) -> tuple[dict, dict]:
    # ETP v0/v2 file layout:
    #   0x00 ( 4 bytes): "EVTX" magic
    #   0x50 (80, 4 bytes): "INDX" section signature
    #   0x54 (84, 4 bytes): INDX header length
    #   0x58 (88, 4 bytes): INDX contents size (bytes)
    #   0x5C (92, 4 bytes): padding
    #   0x60 (96, N bytes): INDX contents — pairs of (string_id: uint32, offset: uint32)
    #   0x60+N (16 bytes): FOOT section
    #   0x60+N+16 (16 bytes): TEXT section header
    #   0x60+N+32 onward: null-terminated strings (TEXT section body)
    #
    # Each INDX entry maps a string_id to a byte offset into the TEXT body.
    # string_id == 0 is a placeholder/empty entry and is skipped.
    f.seek(88)  # jump to INDX size field (past INDX sig at 80 and header length at 84)
    indx_size = unpack_uint(f.read(4))
    f.seek(96)  # jump to INDX contents (past padding at 92)
    indx_contents = f.read(indx_size)

    f.read(16)  # skip FOOT
    f.read(16)  # skip TEXT header
    text_pos = f.tell()

    ja_records = {}
    for string_id, offset in iter_unpack("<I I", indx_contents):
        if string_id == 0:
            continue
        f.seek(text_pos + offset)
        text_str = read_cstr(f)
        ja_records[string_id] = {text_str: text_str}  # source text maps to itself (used as translation key)

    en_records = {sid: {text: ""} for sid, v in ja_records.items() for text in v}
    return ja_records, en_records


def _parse_etp_sub_package(f) -> tuple[dict, dict]:
    f.seek(0)
    is_be = f.read(4) == b"XTVE"

    if is_be:
        # Big-endian ETP file layout (all three BE file types use this unified format):
        #   0x00 ( 4 bytes): "XTVE" magic (big-endian EVTX)
        #   0x58 (88, 4 bytes): INDX contents size (bytes, big-endian)
        #   0x5C (92, 4 bytes): padding
        #   0x60 (96, N bytes): INDX contents — pairs of (string_id: uint32_BE, offset: uint32_BE)
        #   0x60+N (16 bytes): TOOF section (big-endian FOOT)
        #   0x60+N+16 (16 bytes): TXET section header (big-endian TEXT)
        #   0x60+N+32 onward: null-terminated UTF-8 strings (text body)
        #
        # Each entry maps a string_id to a byte offset into the text body.
        # string_id == 0 entries are skipped.
        f.seek(88)
        indx_size = unpack(">I", f.read(4))[0]
        f.read(4)  # skip padding
        indx_contents = f.read(indx_size)

        f.read(16)  # skip TOOF
        f.read(16)  # skip TXET header
        text_pos = f.tell()

        ja_records = {}
        for string_id, offset in iter_unpack(">II", indx_contents):
            if string_id == 0:
                continue
            f.seek(text_pos + offset)
            text_str = read_cstr(f)
            ja_records[string_id] = {text_str: text_str}

        en_records = {sid: {text: ""} for sid, v in ja_records.items() for text in v}
        return ja_records, en_records

    # LE ETP v1 file layout:
    #   0x00 ( 4 bytes): "EVTX" magic
    #   0x2C (44, 4 bytes): total offset count (from CMNH section header)
    #   0x58 (88, 4 bytes): INDX contents size (bytes)
    #   0x5C (92, 4 bytes): padding
    #   0x60 (96, N bytes): INDX contents
    #     +0x00 (2 bytes): unknown
    #     +0x02 (2 bytes): count of entries in the short (2-byte) offset table
    #     +0x04 (16 bytes): unknown
    #     +0x14 (20, variable): short offset table — short_count * uint16 offsets
    #     after short table: optional 2-byte alignment pad (if file pos is not 4-byte aligned)
    #     after alignment: long offset table — (offset_count - short_count) * uint32 offsets
    #   0x60+N (16 bytes): FOOT section
    #   0x60+N+16 (16 bytes): TEXT section header
    #   0x60+N+32 onward: null-terminated strings (TEXT section body)
    #
    # Each offset is a character index into the TEXT body (multiply by 2 to get byte offset).
    # offset == 0 and duplicate offsets are skipped; the record key is the offset itself.
    # Offsets exceeding ushort range overflow into the long (4-byte uint) table.
    f.seek(44)  # jump to CMNH section that has total offset count
    offset_count = unpack_uint(f.read(4))

    f.seek(88)  # jump to INDX size field
    indx_size = unpack_uint(f.read(4))
    f.seek(96)  # jump to INDX contents (past padding at 92)
    indx_contents = f.read(indx_size)

    f.read(16)  # skip FOOT
    f.read(16)  # skip TEXT header
    text_pos = f.tell()

    # indx_contents[2:4]: count of entries in the short (2-byte) offset table
    short_count = unpack_ushort(indx_contents[2:4])
    short_table_start = 20  # offset table begins at byte 20 within indx_contents
    short_table_end = short_table_start + short_count * 2

    short_offsets = [o for o, in iter_unpack("<H", indx_contents[short_table_start:short_table_end])]

    # If total offsets exceed the short table, the remainder are stored as 4-byte uints.
    # Two padding bytes ("CD AB") may precede this section to restore 4-byte alignment.
    long_table_start = short_table_end
    if (long_table_start + 96) % 4 != 0:  # 96 = file offset of indx_contents start
        long_table_start += 2
    long_count = offset_count - short_count
    long_offsets = [o for o, in iter_unpack("<I", indx_contents[long_table_start:long_table_start + long_count * 4])]

    ja_records = {}
    offsets_seen = set()

    for offset in short_offsets + long_offsets:
        if offset == 0 or offset in offsets_seen:
            continue
        offsets_seen.add(offset)
        f.seek(text_pos + (offset * 2))
        text_str = read_cstr(f)
        ja_records[offset] = {text_str: text_str}

    en_records = {sid: {text: ""} for sid, v in ja_records.items() for text in v}
    return ja_records, en_records


def _parse_etp_smldt_msg_pkg(f) -> tuple[dict, dict]:
    # ETP v4 file layout:
    #   0x00 ( 4 bytes): "EVTX" magic
    #   0x58 (88, 4 bytes): INDX table size (bytes)
    #   0x5C (92, 4 bytes): padding
    #   0x60 (96, N bytes): INDX table
    #     +0x00 (2 bytes): count of 2-byte string IDs
    #     +0x02 (2 bytes): count of entries in the short (2-byte) offset table
    #     +0x04 (4 bytes): unknown
    #     +0x08 (4 bytes): offset within INDX table where 4-byte string ID section begins
    #     +0x0C (4 bytes): offset within INDX table where short (2-byte) offset table begins
    #     +0x10 (4 bytes): offset within INDX table where long (4-byte) offset table begins
    #     +0x14 (20, variable): 2-byte string IDs (str_table_size bytes)
    #     at long_str_start: 4-byte string IDs (empty when all IDs fit in a ushort)
    #     at short_offset_start: short (2-byte) offset table (offset_table_size bytes)
    #     at long_offset_start: long (4-byte) offset table (remainder of INDX table)
    #   0x60+N (32 bytes): FOOT section (16 bytes) + TEXT section header (16 bytes)
    #   0x60+N+32 onward: null-terminated strings (TEXT section body)
    #
    # String IDs and their offsets are stored in parallel: 2-byte IDs pair with 2-byte offsets,
    # 4-byte IDs pair with 4-byte offsets. Each offset is a character index into the TEXT body
    # (multiply by 2 to get byte offset). Duplicate offsets are skipped; first occurrence wins.
    f.seek(88)  # jump to INDX length

    # size of entire INDX table (minus the first 16 bytes for the INDX header)
    indx_size = unpack_uint(f.read(4))
    f.seek(96)  # jump to INDX contents (past padding at 92)
    indx_table = f.read(indx_size)

    # first 2 bytes: count of 2-byte string IDs (ushort). multiply by 2 to get byte length.
    str_table_size = unpack("<H", indx_table[0:2])[0] * 2

    # next 2 bytes: count of 2-byte (short) offsets (ushort). multiply by 2 to get byte length.
    offset_table_size = unpack("<H", indx_table[2:4])[0] * 2

    # this is not hit.
    if str_table_size == 0:
        print("String table length is 0. Ignoring this file because it's abnormal.")
        return

    f.seek(96 + indx_size)  # jump past indx table
    f.read(32)  # jump past FOOT + TEXT
    text_pos = f.tell()

    # INDX header bytes 8-11: start position (within indx_table) of the 4-byte string ID section.
    # When all IDs fit in a ushort this equals the short offset table start (empty 4-byte section).
    long_str_start = unpack("<I", indx_table[8:12])[0]

    # INDX header bytes 12-15: start position of the short (2-byte) offset table.
    short_offset_start = unpack("<I", indx_table[12:16])[0]

    # INDX header bytes 16-19: start position of the long (4-byte) offset table.
    long_offset_start = unpack("<I", indx_table[16:20])[0]

    # 2-byte string IDs start at byte 20.
    short_string_table = indx_table[20:20+str_table_size]

    # 4-byte string IDs follow. This section is empty when all IDs fit in a ushort.
    long_string_table = indx_table[long_str_start:short_offset_start]

    # offset tables are split into short (2-byte) and long (4-byte) sections at known positions.
    short_offset_table = bytearray(indx_table[short_offset_start:short_offset_start+offset_table_size])
    long_offset_table = bytearray(indx_table[long_offset_start:])

    ja_records = {}
    offsets_seen = set()

    # iterate over all string IDs: 2-byte IDs first, then 4-byte IDs.
    all_string_ids = [s[0] for s in iter_unpack("<H", short_string_table)]
    all_string_ids += [s[0] for s in iter_unpack("<I", long_string_table)]

    for string_id in all_string_ids:
        if short_offset_table:
            offset = unpack("<H", short_offset_table[0:2])[0]
            del short_offset_table[0:2]
        else:
            offset = unpack("<I", long_offset_table[0:4])[0]
            del long_offset_table[0:4]

        # game will sometimes have string ids that are pointing to the same
        # offset. in this case, we only want to use the first occurrence.
        # during packing, we'll handle these multiples.
        if offset in offsets_seen:
            continue
        offsets_seen.add(offset)

        f.seek(text_pos + (offset * 2))
        text_str = read_cstr(f)
        ja_records[string_id] = {text_str: text_str}

    en_records = {sid: {text: ""} for sid, v in ja_records.items() for text in v}
    return ja_records, en_records


def unpack_etp(file: str):
    parsers = {
        0: _parse_etp_event_text,
        2: _parse_etp_event_text,
        1: _parse_etp_sub_package,
        "be": _parse_etp_sub_package,
        4: _parse_etp_smldt_msg_pkg,
    }
    with open(file, "rb") as f:
        magic = unpack("4s", f.read(4))[0]
        if magic == b"XTVE":
            file_version = "be"
        elif magic == b"EVTX":
            f.seek(15)
            file_version = f.read(1)[0]
        else:
            sys.exit("Not an ETP file.")
        parser = parsers.get(file_version)
        if parser is None:
            sys.exit(f"ETP version \"{file_version}\" is not currently supported.")
        data = parser(f)

    if data:
        for locale, records in zip(("ja", "en"), data):
            write_to_json(orig_filename=file, data=records, locale=locale)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read an unencrypted ETP file and dump to JSON.")
    parser.add_argument("-e", help="Unpack a single ETP file.")
    parser.add_argument("-a", action="store_true", help="Unpack all ETPs dumped in the dump_etps folder.")
    args = parser.parse_args()

    if args.e:
        unpack_etp(file=args.e)

    if args.a:
        for etp in glob.glob("../dump_etps/etps/*.etp") + glob.glob("../dump_etps/rps/*/*.etp"):
            print(etp)
            unpack_etp(file=etp)
