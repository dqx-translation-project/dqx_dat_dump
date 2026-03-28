import argparse
import glob
import json
import os
from struct import unpack, iter_unpack
from subprocess import run
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.fileops import (
    pack_uint,
    pack_ushort,
    unpack_uint,
    unpack_ushort,
    write_foot,
    write_text
)
from tools.dump_etps.dqxcrypt.dqxcrypt import (
    attach_client,
    encrypt
)


def read_json_file(file: str):
    with open(file, "r", encoding="utf-8") as f:
        contents = f.read()
        return json.loads(contents)


def align_file(file_obj: object, alignment: int):
    """Add padding to end of file until its size is divisible by alignment."""
    while file_obj.seek(0, 2) % alignment != 0:
        file_obj.write(b"\x00")


def determine_etp_version(file: str) -> int:
    with open(file, "rb") as f:
        evtx_header = unpack("4s", f.read(4))[0]
        if evtx_header != b"EVTX":
            return None
        f.read(11)
        version = f.read(1)
    return int(version.hex())


def _pick_translation(record: dict) -> bytes:
    """Returns the translated string (en) if available, otherwise the source (ja), as null-terminated UTF-8 bytes."""
    ja, en = next(iter(record.items()))
    return bytes(en if en else ja, encoding="utf-8") + b"\x00"


def get_string_bytes(json_list: list, search_key: str) -> bytes:
    return _pick_translation(json_list[search_key])


def search_sublist(str_id_list: list, search_id: int):
    """
    Searches a list of lists for a matching search_id, then
    returns the first index in the list. This is intended to be used
    with version 4 files where we can find string ids that share the same offset,
    returning the string ids that are associated with an offset.

    :param str_id_list: List of string ids that you want to query
    :param search_id: The id to search for in the str_id_list
    :returns: Associated string ids.
    """
    for sublist in str_id_list:
        if search_id in sublist:
            return sublist


def build_string_table_1(json_list: list):
    """
    Builds a string table from json_list for version 1 files.
    Returns a list of the translated bytes to write to the string table
    and the new offset to write to the indx table.
    Return ex: {"114": {"str": "\x01\x03\x03\x05", new_offset: "\x01\xAB\x01\x00"}}
    In this example, "114" is the original offset to look up from the original file.
    """
    final_bytes = bytearray()
    offset_data = {}
    for str_id in json_list:
        str_bytes = _pick_translation(json_list[str_id])
        # ensures the string (including NTs) has an even number of bytes
        if len(str_bytes) % 2 != 0:
            str_bytes += b"\x00"
        if final_bytes:
            # shifts the offset by one
            new_offset = int(len(final_bytes) / 2 + 1)
        else:
            # v1 files start at offset 1
            new_offset = 1
        final_bytes += str_bytes
        offset_data[str_id] = {
            "str": str_bytes,
            "new_offset": new_offset
        }
    return offset_data, final_bytes


def build_string_table_4(json_list: list, dupe_string_list: list):
    """
    Builds a string table from json_list for version 4 files.
    Returns a list of the translated bytes to write to the string table
    and the new offset to write to the indx table.
    Return ex: {"114": {"str": "\x01\x03\x03\x05", new_offset: "\x01\xAB\x01\x00"}}
    In this example, "114" is the original offset to look up from the original file.
    """
    final_bytes = bytearray()
    offset_data = {}
    for str_id in json_list:
        find_dupes = search_sublist(str_id_list=dupe_string_list, search_id=int(str_id))

        # if there are multiple string ids that share the same offset,
        # we want to check if this is the primary (first) match. if not,
        # all other string ids in the list are going to reference the first
        # occurrence. we don't want to add the dupes to the text table, so
        # just map the existing offset.
        if len(find_dupes) > 1 and int(str_id) != find_dupes[0]:
            str_bytes = b""
            new_offset = offset_data[str(find_dupes[0])]["new_offset"]
        else:
            str_bytes = _pick_translation(json_list[str_id])
            # ensures the string (including NTs) has an even number of bytes
            if len(str_bytes) % 2 != 0:
                str_bytes += b"\x00"
            if final_bytes:
                new_offset = int(len(final_bytes) / 2)
            else:
                new_offset = 0
            final_bytes += str_bytes

        offset_data[str_id] = {
            "str": str_bytes,
            "new_offset": new_offset
        }

    return offset_data, final_bytes


