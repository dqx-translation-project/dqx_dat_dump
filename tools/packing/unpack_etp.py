import argparse
import glob
import json
import os
from struct import unpack, iter_unpack
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.fileops import (
    unpack_uint,
    unpack_ushort,
    read_cstr
)


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

        # first 2 bytes are str table size. str table size is read as ushort * 2, or 18810
        str_table_size = unpack("<H", f.read(2))[0] * 2

        # next 2 bytes are offset table size. offset table size is read as ushort * 2, or 12944
        offset_table_size = unpack("<H", f.read(2))[0] * 2

        # this is not hit.
        if str_table_size == 0:
            print(f"String table length is 0 for {file}. I'm ignoring this file because it's abnormal.")
            return

        # this just gets TEXT stuff and isn't the current problem.
        f.seek(96 + indx_size) # jump passed indx table
        f.read(32)  # jump passed FOOT + TEXT
        text_pos = f.tell()

        # read our index table buffer to get the entire string table. we start at pos 20 in the buffer as we read this already.
        # strings start at pos 20 in the indx_table buffer.
        string_table = indx_table[20:20+str_table_size]

        # immediately after the string table in our buffer is the offset table. 20+ skips the first 20 bytes we already read
        # previously and we read passed the entire string table all the way to the end of the buffer.
        offset_table = bytearray(indx_table[20+str_table_size:])

        # if offset table starts with "CD AB", this was part of the string table
        # that isn't included in the size. get rid of it
        if offset_table[0:2] == b"\xCD\xAB":
            del offset_table[0:2]


        # this is a little janky to rely on, but if we find a needle in our haystack that is an odd number, we've found the
        # wrong delimiter. this splits the short and long offset tables up based on what we find.
        # the more "right" way to approach this would probably be to read the offsets 2 bytes at a time and look for a match,
        # but this was much quicker to implement.
        offset_tables = []

        pos = 0
        while True:
            pos = offset_table.find(b"\xCD\xAB", pos)

            # we didn't find a match at all. treat it as one bytearray.
            if (pos == -1):
                offset_tables.append(offset_table[0:])
                break

            # we found a match, but it's in the middle of two uints (because the number is negative). not the right delimiter.
            # keep looking...
            if (pos % 2) != 0:
                pos = pos + 1
                continue

            # we found a match and the number is positive. this is the right delimiter. split the table into short and long.
            if (pos % 2) == 0:
                offset_tables.append(offset_table[0:pos])
                offset_tables.append(offset_table[pos+2:])
                break

        short_offset_table = bytearray(offset_tables[0])
        long_offset_table = bytearray()

        # if we have more than one item in our offset_tables list, we have a long offset table we need to handle.
        if len(offset_tables) > 1:
            if len(offset_tables[1]) > 14:
                long_offset_table = bytearray(offset_tables[1])

        # we didn't find a CD AB delimiter, but there are definitely some long offsets in here because the offset
        # count that we read doesn't match. split the table up based on what we know.
        elif len(short_offset_table) > offset_table_size:
            short_offset_table = bytearray(offset_tables[0][:offset_table_size])
            long_offset_table = bytearray(offset_tables[0][offset_table_size:])

        ja_records = {}
        en_records = {}
        offsets_written = []

        # iterate over the string table
        for string_id in iter_unpack("<H", string_table):
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
            ja_records[string_id[0]] = {text_str: text_str}
            en_records[string_id[0]] = {text_str: ""}
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
