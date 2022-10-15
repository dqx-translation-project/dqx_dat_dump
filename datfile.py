from struct import unpack
from zlib import decompress


class DatEntry:
    def __init__(self, dat_file: str, offset: int):
        self.dat_file = dat_file
        self.offset = offset

        self.block_table = self.block_table(offset=self.offset)

    def block_table(self, offset: int):
        with open(self.dat_file, "rb") as f:
            f.seek(offset)
            data = unpack("<I I I I I I", f.read(24))

            blocks = []
            table = {
                "length": data[0],
                "type": data[1],  # 0x01 - Empty, 0x02 - Binary, 0x03 - Model, 0x04 - Texture
                "uncomp_size": data[2],
                "unknown": data[3],
                "block_buffer_size": data[4],  # buffer size needed to read largest block
                "num_blocks": data[5],
                "blocks": blocks
            }

            count = 0
            while count < table["num_blocks"]:
                data = unpack("<I H H", f.read(8))
                block = {
                    "offset": data[0],
                    "size": data[1],
                    "decomp_size": data[2],
                    "start_loc": offset + table["length"] + data[0]
                }

                blocks.append(block)
                count += 1
            
            if table["num_blocks"] == len(table["blocks"]):
                return table

            return None

    def data(self):
        with open(self.dat_file, "rb") as f:
            blocks = self.block_table["blocks"]
            game_data = b""
            for block in blocks:
                f.seek(block["start_loc"])
                header = unpack("<I 4x I I", f.read(16))

                h_length = header[0]
                comp_length = header[1]
                uncomp_length = header[2]

                if comp_length == 128000:  # file is not actually compressed, just read decompressed bytes
                    game_data = game_data + f.read(uncomp_length)
                else:
                    result = f.read(comp_length)
                    game_data = game_data + decompress(result, wbits=-15)

        if game_data:
            return game_data
        return False