def recalculate_headers(file_obj: object):
    "Update header lengths and add FOOTs to end of file."
    # update TEXT sizing
    file_obj.seek(88)
    indx_size = unpack_uint(file_obj.read(4))
    file_obj.read(4)  # read past padding
    file_obj.read(indx_size)
    file_obj.read(16)  # read past FOOT
    file_obj.read(16)  # read past TEXT
    text_start = file_obj.tell()
    text_end = file_obj.seek(0, 2)
    text_size = text_end - text_start
    file_obj.seek(text_start - 16 + 8)  # -16 to get to beginning of TEXT and +8 to jump to size. easier to read this way
    file_obj.write(pack_uint(text_size) + b"\x00\x00\x00\x00")
    file_obj.seek(0, 2)
    write_foot(file_obj=file_obj)

    # calculate new size for blja header
    file_obj.seek(80)
    blja_start = file_obj.tell()
    file_obj.seek(0, 2)
    blja_end = file_obj.tell()
    blja_size = blja_end - blja_start
    file_obj.seek(72)
    file_obj.write(pack_uint(blja_size))
    file_obj.seek(0, 2)
    write_foot(file_obj=file_obj)

    # calculate new size for evtx header
    file_obj.seek(16)
    evtx_start = file_obj.tell()
    file_obj.seek(0, 2)
    evtx_end = file_obj.tell()
    evtx_size = evtx_end - evtx_start
    file_obj.seek(8)
    file_obj.write(pack_uint(evtx_size))
    file_obj.seek(0, 2)
    write_foot(file_obj=file_obj)


def build_etp_0_2(json_list: list, src_etp: str):
    "Builds an ETP file for file versions 0 and 2."
    # grab original file header data we'll copy over to new file
    with open(src_etp, "rb") as f:
        orig_etp_data = f.read(96)
        indx_size = unpack_uint(orig_etp_data[88:92])
        indx_start = f.tell()
        orig_indx_table = f.read(indx_size)
        f.read(32)  # skip past FOOT + TEXT
        text_start = f.tell()

    etp_file = os.path.basename(src_etp)
    with open(f"new_etp/{etp_file}", "w+b") as etp_f:
        etp_f.write(orig_etp_data)
        etp_f.write(orig_indx_table)
        write_foot(file_obj=etp_f)
        write_text(file_obj=etp_f)
        curr_indx_pos = 0
        # iterate over indx entries in table
        for string_id, offset in iter_unpack("<I I", orig_indx_table):
            if string_id == 0:
                continue
            # update the indx entry first. we figure out where this is by jumping to the end
            # of the file, grabbing its position and subtracting it with the initial text start.
            text_offset = etp_f.seek(0, 2) - text_start # seek to end of file to get offset
            etp_f.seek(indx_start + curr_indx_pos + 4) # jump past string_id and get to text offset
            etp_f.write(pack_uint(text_offset)) # update the new offset
            etp_f.seek(0, 2) # position pointer back to end of file to write text
            string_bytes = get_string_bytes(json_list=json_list, search_key=str(string_id))
            if not string_bytes:
                sys.exit(f"Cannot build ETP. Unable to find key {offset} in json file.")
            etp_f.write(string_bytes)
            curr_indx_pos += 8
        align_file(file_obj=etp_f, alignment=16)
        recalculate_headers(file_obj=etp_f)


