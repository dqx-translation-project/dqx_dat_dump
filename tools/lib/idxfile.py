from binascii import hexlify
from struct import unpack, pack

SMPK_SIZE = 0x400
STRUCT_SIZE = 0x400

file_types = {
    1: "SQDB?",
    2: "Data",
    3: "Index"
}


class IdxFile:
    def __init__(self, file: str):
        self.file = file

        # idx files are pretty small (less than 4MB), so read all in
        with open(file, "rb") as f:
            file_data = f.read()

        self.smpk = self.smpk(
            buf=file_data[0:SMPK_SIZE])
        self.segments = self.segments(
            buf=file_data[SMPK_SIZE:SMPK_SIZE+STRUCT_SIZE])
        self.records = self.records(
            buf=file_data[SMPK_SIZE+STRUCT_SIZE:SMPK_SIZE+STRUCT_SIZE+self.segments[1]["size"]]
        )

    def smpk(self, buf):
        data = unpack("<4s 8x I 4x I 936x 20s 44x", buf)
        header = {
            "signature": data[0],
            "length": data[1],
            "type": file_types[data[2]],
            "sha1": hexlify(data[3])
        }

        return header

    def segments(self, buf):
        data = unpack("<I I I I 20s 44x I I I 20s 44x I I I 16s 44x I I I 16s 704x 20s 44x", buf)
        segments = {
            "length": data[0],
            "num_dats": data[5],
            "sha1": hexlify(data[17]),
            1: {  # files
                "unknown": data[1],
                "offset": data[2],
                "size": data[3],
                "sha1": hexlify(data[4]),
            },
            2: {
                "offset": data[6],
                "size": data[7],
                "sha1": hexlify(data[8]),
            },
            3: {
                "unknown": data[9],
                "offset": data[10],
                "size": data[11],
                "sha1": hexlify(data[12]),
            },
            4: {  # folders
                "unknown": data[13],
                "offset": data[14],
                "size": data[15],
                "sha1": hexlify(data[16]),
            }
        }

        return segments

    def records(self, buf):
        rows = buf
        count = 0
        position = 0
        records = []
        num_records = len(rows) / 16

        record_dict = {
            "count": int(num_records),
            "records": records
        }

        while count < num_records:
            data = unpack("<I I I 4x", rows[position:position+16])

            # using as an identifier to figure out which row in the index something is in
            # since I don't have filenames to work with. this just outputs the first 8 bytes
            # of the index entry.
            filename = (hexlify(pack("<L", data[0])) + hexlify(pack("<L", data[1]))).decode()

            record = {
                "file_hash": data[0],
                "folder_hash": data[1],
                "idx_offset": SMPK_SIZE + STRUCT_SIZE + position,
                "dat_offset": (data[2] & ~0xF) * 0x08,
                "dat_num": str((data[2] & 0b1110) >> 1),
                "filename": filename
            }

            records.append(record)
            count += 1
            position += 16

        return record_dict
