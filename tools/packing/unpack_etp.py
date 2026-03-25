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


def determine_etp_version(file: str) -> int:
    with open(file, "rb") as f:
        evtx_header = unpack("4s", f.read(4))[0]
        if evtx_header != b"EVTX":
            return None
        f.read(11)
        version = f.read(1)
    return int(version.hex())


def unpack_etp_0_2(file: str):
    with open(file, "rb") as f:
        evtx_header = unpack("4s", f.read(4))[0]
        if evtx_header != b"EVTX":
            return "Not an ETP file."
        f.seek(80)  # jump to INDX structure
        f.read(4)  # jump passed INDX signature
        f.read(4)  # jump passed header length
        indx_size = unpack_uint(f.read(4))
        f.read(4)  # jump passed padding
        indx_pos = f.tell()
        indx_contents = f.read(indx_size)
        f.read(16)  # jump passed FOOT
        f.read(16)  # jump passed TEXT signature

        text_pos = f.tell()

        # iterate over INDX structure
        count = 0
        position = 0
        ja_records = {}
        en_records = {}
        for string_id, offset in iter_unpack("<I I", indx_contents):
            if string_id == 0:
                continue
            f.seek(text_pos + offset)

            text_str = read_cstr(f)
            ja_record = {text_str: text_str}
            en_record = {text_str: ""}
            ja_records[string_id] = ja_record
            en_records[string_id] = en_record

            count += 1
            position += 8

    return ja_records, en_records


def unpack_etp_1(file: str):
    with open(file, "rb") as f:
        evtx_header = unpack("4s", f.read(4))[0]
        if evtx_header != b"EVTX":
            return "Not an ETP file."
        f.seek(44)  # jump to CMNH section that has number of offsets in file
        offset_count = unpack_uint(f.read(4))
        f.seek(88)  # jump to INDX structure
        indx_size = unpack_uint(f.read(4))
        f.seek(4, 1)
        indx_contents = f.read(indx_size)
        offset_table_size = unpack_ushort(indx_contents[2:4])  # size of offset table. if number of offsets is bigger than this, the table has a second section of offsets read in <I
        f.seek(32, 1)
        text_pos = f.tell()

        ja_records = {}
        en_records = {}

        offsets_used = []
        iterate = 0
        indx_pos = 20  # 20 is start of offsets in indx
        while iterate != offset_table_size:
            iterate += 1
            offset = unpack_ushort(indx_contents[indx_pos:indx_pos+2])
            if offset == 0 or offset in offsets_used:
                indx_pos += 2
                continue

            f.seek(text_pos + (offset * 2))

            text_str = read_cstr(f)

            ja_records[offset] = {text_str: text_str}
            en_records[offset] = {text_str: ""}
            offsets_used.append(offset)
            indx_pos += 2


        # remaining offsets must be read as <I
        if iterate != offset_count:
            next_indx_pos = (iterate * 2) + 20  # 20 is where we started for offsets
            # if current pos is not divisble by 4, next two bytes will be "CD AB". if this is true,
            # skip over it as these are bytes to pad alignment before transitioning to reading offsets
            # as <I
            if diff := (next_indx_pos + 96) % 4 != 0:  # 96 is start of inside of indx table
                next_indx_pos += 2

            while iterate != offset_count:
                iterate += 1
                offset = unpack_uint(indx_contents[next_indx_pos:next_indx_pos+4])
                if offset == 0 or offset in offsets_used:
                    next_indx_pos += 4
                    continue

                f.seek(text_pos + (offset * 2))

                text_str = read_cstr(f)

                ja_records[offset] = {text_str: text_str}
                en_records[offset] = {text_str: ""}
                offsets_used.append(offset)
                next_indx_pos += 4

        return ja_records, en_records


def unpack_etp_4(file: str):
    with open(file, "rb") as f:
        evtx_header = unpack("4s", f.read(4))[0]
        if evtx_header != b"EVTX":
            return "Not an ETP file."

        # ignore other headers and jump straight to INDX
        f.seek(88)  # jump to INDX length

        # size of entire INDX table (minus the first 16 bytes for the INDX header)
        indx_size = unpack_uint(f.read(4))
        f.read(4)  # jump passed junk

        # read in entire indx table starting at pos 96
        indx_table = f.read(indx_size)

        # go back to the beginning of the indx table at pos 96
        f.seek(-indx_size, 1)

        # first 2 bytes: count of 2-byte string IDs (ushort). multiply by 2 to get byte length.
        str_table_size = unpack("<H", f.read(2))[0] * 2

        # next 2 bytes: count of 2-byte (short) offsets (ushort). multiply by 2 to get byte length.
        offset_table_size = unpack("<H", f.read(2))[0] * 2

        # this is not hit.
        if str_table_size == 0:
            print(f"String table length is 0 for {file}. I'm ignoring this file because it's abnormal.")
            return

        f.seek(96 + indx_size) # jump passed indx table
        f.read(32)  # jump passed FOOT + TEXT
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
        en_records = {}
        offsets_written = []

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
            if offset in offsets_written:
                continue

            f.seek(text_pos + (offset * 2))

            text_str = read_cstr(f)
            ja_records[string_id] = {text_str: text_str}
            en_records[string_id] = {text_str: ""}
            offsets_written.append(offset)

    return ja_records, en_records


def unpack_etp(file: str):
    file_version = determine_etp_version(file)
    if file_version in [0, 2]:
        data = unpack_etp_0_2(file=file)
    elif file_version == 1:
        data = unpack_etp_1(file=file)
    elif file_version == 4:
        data = unpack_etp_4(file=file)
    elif not file_version:
        sys.exit("Not an ETP file.")
    else:
        sys.exit(f"ETP version \"{file_version}\" is not currently supported.")
    if data:
        write_to_json(orig_filename=file, data=data[0], locale="ja")
        write_to_json(orig_filename=file, data=data[1], locale="en")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read an unencrypted ETP file and dump to JSON.")
    parser.add_argument("-e", help="Unpack a single ETP file.")
    parser.add_argument("-a", default=False, action="store_true", help="Unpack all ETPs dumped in the dump_etps folder.")
    args = parser.parse_args()

    if args.e:
        unpack_etp(file=args.e)

    if args.a:
        etp_files = glob.glob("../dump_etps/etps/*.etp")
        rps_files = glob.glob("../dump_etps/rps/*/*.etp")
        etps = etp_files + rps_files
        for etp in etps:
            print(etp)
            unpack_etp(file=etp)
