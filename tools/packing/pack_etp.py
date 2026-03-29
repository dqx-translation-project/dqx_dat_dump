import argparse
import glob
import json
import os
import sqlite3
import sys
from struct import iter_unpack, pack, unpack

sys.path.append("../../")  # hack to use tools
from tools.dump_etps.dqxcrypt.dqxcrypt import attach_client, encrypt
from tools.lib.fileops import (
    pack_uint,
    pack_ushort,
    unpack_uint,
    unpack_ushort,
    write_foot,
    write_text,
    write_toof,
    write_txet,
)


def read_json_file(file: str):
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)


def align_file(file_obj: object, alignment: int):
    """Add padding to end of file until its size is divisible by alignment."""
    pos = file_obj.seek(0, 2)
    pad = (-pos) % alignment
    if pad:
        file_obj.write(b"\x00" * pad)


def determine_etp_version(file: str):
    with open(file, "rb") as f:
        magic = unpack("4s", f.read(4))[0]
        if magic == b"XTVE":
            return "be"
        elif magic != b"EVTX":
            return None
        f.read(11)
        version = f.read(1)
    return int(version.hex())


def _pick_translation(record: dict) -> bytes:
    """Returns the translated string (en) if available, otherwise the source (ja), as null-terminated UTF-8 bytes."""
    ja, en = next(iter(record.items()))
    return bytes(en if en else ja, encoding="utf-8") + b"\x00"


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


def _build_string_table(json_list: list, start_offset: int = 0, dupe_string_list: list = None):
    """
    Builds a string table from json_list.
    Returns a mapping of original str_id -> new character offset, and the packed string bytes.

    start_offset: character offset for the first string (1 for v1, 0 for v4).
    dupe_string_list: groups of string IDs sharing the same offset (v4 only).
                      Secondary IDs in each group reuse the primary's offset.
    """
    final_bytes = bytearray()
    offset_data = {}

    # precompute lookup to avoid O(n) search per string ID
    dupe_lookup = (
        {sid: sublist for sublist in dupe_string_list for sid in sublist}
        if dupe_string_list is not None else None
    )

    for str_id in json_list:
        # v4: if multiple string IDs share an offset, only the first gets a new entry;
        # the rest reference the primary occurrence's offset.
        if dupe_lookup is not None:
            sublist = dupe_lookup.get(int(str_id), [int(str_id)])
            if len(sublist) > 1 and int(str_id) != sublist[0]:
                offset_data[str_id] = offset_data[str(sublist[0])]
                continue

        str_bytes = _pick_translation(json_list[str_id])
        # ensures the string (including null terminator) has an even number of bytes
        if len(str_bytes) % 2 != 0:
            str_bytes += b"\x00"
        offset_data[str_id] = len(final_bytes) // 2 + start_offset
        final_bytes += str_bytes

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
    text_size = file_obj.seek(0, 2) - text_start
    file_obj.seek(text_start - 16 + 8)  # -16 to get to beginning of TEXT and +8 to jump to size. easier to read this way
    file_obj.write(pack_uint(text_size) + b"\x00\x00\x00\x00")
    file_obj.seek(0, 2)
    write_foot(file_obj=file_obj)

    # calculate new size for blja header
    blja_size = file_obj.seek(0, 2) - 80
    file_obj.seek(72)
    file_obj.write(pack_uint(blja_size))
    file_obj.seek(0, 2)
    write_foot(file_obj=file_obj)

    # calculate new size for evtx header
    evtx_size = file_obj.seek(0, 2) - 16
    file_obj.seek(8)
    file_obj.write(pack_uint(evtx_size))
    file_obj.seek(0, 2)
    write_foot(file_obj=file_obj)


def _recalculate_headers_be(file_obj: object):
    "Update header lengths and add TOOFs to end of file (big-endian)."
    # update TXET sizing
    file_obj.seek(88)
    indx_size = unpack(">I", file_obj.read(4))[0]
    file_obj.read(4)  # read past padding
    file_obj.read(indx_size)
    file_obj.read(16)  # read past TOOF
    file_obj.read(16)  # read past TXET header
    text_start = file_obj.tell()
    text_size = file_obj.seek(0, 2) - text_start
    file_obj.seek(text_start - 16 + 8)
    file_obj.write(pack(">I", text_size) + b"\x00\x00\x00\x00")
    file_obj.seek(0, 2)
    write_toof(file_obj=file_obj)

    # calculate new size for ajlb header
    blja_size = file_obj.seek(0, 2) - 80
    file_obj.seek(72)
    file_obj.write(pack(">I", blja_size))
    file_obj.seek(0, 2)
    write_toof(file_obj=file_obj)

    # calculate new size for xtve header
    evtx_size = file_obj.seek(0, 2) - 16
    file_obj.seek(8)
    file_obj.write(pack(">I", evtx_size))
    file_obj.seek(0, 2)
    write_toof(file_obj=file_obj)