def build_etp_1(json_list: list, src_etp: str):
    "Builds an ETP file for file version 1."
    with open(src_etp, "rb") as f:
        orig_etp_data = f.read(96)
        offset_count = unpack_uint(orig_etp_data[44:48])  # get from cmnh
        indx_size = unpack_uint(orig_etp_data[88:92])
        orig_indx_table = f.read(indx_size)
        offset_table_size = unpack_ushort(orig_indx_table[2:4])

    etp_file = os.path.basename(src_etp)
    with open(f"new_etp/{etp_file}", "w+b") as etp_f:
        # write beginning of file
        etp_f.write(orig_etp_data)
        etp_f.write(orig_indx_table[:20])

        # first, we need to build our new string table.
        str_table, str_bytes = build_string_table_1(
            json_list=json_list,
        )

        # now we need to read the existing offset table, find the original offset in the
        # new str_table, grab the new offset we generated and write it here.
        iterate = 0
        orig_indx_pos = 20  # first offset is 20 bytes in
        wrote_offset_divider = False
        end_of_short_pos = 0
        wrote_cdab = False

        etp_f.seek(0, 2)
        while iterate < offset_table_size:
            offset = unpack_ushort(orig_indx_table[orig_indx_pos:orig_indx_pos+2])
            if offset == 0:
                if not wrote_offset_divider:
                    etp_f.write(b"\x00\x00")
                else:
                    etp_f.write(b"\x00\x00\x00\x00")
                orig_indx_pos += 2
                iterate += 1
                continue

            result = str_table[str(offset)]
            # write in shorts until we encounter our first uint
            if result["new_offset"] <= 65535 and not wrote_offset_divider:
                new_offset = pack_ushort(result["new_offset"])
            else:
                # hit our first uint. split the table up
                if not wrote_offset_divider:
                    end_of_short_pos = etp_f.tell()
                    if etp_f.tell() % 4 != 0:
                        end_of_short_pos = f.tell()
                        etp_f.write(b"\xCD\xAB")
                        wrote_cdab = True
                    wrote_offset_divider = True
                # hit an int that is too large to fit in a short. this table
                # will have a 4 byte offset section in the indx table going forward.
                new_offset = pack_uint(result["new_offset"])
            etp_f.write(new_offset)

            orig_indx_pos += 2
            iterate += 1

        # if we still have offsets in the original file left, we need to read them
        # as uints instead of ushorts.
        if iterate != offset_count:
            # check if we need to skip over cdab bytes in original table
            if orig_indx_table[orig_indx_pos:orig_indx_pos+2] == b"\xCD\xAB":
                orig_indx_pos += 2

            # iterate over remaining offsets in table
            while iterate != offset_count:
                offset = unpack_uint(orig_indx_table[orig_indx_pos:orig_indx_pos+4])
                if offset == 0:
                    if not wrote_offset_divider:
                        etp_f.write(b"\x00\x00")
                    else:
                        etp_f.write(b"\x00\x00\x00\x00")
                    orig_indx_pos += 4
                    iterate += 1
                    continue

                result = str_table[str(offset)]
                # write in shorts until we encounter our first uint
                if result["new_offset"] <= 65535 and not wrote_offset_divider:
                    new_offset = pack_ushort(result["new_offset"])
                else:
                    # hit our first uint. split the table up
                    if not wrote_offset_divider:
                        end_of_short_pos = etp_f.tell()
                        if etp_f.tell() % 4 != 0:
                            etp_f.write(b"\xCD\xAB")
                            wrote_cdab = True
                        wrote_offset_divider = True
                    # hit an int that is too large to fit in a short. this table
                    # will have a 4 byte offset section in the indx table going forward.
                    new_offset = pack_uint(result["new_offset"])
                etp_f.write(new_offset)
                orig_indx_pos += 4
                iterate += 1

        # need to track the short offset table size to update the data inside of the indx table
        if end_of_short_pos == 0:
            end_of_short_pos = etp_f.tell()

        # add cdab if current eof isn't in 4 byte increments
        if etp_f.tell() % 4 != 0:
            etp_f.write(b"\xCD\xAB")
            wrote_cdab = True
        align_file(file_obj=etp_f, alignment=16)
        end_of_indx = etp_f.tell()

        # update the value of the short table. if there is a "cd ab" value,
        # don't include this in the calculation
        etp_f.seek(98)
        etp_f.write(pack_uint(int((end_of_short_pos - 116) / 2)))  # -116 to remove everything up to where offset starts

        # update the value of the entire INDX section up to the end of the short
        # table. if there is a "cd ab" value, DO include this in the calculation.
        etp_f.seek(112)
        short_len = end_of_short_pos - 96  # -96 to remove everything up until start of indx
        if wrote_cdab:
            short_len += 2
        etp_f.write(pack_uint(short_len))

        new_indx_size = end_of_indx - 96
        etp_f.seek(88)
        etp_f.write(pack_uint(new_indx_size) + b"\x00\x00\x00\x00")
        etp_f.seek(0, 2)
        write_foot(file_obj=etp_f)
        write_text(file_obj=etp_f)
        etp_f.write(b"\x00\x00")  # first offset is always 0
        etp_f.write(str_bytes)
        align_file(file_obj=etp_f, alignment=16)
        recalculate_headers(file_obj=etp_f)


