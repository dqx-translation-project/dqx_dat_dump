import os
from struct import unpack
from .extensions import EXTENSIONS

HEADER_SIZE = 0x30


class RpsFile:
    def __init__(self, file: str):
        self.file = file
        self.output_folder = file.rsplit("\\", 1)[0] + "\\" + file.split("\\")[-1].replace(".", "_")

        with open(file, "rb") as f:
            file_data = f.read()

        if file_data[0:8] != b"\x53\x45\x44\x42\x52\x45\x53\x20":  # SEDBRES
            raise(f"{file} is not an RPS file!")

        self.header = self.header(
            buf=file_data[0:HEADER_SIZE])
        self.index_table = self.index_table(
            buf=file_data[HEADER_SIZE:])
        self.resource_names = self.resource_names(
            buf=file_data)
        self.resource_types = self.resource_types(
            buf=file_data)
        self.resource_ids = self.resource_ids(
            buf=file_data)
        self.__add_resources_to_indx()

    # this is a best effort guess, but the important stuff is here.
    def header(self, buf):
        data = unpack("<8s I B B H I I I I I I I 4s", buf)

        header = {
            "magic": data[0].decode(),
            "format_ver": data[1],
            "flags": data[2],
            "unk_1": data[3],
            "rps_info_offset": data[4],  # absolute offset in file of the info struct
            "file_size": data[5],
            "unk_2": data[6],
            "unk_3": data[7],
            "unk_4": data[8],

            # info struct
            "path_table_count": data[9],
            "path_table_offset": data[10],
            "entry_count": data[11],
            "db_type": data[12][::-1].lstrip(b'\x00').decode()
        }

        # Calculate the file_base_offset based on the alignment.
        # The alignment changes depending on the format version.
        entry_table_start = 0x30  # fixed
        entry_size = 16
        if header["format_ver"] >= 4103:
            alignment = 64
        elif header["format_ver"] >= 4003:
            alignment = 32
        else:
            alignment = 1

        file_base_offset = (entry_table_start + (entry_size*header["entry_count"]) + alignment - 1) & ~(alignment - 1)
        header.update({"file_base_offset": file_base_offset})

        return header


    def index_table(self, buf):
        position = 0
        rows = []

        table = {
            "rows": rows
        }

        for i in range(self.header["entry_count"]):
            data = unpack("<I I I I", buf[position:position+16])
            row = {
                "count": data[0],
                "offset": data[1],
                "length": data[2],
                "flags": data[3],
            }

            rows.append(row)
            position += 16

        return table


    def resource_names(self, buf):
        names = []
        pos = self.header["file_base_offset"] + self.header["path_table_offset"]
        for i in range(self.header["entry_count"]):
            name = ""
            while buf[pos:pos+1] != b"\x00":
                name = name + buf[pos:pos+1].decode()
                pos = pos + 1

            pos += 1
            names.append(name)

        return names


    def resource_types(self, buf):
        idx = self.resource_names.index("RESOURCE_TYPE")
        entry = self.index_table["rows"][idx]
        pos = self.header["file_base_offset"] + entry["offset"]
        types = []
        for i in range(self.header["entry_count"]):
            res_type = buf[pos:pos+4].decode("ascii")[::-1].strip("\x00")
            types.append(res_type)
            pos += 4

        return types


    def resource_ids(self, buf):
        idx = self.resource_names.index("RESOURCE_ID")
        entry = self.index_table["rows"][idx]
        pos = self.header["file_base_offset"] + entry["offset"]
        ids = []
        for i in range(self.header["entry_count"]):
            res_type = buf[pos:pos+16].decode("ascii").strip("\x00")
            ids.append(res_type)
            pos += 16

        return ids


    def __add_resources_to_indx(self):
        """Iterates through entries and adds resource ids and types to 'self.index_table'."""
        for i in range(self.header["entry_count"]):
            filename = self.resource_names[i]
            if self.resource_types[i] != "":
                filename = filename + '.' + self.resource_types[i]
            self.index_table["rows"][i].update({"filename": filename})


    def dump(self):
        for file in self.index_table["rows"]:
            with open(self.file, "rb") as f:
                file_pos = self.header["file_base_offset"] + file["offset"]
                f.seek(file_pos)
                data = f.read(file["length"])

                filename = file["filename"]
                if filename in ["RESOURCE_ID", "RESOURCE_TYPE"]:
                    continue

                if data[0:4] in EXTENSIONS:  # add .cry to end of file. can't read encrypted files right now.
                    filename = filename + EXTENSIONS[data[0:4]]

                # write file
                if d := filename.rsplit("\\", 1)[0]:
                    os.makedirs(f"{self.output_folder}\\{d}", exist_ok=True)
                else:
                    os.makedirs(self.output_folder, exist_ok=True)

                with open(f"{self.output_folder}\\{filename}", "bw+") as f2:
                    f2.write(data)
