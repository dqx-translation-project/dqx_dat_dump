import glob
import os
import sqlite3
import sys
import zlib
sys.path.append("../../")  # hack to use tools
from tools.idx_searcher.main import find_file
from tools.globals import GAME_DATA_DIR
from tools.lib.fileops import (
    pack_uint,
    pack_ushort
)

DB_PATH = "../import_sql/dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def get_record(etp_file: str):
    DB_CUR.execute(f'SELECT file_dir_hash, blowfish_key FROM files WHERE file = "{etp_file}" OR clarity_name = "{etp_file}"')
    result = DB_CUR.fetchone()
    if result:
        return result[0], result[1]
    return None


def get_idx_offset(idx_file: str, file_dir_hash: str):
    byte_search = bytearray.fromhex(file_dir_hash)
    idx_path = "/".join([GAME_DATA_DIR, idx_file])
    with open(idx_path, "rb") as f:
        data = f.read()
    offset = data.find(byte_search)
    if offset == -1:
        return None
    return offset


def calculate_new_offset(offset: int, dat_num: int):
    new_offset = offset // 8 | dat_num << 1
    return pack_uint(new_offset)


def calculate_padding(offset: int):
    "Return padding for 0x80 file alignment."
    padding = 0
    while True:
        if offset % 128 == 0:
            break
        else:
            offset += 1
            padding += 1
    return bytes(padding)


def get_current_offset(offset: int):
    return (offset & ~0xF) * 0x08


def compress_chunk(chunk: bytes):
    return zlib.compress(chunk, level=9, wbits=-15)


def generate_chunk_list(file: str):
    """
    Breaks up a file into chunk_len sized chunks.

    :param file: File to read to break into chunks.
    :returns: A tuple of chunk_list and the length of the uncompressed data.
    """
    with open(file, "rb") as f:
        uncomp_data = f.read()

    chunk_len = 64000
    chunk_list = []

    for i in range(0, len(uncomp_data), chunk_len):
        chunk_list.append(uncomp_data[i : i + chunk_len])

    return chunk_list, len(uncomp_data)


def generate_dat_entry(uncomp_len: int, file_chunk_list: list):
    """
    Creates a dat entry from an uncompressed chunk list.

    :param uncomp_len: Uncompressed length of bytes of the entire file_chunk_list
    :param file_chunk_list: A list of chunks of the file to generate for
    :returns: A bytearray of the dat entry. This should be written to a dat file.
    """
    block_table = bytearray()

    # these are in order of the block table in the dat file
    header_length = pack_uint(0)  # we don't know this yet, but we'll update it later. this is beginning of header to end of padding
    file_type = pack_uint(2)  # should always be 2 for our purposes
    uncomp_length = pack_uint(uncomp_len)  # total actual file size
    unk_value = pack_uint(0)  # dunno what this value is, but making it 0 still allows it to load.
    max_buffer_size = pack_uint(60000)  # _seems_ arbitrary. this must be the same value as the largest chunk
    num_blocks = pack_uint(len(file_chunk_list))  # we don't know what the offsets are yet, but we do know how many blocks there will be.

    # put what we know so far together
    block_table.extend(header_length)
    block_table.extend(file_type)
    block_table.extend(uncomp_length)
    block_table.extend(unk_value)
    block_table.extend(max_buffer_size)
    block_table.extend(num_blocks)

    # append the data we would use for the blocks
    for i in range(len(file_chunk_list)):
        block_table.extend(b"\x00\x00\x00\x00") # offset currently unknown
        block_table.extend(b"\x00\x00") # block size currently unknown, but spans from beginning of block header to end of padding
        block_table.extend(b"\x00\x00") # decompressed size, will come back to this later
    padding = calculate_padding(len(block_table))
    block_table.extend(padding)

    # iterate over file_chunk_list, building our chunks
    block_offsets = []
    offset_start = len(block_table)
    for block in file_chunk_list:
        # get the current offset of the file and write to list for updating the data entry header
        offset_position = len(block_table) - offset_start

        # compress the chunk first to get the compressed size.
        compressed_chunk = compress_chunk(block)

        # build the block header
        header_length = pack_uint(16)
        padding = pack_uint(0)
        compressed_length = pack_uint(len(compressed_chunk))
        uncompressed_length = pack_uint(len(block))

        # append block header
        block_table.extend(header_length)
        block_table.extend(padding)
        block_table.extend(compressed_length)
        block_table.extend(uncompressed_length)

        # append block data
        block_table.extend(compressed_chunk)

        # get padding for alignment and append
        alignment = calculate_padding(len(block_table))
        block_table.extend(alignment)

        # get the total size of everything we wrote
        block_size = len(header_length) + len(padding) + len(compressed_length) + len(uncompressed_length) + len(compressed_chunk) + len(alignment)

        # append the offset and size to our block_offsets list for updating the data entry header
        block_offsets.append(
            {
                "offset": offset_position,
                "block_size": block_size,
                "decompressed_size": len(block)
            }
        )

    # at this point, all of our data is in block_table. now we need to go back to the beginning
    # and update our offsets to tell the data entry header where all of these files are.
    block_table[0:4] = pack_uint(offset_start)  # update the data entry header with the size

    # iterate over the block_offsets list to update the offsets in the data entry header
    block_offset_start = 24
    for block in block_offsets:
        block_table[ block_offset_start : block_offset_start + 4 ] = pack_uint(block["offset"])
        block_offset_start += 4
        block_table[ block_offset_start : block_offset_start + 2 ] = pack_ushort(block["block_size"])
        block_offset_start += 2
        block_table[ block_offset_start : block_offset_start + 2 ] = pack_ushort(block["decompressed_size"])
        block_offset_start += 2

    return block_table