def get_duplicate_offsets_4(src_etp: str):
    basename = os.path.basename(src_etp)
    with open(f"../dump_etps/etps/{basename}", "rb") as f:
        indx_start = 96
        f.seek(indx_start)
        indx_header = f.read(20)

        short_id_count   = unpack("<H", indx_header[0:2])[0]
        short_off_count  = unpack("<H", indx_header[2:4])[0]
        long_str_start   = unpack("<I", indx_header[8:12])[0]
        short_off_start  = unpack("<I", indx_header[12:16])[0]
        long_off_start   = unpack("<I", indx_header[16:20])[0]

        long_id_count  = (short_off_start - long_str_start) // 4
        total_id_count = short_id_count + long_id_count

        # read 2-byte string IDs
        f.seek(indx_start + 20)
        all_str_ids = [unpack("<H", f.read(2))[0] for _ in range(short_id_count)]

        # read 4-byte string IDs (empty section when all IDs fit in a ushort)
        f.seek(indx_start + long_str_start)
        all_str_ids += [unpack("<I", f.read(4))[0] for _ in range(long_id_count)]

        # read short (2-byte) offsets
        f.seek(indx_start + short_off_start)
        all_offsets = [unpack("<H", f.read(2))[0] for _ in range(short_off_count)]

        # read long (4-byte) offsets
        f.seek(indx_start + long_off_start)
        all_offsets += [unpack("<I", f.read(4))[0] for _ in range(total_id_count - short_off_count)]

        # associate offset <-> str_id to find duplicates.
        # the offsets themselves are irrelevant for packing because our data will have
        # different offsets, so just group the string ids together to get the duplicates.
        offset_dict = {}
        for str_id, offset in zip(all_str_ids, all_offsets):
            if offset in offset_dict:
                offset_dict[offset].append(str_id)
            else:
                offset_dict[offset] = [str_id]

        return list(offset_dict.values())


def build_etp_4(json_list: list, src_etp: str):
    "Builds an ETP file for file version 4."
    with open(src_etp, "rb") as f:
        orig_etp_data = f.read(116)
        f.seek(96)
        orig_indx_table = f.read(unpack("<I", orig_etp_data[88:92])[0])

    indx_header = orig_indx_table[:20]
    str_table_size  = unpack("<H", indx_header[0:2])[0] * 2
    long_str_start  = unpack("<I", indx_header[8:12])[0]
    short_off_start = unpack("<I", indx_header[12:16])[0]

    # 2-byte and 4-byte string ID sections — copied unchanged from original
    short_string_table = orig_indx_table[20:20+str_table_size]
    long_string_table  = orig_indx_table[long_str_start:short_off_start]

    etp_file = os.path.basename(src_etp)
    with open(f"new_etp/{etp_file}", "w+b") as etp_f:
        # write beginning of file (includes the 20-byte INDX sub-header verbatim;
        # bytes 8-15 describe string ID section positions which stay the same since
        # we copy both string tables unchanged)
        etp_f.write(orig_etp_data)

        dupe_string_list = get_duplicate_offsets_4(src_etp)
        str_text, str_bytes = build_string_table_4(json_list=json_list, dupe_string_list=dupe_string_list)

        # write 2-byte string ID table
        etp_f.write(short_string_table)

        # align to 4 bytes with CD AB if needed
        if etp_f.tell() % 4 != 0:
            etp_f.write(b"\xCD\xAB")

        # write 4-byte string ID table (empty for files where all IDs fit in a ushort)
        etp_f.write(long_string_table)

        # record where the offset table starts (after both string ID sections)
        off_table_start = etp_f.tell()

        # iterate all string IDs in order: 2-byte first, then 4-byte
        all_string_ids = [s[0] for s in iter_unpack("<H", short_string_table)]
        all_string_ids += [s[0] for s in iter_unpack("<I", long_string_table)]

        wrote_offset_divider = False
        strings_written = 0
        short_offset_end = 0
        wrote_cdab = False
        for s_id in all_string_ids:
            find_dupe = search_sublist(str_id_list=dupe_string_list, search_id=s_id)[0]
            result = str_text[str(find_dupe)]

            # write in shorts until we encounter our first uint
            if result["new_offset"] <= 65535 and not wrote_offset_divider:
                etp_f.write(pack_ushort(result["new_offset"]))
                strings_written += 1
            else:
                # hit our first uint. split the table up
                if not wrote_offset_divider:
                    short_offset_end = etp_f.tell()
                    if etp_f.tell() % 4 != 0:
                        etp_f.write(b"\xCD\xAB")
                        wrote_cdab = True
                    wrote_offset_divider = True
                # hit an int that is too large to fit in a short. this table
                # will have a 4 byte offset section in the indx table.
                etp_f.write(pack_uint(result["new_offset"]))
                strings_written += 1

        # if table is not 4 byte aligned, need to add "CD AB" bytes to make it so
        etp_f.seek(0, 2)
        if etp_f.tell() % 4 != 0:
            etp_f.write(b"\xCD\xAB")

        if not short_offset_end:
            short_offset_end = etp_f.tell()

        align_file(file_obj=etp_f, alignment=16)
        end_of_indx = etp_f.tell()

        # update bytes 2-3: count of short offsets
        short_offset_count = int((short_offset_end - off_table_start) / 2)
        etp_f.seek(98)
        etp_f.write(pack_ushort(short_offset_count))

        # update bytes 16-19: start of long offset table (= end of short offsets + any CD AB)
        long_offset_start = short_offset_end - 96
        if wrote_offset_divider and wrote_cdab:
            long_offset_start += 2
        etp_f.seek(112)
        etp_f.write(pack_uint(long_offset_start))

        new_indx_size = end_of_indx - 96
        etp_f.seek(88)
        etp_f.write(pack_uint(new_indx_size) + b"\x00\x00\x00\x00")
        etp_f.seek(0, 2)
        write_foot(file_obj=etp_f)
        write_text(file_obj=etp_f)
        etp_f.write(str_bytes)
        align_file(file_obj=etp_f, alignment=16)
        recalculate_headers(file_obj=etp_f)

        total_ids = len(short_string_table) // 2 + len(long_string_table) // 4
        if total_ids != strings_written:
            print(f"ERROR: File {etp_file} did not write correct amount of strings. Expected: {total_ids}, Actual: {strings_written}")


