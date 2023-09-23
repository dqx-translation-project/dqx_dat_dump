import pathlib
import sys
import zlib
sys.path.append("../../")  # hack to use tools
from tools.py_globals import ORIG_NUM_DATS, PROJECT_ROOT
from tools.lib.fileops import pack_uint, pack_ushort


class DatFile:
    """
    Manages a custom dat file.
    """
    def __init__(self, file: str):
        """
        :param dat_file: Absolute path to the dat file.
        """
        self.dat_file = file
        self.idx_file = "/".join([PROJECT_ROOT, pathlib.Path(self.dat_file).stem + ".idx"])


    def __generate_chunk_list_from_file(self, file: str):
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


    def __calculate_new_offset(self, offset: int, dat_num: int):
        new_offset = offset // 8 | dat_num << 1
        return pack_uint(new_offset)


    def __calculate_padding(self, offset: int):
        "Return padding for 0x80 file alignment."
        padding = 0
        while True:
            if offset % 128 == 0:
                break
            else:
                offset += 1
                padding += 1
        return bytes(padding)


    def __compress_chunk(self, chunk: bytes):
        return zlib.compress(chunk, level=9, wbits=-15)


    def __generate_dat_entry(self, uncomp_len: int, file_chunk_list: list):
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
        padding = self.__calculate_padding(len(block_table))
        block_table.extend(padding)

        # iterate over file_chunk_list, building our chunks
        block_offsets = []
        offset_start = len(block_table)
        for block in file_chunk_list:
            # get the current offset of the file and write to list for updating the data entry header
            offset_position = len(block_table) - offset_start

            # compress the chunk first to get the compressed size.
            compressed_chunk = self.__compress_chunk(block)

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
            alignment = self.__calculate_padding(len(block_table))
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


    def write_to_dat(self, idx_offset: int, file: str):
        """
        Writes a new file to a dat and overwrites the idx entry to point to the new dat offset.

        :param idx_offset: Offset of the record in the idx file that points to the file you're overwriting.
        :param file: Path to the file you want to write to the dat.
        """
        # split the file into chunks and generate our dat entry
        chunked_data = self.__generate_chunk_list_from_file(file)
        dat_data_to_write = self.__generate_dat_entry(uncomp_len=chunked_data[1], file_chunk_list=chunked_data[0])

        with open(self.idx_file, "r+b") as idx_f:
            idx_f.seek(idx_offset + 8)  # jump straight to where the offset needs to be written

            with open(self.dat_file, "r+b") as dat_f:
                dat_f.seek(0, 2)
                pos = dat_f.tell()

                # fix byte alignment before we write. eof on dats are not always 0x80 byte aligned
                padding = self.__calculate_padding(dat_f.tell())
                if padding:
                    dat_f.write(padding)

                # gather new offset to tell the idx file where this entry will live
                new_dat_offset = self.__calculate_new_offset(
                    offset=dat_f.tell(),
                    dat_num=int(self.dat_file[-1])
                )

                # write new file entry at end of dat
                dat_f.write(dat_data_to_write)

            # update indx with new position
            idx_f.write(new_dat_offset)

            print(f"Wrote {file} to offset {pos}.")
