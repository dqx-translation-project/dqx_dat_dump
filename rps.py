import os
from struct import unpack

HEADER_SIZE = 0x30

class RpsFile:
    def __init__(self, file: str):
        self.file = file
        self.output_folder = file.rsplit("\\", 1)[0] + "\\" + file.split("\\")[-1].replace(".", "_")

        with open(file, "rb") as f:
            file_data = f.read()
        
        self.header = self.header(
            buf=file_data[0:HEADER_SIZE])
        self.index_table = self.index_table(
            buf=file_data[HEADER_SIZE:])

    # this is a best effort guess, but the important stuff is here.
    def header(self, buf):
        data = unpack("<8s I I I 12x I I I 4c", buf)

        header = {
            "magic": data[0],
            "unk_1": data[1],  # always \xA4\x0F\x00\x00
            "unk_2": data[2],  # always \x00\x04\x20\x00
            "file_size": data[3],  # num bytes in file
            "num_files": data[4],
            "data_size": data[5],
            "num_files_2": data[6],  # num files a second time?
            "file_ext": data[7][::-1].decode(),  # always equals \x73\x70\x72\x00 ("spr", which is "rps")
            "data_start": 48 + (data[4] * 16) + 16  # end of index table is usually padded with 16 nulls
        }

        return header

    def index_table(self, buf):
        position = 0
        rows = []

        table = {
            "rows": rows
        }

        for count in range(self.header["num_files"]):
            data = unpack("<I I I I", buf[position:position+16])
            row = {
                "count": data[0],
                "offset": data[1],
                "length": data[2],
                "unk": data[3],  # always \x01\x00\x00\x00
            }

            rows.append(row)
            position += 16

        # i don't know why, but sometimes you don't see the table extended by 16 bytes.
        # we need to check if the last row is padded by 16 bytes of nulls or not.
        prev_entry = self.header["num_files"] * 16

        if buf[prev_entry:prev_entry+16] != b"\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00":
            self.header.update({"data_start": self.header["data_start"] - 16})

        return table

    def dump(self):
        pos_start = self.header["data_start"]
        for file in self.index_table["rows"]:
            with open(self.file, "rb") as f:
                file_pos = pos_start + file["offset"]
                f.seek(file_pos)
                data = f.read(file["length"])

                # write file
                os.makedirs(self.output_folder, exist_ok=True)
                with open(f"{self.output_folder}/{file['count']}", "bw+") as f2:
                    f2.write(data)

    # todo: filenames and file extensions are at the last two rows in the index table.
    # read them backwards to figure out how to name them