def _build_etp_event_text(json_list: list, src_etp: str):
    "Builds an ETP file for file versions 0 and 2."
    # grab original file header data we'll copy over to new file
    with open(src_etp, "rb") as f:
        orig_etp_data = f.read(96)
        indx_size = unpack_uint(orig_etp_data[88:92])
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
            etp_f.seek(96 + curr_indx_pos + 4) # jump past string_id and get to text offset
            etp_f.write(pack_uint(text_offset)) # update the new offset
            etp_f.seek(0, 2) # position pointer back to end of file to write text
            etp_f.write(_pick_translation(json_list[str(string_id)]))
            curr_indx_pos += 8
        align_file(file_obj=etp_f, alignment=16)
        recalculate_headers(file_obj=etp_f)


def _build_etp_sub_package(json_list: list, src_etp: str):
    "Builds an ETP file for file version 1 (LE) or BE."
    with open(src_etp, "rb") as f:
        is_be = f.read(4) == b"XTVE"

    if is_be:
        # BE file layout: (string_id: uint32_BE, byte_offset: uint32_BE) pairs in INDX.
        # Text body is UTF-8 null-terminated strings; offsets are direct byte offsets.
        with open(src_etp, "rb") as f:
            orig_etp_data = f.read(96)
            indx_size = unpack(">I", orig_etp_data[88:92])[0]
            orig_indx = f.read(indx_size)
            f.read(32)  # skip TOOF + TXET header
            text_pos = f.tell()
            # pre-read all original strings for fallback when a string_id is absent from json_list
            orig_strings = {}
            for sid, off in iter_unpack(">II", orig_indx):
                if sid == 0:
                    continue
                f.seek(text_pos + off)
                buf = bytearray()
                while True:
                    ch = f.read(1)
                    if ch == b"\x00":
                        break
                    buf.extend(ch)
                orig_strings[sid] = buf.decode("utf-8")

        str_bytes = bytearray()
        orig_offset_to_new = {}  # deduplication: orig_byte_offset -> new_byte_offset
        new_indx = bytearray()

        for string_id, orig_offset in iter_unpack(">II", orig_indx):
            if string_id == 0:
                new_indx += pack(">II", 0, 0)
                continue
            if orig_offset in orig_offset_to_new:
                new_offset = orig_offset_to_new[orig_offset]
            else:
                new_offset = len(str_bytes)
                orig_offset_to_new[orig_offset] = new_offset
                str_key = str(string_id)
                original = orig_strings.get(string_id, "")
                record = json_list.get(str_key)
                if record is not None and next(iter(record)) == original:
                    # source text in JSON matches original ETP string — use translation
                    str_bytes += _pick_translation(record)
                else:
                    # key absent or source text mismatch (wrong JSON) — use original
                    str_bytes += original.encode("utf-8") + b"\x00"
            new_indx += pack(">II", string_id, new_offset)

        etp_file = os.path.basename(src_etp)
        with open(f"new_etp/{etp_file}", "w+b") as etp_f:
            etp_f.write(orig_etp_data)
            etp_f.write(new_indx)
            write_toof(file_obj=etp_f)
            write_txet(file_obj=etp_f)
            etp_f.write(str_bytes)
            align_file(file_obj=etp_f, alignment=16)
            _recalculate_headers_be(file_obj=etp_f)
        return

    with open(src_etp, "rb") as f:
        orig_etp_data = f.read(96)
        offset_count = unpack_uint(orig_etp_data[44:48])  # get from cmnh
        indx_size = unpack_uint(orig_etp_data[88:92])
        orig_indx_table = f.read(indx_size)

    # Parse all original offsets upfront: short (2-byte) table first, then long (4-byte).
    # Mirrors the same approach used in _parse_etp_sub_package.
    short_count = unpack_ushort(orig_indx_table[2:4])
    short_table_end = 20 + short_count * 2
    short_offsets = [o for o, in iter_unpack("<H", orig_indx_table[20:short_table_end])]

    long_table_start = short_table_end
    if (long_table_start + 96) % 4 != 0:  # skip CD AB alignment bytes if present
        long_table_start += 2
    long_count = offset_count - short_count
    long_offsets = [o for o, in iter_unpack("<I", orig_indx_table[long_table_start:long_table_start + long_count * 4])]

    str_table, str_bytes = _build_string_table(json_list=json_list, start_offset=1)

    etp_file = os.path.basename(src_etp)
    with open(f"new_etp/{etp_file}", "w+b") as etp_f:
        etp_f.write(orig_etp_data)
        etp_f.write(orig_indx_table[:20])

        # Iterate all offsets in order (short then long). For each, look up its new value
        # and write as ushort or uint. The first time a new offset overflows ushort range,
        # record the split point and insert CD AB alignment bytes if needed.
        wrote_offset_divider = False
        end_of_short_pos = 0
        wrote_cdab = False

        for offset in short_offsets + long_offsets:
            if offset == 0:
                etp_f.write(b"\x00\x00" if not wrote_offset_divider else b"\x00\x00\x00\x00")
                continue

            new_offset_val = str_table[str(offset)]
            if new_offset_val <= 65535 and not wrote_offset_divider:
                etp_f.write(pack_ushort(new_offset_val))
            else:
                if not wrote_offset_divider:
                    end_of_short_pos = etp_f.tell()
                    if etp_f.tell() % 4 != 0:
                        etp_f.write(b"\xCD\xAB")
                        wrote_cdab = True
                    wrote_offset_divider = True
                etp_f.write(pack_uint(new_offset_val))

        if end_of_short_pos == 0:
            end_of_short_pos = etp_f.tell()

        if etp_f.tell() % 4 != 0:
            etp_f.write(b"\xCD\xAB")
            wrote_cdab = True
        align_file(file_obj=etp_f, alignment=16)
        end_of_indx = etp_f.tell()

        # update the value of the short table. if there is a "cd ab" value,
        # don't include this in the calculation
        etp_f.seek(98)
        etp_f.write(pack_uint((end_of_short_pos - 116) // 2))  # -116 to remove everything up to where offset starts

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
    with open(src_etp, "rb") as f:
        f.seek(96)
        indx_header = f.read(20)

        short_id_count   = unpack("<H", indx_header[0:2])[0]
        short_off_count  = unpack("<H", indx_header[2:4])[0]
        long_str_start   = unpack("<I", indx_header[8:12])[0]
        short_off_start  = unpack("<I", indx_header[12:16])[0]
        long_off_start   = unpack("<I", indx_header[16:20])[0]

        long_id_count  = (short_off_start - long_str_start) // 4
        total_id_count = short_id_count + long_id_count

        # read all string IDs and offsets as contiguous slices
        f.seek(96 + 20)
        short_ids_raw = f.read(short_id_count * 2)
        f.seek(96 + long_str_start)
        long_ids_raw = f.read(long_id_count * 4)
        f.seek(96 + short_off_start)
        short_offs_raw = f.read(short_off_count * 2)
        f.seek(96 + long_off_start)
        long_offs_raw = f.read((total_id_count - short_off_count) * 4)

        all_str_ids = [s for s, in iter_unpack("<H", short_ids_raw)]
        all_str_ids += [s for s, in iter_unpack("<I", long_ids_raw)]
        all_offsets = [o for o, in iter_unpack("<H", short_offs_raw)]
        all_offsets += [o for o, in iter_unpack("<I", long_offs_raw)]

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


def _build_etp_smldt_msg_pkg(json_list: list, src_etp: str):
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
        str_text, str_bytes = _build_string_table(json_list=json_list, dupe_string_list=dupe_string_list)

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

        dupe_lookup = {sid: sublist for sublist in dupe_string_list for sid in sublist}

        wrote_offset_divider = False
        short_offset_end = 0
        wrote_cdab = False
        for s_id in all_string_ids:
            find_dupe = dupe_lookup.get(s_id, [s_id])[0]
            new_offset_val = str_text[str(find_dupe)]

            # write in shorts until we encounter our first uint
            if new_offset_val <= 65535 and not wrote_offset_divider:
                etp_f.write(pack_ushort(new_offset_val))
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
                etp_f.write(pack_uint(new_offset_val))

        if not short_offset_end:
            short_offset_end = etp_f.tell()

        # if table is not 4 byte aligned, need to add "CD AB" bytes to make it so
        if etp_f.tell() % 4 != 0:
            etp_f.write(b"\xCD\xAB")

        align_file(file_obj=etp_f, alignment=16)
        end_of_indx = etp_f.tell()

        # update bytes 2-3: count of short offsets
        short_offset_count = (short_offset_end - off_table_start) // 2
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
        if total_ids != len(all_string_ids):
            print(f"ERROR: File {etp_file} did not write correct amount of strings. Expected: {total_ids}, Actual: {len(all_string_ids)}")


def build_etp(json_file: list, src_etp: str):
    builders = {
        0: _build_etp_event_text,
        2: _build_etp_event_text,
        1: _build_etp_sub_package,
        "be": _build_etp_sub_package,
        4: _build_etp_smldt_msg_pkg,
    }
    file_version = determine_etp_version(file=src_etp)
    if file_version is None:
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
