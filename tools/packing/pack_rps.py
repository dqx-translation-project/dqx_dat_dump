#
# This is specifically for
# packageManagerRegistIncludeAutoClient.rps.
#

import glob
import os
from struct import unpack, pack
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.fileops import (
    pack_uint,
    unpack_uint,
    read_cstr
)
from pathlib import Path


def get_alignment(file_version: int):
    if file_version >= 4103:
        alignment = 64
    elif file_version >= 4003:
        alignment = 32
    else:
        alignment = 1
    return alignment


def align_file(file_obj: object, alignment: int):
    """
    Add x99 padding to end of file
    until the number is divisible by alignment.
    """
    # add 00 padding to file to meet alignment needs.
    while True:
        eof = file_obj.seek(0, 2) / alignment
        check_int = float(eof).is_integer()
        if check_int:
            return True
        file_obj.write(b"\x99")


def get_alignment_count(integer: int, alignment: int):
    """
    Figure out how many additional bytes are needed
    to reach the alignment count.
    """
    added_count = 0
    orig_integer = integer
    while True:
        number = integer / alignment
        check_int = float(number).is_integer()
        if check_int:
            return int(orig_integer + added_count)
        integer += 1
        added_count += 1


def pack_etp_rps():
    with open("../dump_etps/rps/packageManagerRegistIncludeAutoClient.rps", "rb") as f:
        header_data = f.read(48)
        alignment = get_alignment(unpack_uint(header_data[8:12]))

        resource_count = unpack_uint(header_data[32:36])
        path_table_offset = unpack_uint(header_data[36:40])

        resource_size = 16
        resource_table = f.read(resource_count * resource_size)

        file_write_start = len(header_data) + len(resource_table) + 16

        entry_table_start = 0x30
        file_base_offset = (entry_table_start + (resource_size*resource_count) + alignment - 1) & ~(alignment - 1)

        # get all resource filenames in order
        f.seek(file_base_offset + path_table_offset, os.SEEK_SET)
        resource_names = []
        for i in range(resource_count):
            s = read_cstr(f)
            resource_names.append(s)

        # need to get the offset of the last real file resource in the table and copy the rest down.
        # this is basically saying to get the third last resource in the resource table, since the last two
        # are RESOURCE_ID and RESOURCE_TYPE, which are meta resources.
        resource_table_len = len(resource_table)
        last_entry = resource_table[resource_table_len-48:resource_table_len-32]
        entry_offset = unpack_uint(last_entry[4:8])
        entry_size = unpack_uint(last_entry[8:12])
        final_pos = file_write_start + entry_offset + entry_size

        resource_type = resource_table[resource_table_len-32:resource_table_len-16]
        resource_type_size = unpack_uint(resource_type[8:12])
        resource_id = resource_table[resource_table_len-16:]
        resource_id_size = unpack_uint(resource_id[8:12])

        # read all file data. will append all of this at the end of our new file.
        f.seek(final_pos)
        file_data = f.read()

    # create our new rps file here
    os.makedirs("new_rps", exist_ok=True)
    file_iter = 0
    last_pos = file_write_start
    offset_list = []
    with open("new_rps/packageManagerRegistIncludeAutoClient.rps", "w+b") as f:
        f.write(header_data)
        f.write(resource_table)
        f.write(b"\x00" * 16)
        for file in resource_names:
            if file in ["RESOURCE_TYPE", "RESOURCE_ID"]:  # not real files, just have entries in resource table
                continue
            file_path = glob.glob(f"../dump_etps/rps/packageManagerRegistIncludeAutoClient_rps/{file}*")
            file_basename = os.path.basename(file_path[0])
            file_ext = os.path.splitext(file_path[0])[1]
            if file_ext == ".etp":
                new_file_path = f"new_etp/{file_basename}"
            elif file_ext == ".cry" and Path(f"new_etp/{file_basename}").exists():
                new_file_path = f"new_etp/{os.path.splitext(file_basename)[0]}"  # remove .cry extension
            else:
                new_file_path = f"../dump_etps/rps/packageManagerRegistIncludeAutoClient_rps/{file_basename}"


            # there may be an ETP or two that we don't move to "new_etp" because we don't support
            # dumping them. these are typically old wii files that are still packaged with the game.
            # grab them from the original dump etp folder if we encounter them
            try:
                with open(new_file_path, "rb") as new_f:
                    data = new_f.read()
            except:
                print(f"Did not find {file_basename} in new_etp. Using dumped version instead.")
                new_file_path = new_file_path.replace("new_etp/", f"../dump_etps/etps/")
                with open(new_file_path, "rb") as new_f:
                    data = new_f.read()

            offset_list.append({file_iter: [{"offset": (f.tell() - file_write_start)}, {"size": 0}]})
            f.write(data)

            # file must be aligned with x99 bytes
            align_file(file_obj=f, alignment=alignment)

            # get new size of each file and write to offset_list
            offset_list[file_iter][file_iter][1]["size"] = f.tell() - last_pos

            file_iter += 1
            last_pos = f.tell()

        eof_pos = f.tell()

        # write the end of the original file data
        f.write(file_data)

        # need to update the resource_id location in the SEDBRES header.
        new_resource_type_loc = eof_pos - ((resource_count + 1) * resource_size) - len(header_data)
        new_resource_id_loc = new_resource_type_loc + resource_type_size
        new_path_table_offset = new_resource_id_loc + resource_id_size

        # update new path table offset location
        f.seek(36)
        f.write(pack_uint(new_path_table_offset))

        # update the resource table with the new offsets we wrote using the
        # offset_list we generated
        f.seek(48)
        for i in range(resource_count - 2):
            (index, offset, size, flags) = unpack("<IIII", f.read(16))
            new_offset = offset_list[i][i][0]["offset"]
            new_size = offset_list[i][i][1]["size"]
            f.seek(-12, 1)
            f.write(pack("<II", new_offset, new_size))
            f.seek(4, 1)

        # update the RESOURCE_TYPE
        for i in range(1):
            (index, offset, size, flags) = unpack("<IIII", f.read(16))
            f.seek(-12, 1)
            f.write(pack_uint(new_resource_type_loc))
            f.seek(8, 1)

        # update the RESOURCE_ID
        for i in range(1):
            (index, offset, size, flags) = unpack("<IIII", f.read(16))
            f.seek(-12, 1)
            f.write(pack_uint(new_resource_id_loc))
            f.seek(8, 1)

        # update the new total file size
        f.seek(0, 2)
        total_size = pack_uint(f.tell())
        f.seek(16)
        f.write(total_size)


pack_etp_rps()