def build_etp(json_file: list, src_etp: str):
    builders = {
        0: build_etp_0_2,
        2: build_etp_0_2,
        1: build_etp_1,
        4: build_etp_4,
    }
    file_version = determine_etp_version(file=src_etp)
    if not file_version:
        print("Not an ETP file.")
        return
    builder = builders.get(file_version)
    if builder is None:
        print(f"ETP version \"{file_version}\" is not currently supported.")
        return
    etp_json = read_json_file(file=json_file)
    builder(json_list=etp_json, src_etp=src_etp)


def build_all():
    json_files = glob.glob("new_json/en/*.json")
    for json_file in json_files:
        etp = os.path.basename(json_file).replace(".json", ".etp")
        print(f"Packing {etp}.")
        etp_file = f"../dump_etps/etps/{etp}"
        build_etp(json_file=json_file, src_etp=etp_file)


def recrypt_file(file: str):
    db_path = "../import_sql/dat_db.db"
    db_conn = sqlite3.connect(db_path)
    db_cur = db_conn.cursor()
    file = os.path.basename(file)
    encrypted_file = db_cur.execute(
        "SELECT file, blowfish_key FROM files WHERE blowfish_key IS NOT NULL AND file = ?",
        (file,)
    )
    result = encrypted_file.fetchone()
    if result:
        if os.path.exists(f"new_etp/{file}"):
            agent = attach_client()
            encrypt(agent=agent, filepath=f"new_etp/{file}", encryption_key=result[1])
            os.replace(src=f"new_etp/{file}.enc", dst=f"new_etp/{file}")
            agent.detach_game()
    else:
        print(f"{file} was either not originally encrypted or there isn't a stored blowfish key for it in the database.")


def recrypt_files():
    db_path = "../import_sql/dat_db.db"
    db_conn = sqlite3.connect(db_path)
    db_cur = db_conn.cursor()
    encrypted_files = db_cur.execute("SELECT file, blowfish_key FROM files WHERE blowfish_key IS NOT NULL")
    for file in encrypted_files.fetchall():
        etp_file = file[0]
        recrypt_file(etp_file)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Read a JSON file dumped by this program and rebuild into an ETP file.")
    parser.add_argument("-e", "--etp-file", type=str, help="Path to ETP file.")
    parser.add_argument("-j", "--json-file", type=str, help="Path to translated JSON file.")
    parser.add_argument("-a", "--pack-all", action="store_true", help="Pack all JSON files dumped by this program into ETP. Before using this flag, ensure you haven't changed any names.")
    parser.add_argument("-r", "--recrypt", action="store_true", help="Recrypt files. DQX must be open. This only works when used with (-e and -j) or (-a).")
    args = parser.parse_args(args=None if sys.argv[1:] else ["--help"])

    os.makedirs("new_etp", exist_ok=True)

    if args.pack_all:
        build_all()
        if args.recrypt:
            recrypt_files()
    else:
        if not (args.etp_file and args.json_file):
            parser.print_help()
            sys.exit(1)
        build_etp(json_file=args.json_file, src_etp=args.etp_file)
        if args.recrypt:
            file = os.path.basename(args.etp_file)
            recrypt_file(file=f"new_etp/{file}")