def create_new_dat(idx_file: str, dat_num: str):
    """
    Create a new dat ("dat1") to store the ETPs.

    :param idx_file: Filename of the idx file.
    :param dat_num: Number of the new dat to write.
    """
    orig_dat_name = idx_file.replace(".idx", f".dat0")
    new_dat_name = idx_file.replace(".idx", f".dat{dat_num}")

    with open(orig_dat_name, "rb") as f:
        dat_header = f.read(2048)

    with open(new_dat_name, "w+b") as f:
        f.write(dat_header)


def update_idx_dat_count(num_dats: int):
    """
    Opens the data00000000.win32.idx file and updates the number of dats to read.
    """
    with open(f"{GAME_DATA_DIR}/data00000000.win32.idx", "r+b") as f:
        f.seek(1104)
        f.write(pack_uint(num_dats))


def write_to_dat(idx_file: str, idx_offset: int, file: str, dat_num: str):
    """
    Writes a new file to a dat and overwrites the idx entry to point to the new dat offset.

    :param idx_file: Filename of the idx file.
    :param idx_offset: Offset of the record in the idx file that points to the file you're overwriting.
    :param file: File you want to write to the dat.
    :param dat_num: Number of the new dat to write.
    """
    # split the file into chunks and generate our dat entry
    chunked_data = generate_chunk_list(file)
    dat_data_to_write = generate_dat_entry(uncomp_len=chunked_data[1], file_chunk_list=chunked_data[0])

    path_to_idx = "/".join([GAME_DATA_DIR, idx_file])
    with open(path_to_idx, "r+b") as idx_f:

        # jump straight to where the offset needs to be written
        idx_f.seek(idx_offset + 8)

        # TODO: need to come back here and support writing to other dat files at a later time
        dat_file = idx_file.replace(".idx", f".dat{dat_num}")
        path_to_dat = "/".join([GAME_DATA_DIR, dat_file])

        with open(path_to_dat, "r+b") as dat_f:
            dat_f.seek(0, 2)
            pos = dat_f.tell()

            # fix byte alignment before we write. eof on dats are not always 0x80 byte aligned
            padding = calculate_padding(dat_f.tell())
            if padding:
                dat_f.write(padding)

            # gather new offset to tell the idx file where this entry will live
            new_dat_offset = calculate_new_offset(offset=dat_f.tell(), dat_num=int(dat_num))

            # write new file entry at end of dat
            dat_f.write(dat_data_to_write)

        # update indx with new position
        idx_f.write(new_dat_offset)

        print(f"Wrote {file} to offset {pos}.")


def write_etps():
    etp_files = glob.glob("new_etp/*.etp")
    rps_files = glob.glob("new_rps/*.rps")
    files_to_pack = etp_files + rps_files

    create_new_dat(
        idx_file=f"{GAME_DATA_DIR}/data00000000.win32.idx",
        dat_num="1"
    )

    update_idx_dat_count(num_dats=2)

    for file in files_to_pack:
        basename = os.path.basename(file)
        db_result = get_record(etp_file=basename)
        if not db_result:
            print(f"Did not find {basename} in the database. Skipping.")
            continue
        file_dir_hash = db_result[0]

        try:
            idx_loc = find_file(filename=file_dir_hash)
        except Exception as e:
            print(
                f"Could not find hash in any idx files for file {file}. Skipping. Error: {e}"
            )
            continue

        write_to_dat(
            idx_file=idx_loc["idx"],
            idx_offset=idx_loc["idx_offset"],
            file=file,
            dat_num="1"
        )

write_etps()
