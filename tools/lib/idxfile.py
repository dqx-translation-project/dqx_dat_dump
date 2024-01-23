from binascii import hexlify
from struct import unpack, pack
import sys
import pathlib
import sqlite3
import shutil
sys.path.append("../../")  # hack to use tools
from tools.py_globals import ORIG_NUM_DATS, PROJECT_ROOT, GAME_DATA_DIR
from tools.lib.fileops import pack_uint


FILE_TYPES = {
    1: "SQDB?",
    2: "Data",
    3: "Index"
}


class IdxFile:
    def __init__(self, file: str):
        """
        :param file: Absolute path to the IDX file.
        """
        self.file = file
        self.__is_idx(file=self.file)

        self.db_path = "../../dat_db.db"
        self.db_conn = sqlite3.connect(self.db_path)
        self.db_cur = self.db_conn.cursor()

        # idx files are pretty small (less than 4MB), so read all in
        with open(file, "rb") as f:
            self.smpk = self.__read_smpk(f.read(0x400))
            self.segments = self.__read_segments(f.read(0x400))

            # only read in the files, which are at the top of the record list.
            self.records = self.__read_all_records(f.read(self.segments[1]["size"]))


    def __is_idx(self, file: str):
        """
        Check if the file provided is a valid IDX file.
        """
        if pathlib.Path(file).suffix != ".idx":
            print("File extension is not '.idx'.")
            sys.exit(1)

        with open(file, "rb") as f:
            if f.read(4) != b"\x53\x4D\x50\x4B":  # SMPK
                print("Unrecognized IDX header. Did not read SMPK.")
                sys.exit(1)


    def __read_smpk(self, buf):
        data = unpack("<4s 8x I 4x I 936x 20s 44x", buf)
        header = {
            "signature": data[0],
            "length": data[1],
            "type": FILE_TYPES[data[2]],
            "sha1": hexlify(data[3])
        }

        return header


    def __read_segments(self, buf):
        data = unpack("<I I I I 20s 44x I I I 20s 44x I I I 16s 44x I I I 16s 704x 20s 44x", buf)
        segments = {
            "length": data[0],
            "sha1": hexlify(data[17]),
            1: {  # files
                "unknown": data[1],
                "offset": data[2],
                "size": data[3],
                "sha1": hexlify(data[4]),
            },
            2: {
                "num_dats": data[5],  # controls how many dats to load. 0x01 = .dat0, 0x02 = .dat0 + .dat1, etc.
                "offset": data[6],
                "size": data[7],
                "sha1": hexlify(data[8]),
            },
            3: {
                "offset": data[9],
                "size": data[10],
                "unknown": data[11],
                "sha1": hexlify(data[12]),
            },
            4: {  # folders
                "offset": data[13],
                "size": data[14],
                "unknown": data[15],
                "sha1": hexlify(data[16]),
            },
        }

        return segments


    def __db_lookup(self, hashed_filename: str):
        db_result = self.db_cur.execute(f"SELECT file, directory FROM files WHERE file_dir_hash = '{hashed_filename}'")
        found = db_result.fetchone()

        return found or ("", "")


    def __read_all_records(self, buf):
        rows = buf
        count = 0
        position = 0
        records = []
        num_records = len(rows) / 16

        while count < num_records:
            data = unpack("<I I I 4x", rows[position:position+16])

            # using as an identifier to figure out which row in the index something is in
            # since I don't have filenames to work with. this just outputs the first 8 bytes
            # of the index entry, which is the hashed file name + folder name.
            hashed_filename = (hexlify(pack("<L", data[0])) + hexlify(pack("<L", data[1]))).decode()

            db_result = self.__db_lookup(hashed_filename=hashed_filename)

            record = {
                "file_hash": pack_uint(data[0]).hex(),
                "folder_hash": pack_uint(data[1]).hex(),
                "idx_offset": 0x800 + position,
                "dat_offset": (data[2] & ~0xF) * 0x08,
                "dat_num": (data[2] & 0b1110) >> 1,
                "dat_file": pathlib.Path(self.file).stem + ".dat" + str((data[2] & 0b1110) >> 1),
                "hashed_filename": hashed_filename,
                "filename": db_result[0],
                "folder": db_result[1],
            }

            records.append(record)
            count += 1
            position += 16

        return records


    def __update_num_dats(self):
        """
        Update the IDX file to increment the number of dats. This is necessary
        to tell the game to load a newly created dat. This does not overwrite
        the existing IDX file, but copies the changes into the project root.
        """
        filename = pathlib.Path(self.file).name
        new_dat_count = ORIG_NUM_DATS[filename] + 1  # we increment here as dat0 is \x01
        new_file = "/".join([PROJECT_ROOT, filename])

        if not pathlib.Path(new_file).is_dir():
            shutil.copy(self.file, new_file)

        with open(new_file, "r+b") as f:
            f.seek(1104)
            f.write(pack_uint(new_dat_count))


    def get_record_by_filename(self, filename: str):
        """
        Gets a record by its actual filename.
        As the database is incomplete, this will likely be missing data.
        Searching by hashed_filename will provide a more complete search.
        """
        for record in self.records:
            if record["filename"] == filename:
                return record
        return None


    def get_record_by_hash(self, hashed_filename: str):
        """
        Gets a record by its hashed filename.
        """
        for record in self.records:
            if record["hashed_filename"] == hashed_filename:
                return record


    def get_matching_filenames(self, str_lookup: str):
        """
        Get all records that match the search string.
        """
        matches = []
        for record in self.records:
            if record["filename"]:
                if str_lookup in record["filename"]:
                    matches.append(record)
        return matches


    def get_records_from_folder_hash(self, folder_hash: str):
        """
        Get all records inside of a hashed folder name.
        """
        matches = []
        for record in self.records:
            if folder_hash == record["folder_hash"]:
                matches.append(record)
        return matches


    def get_records_from_folder_path(self, folder: str):
        """
        Get all records inside of a folder path.
        As the database is incomplete, this will likely be missing data.
        Searching by folder_hash will provide a more complete search.
        """
        matches = []
        for record in self.records:
            if folder == record["folder"]:
                matches.append(record)
        return matches


    def create_custom_dat(self):
        """
        Creates a new dat file by incrementing the total number of current dats.
        Unsure of a reliable way to calculate the next dat as there could be custom
        dats in the directory already, so the original number of dats is hardcoded.
        Since a dat file is associated with an IDX file, the creation of the dat is
        found in this class.
        """
        idx_basename = pathlib.Path(self.file).name

        # all dats have a dat0 and we use this as the base when creating a new one
        orig_dat0 = "/".join([GAME_DATA_DIR, pathlib.Path(idx_basename).stem + ".dat0"])
        next_dat = pathlib.Path(idx_basename).stem + ".dat" + str(ORIG_NUM_DATS[idx_basename])
        new_file = "/".join([PROJECT_ROOT, next_dat])

        if not pathlib.Path(new_file).is_file():
            with open(orig_dat0, "rb") as f:
                dat_header = f.read(2048)
            with open(new_file, "w+b") as f:
                f.write(dat_header)

        self.__update_num_dats()

        return new_file
