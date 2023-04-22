import csv
import os
from subprocess import run
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.datfile import DatEntry
from tools.lib.extensions import EXTENSIONS
from tools.lib.idxfile import IdxFile
from tools.idx_searcher.main import get_idx_files

GAME_DATA_DIR = "C:\\Program Files (x86)\\SquareEnix\\DRAGON QUEST X\\Game\\Content\\Data"
DB_PATH = "../import_sql/dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def find_etps():
    found = []
    idx_list = get_idx_files()
    for idx in idx_list:
        file = IdxFile(idx)
        for record in file.records["records"]:
            if record["filename"][8:16] == "669a9b71":  # common/data/eventText/ja/current. all ETP files are here
                idx_file = idx.split("\\")[-1]
                dat_file = idx_file.replace(".win32.idx", f".win32.dat{record['dat_num']}")
                found.append({"idx": idx_file, "dat": dat_file, "file": record["filename"][0:8], "dir": record["filename"][8:16], "dat_offset": record["dat_offset"]})
    return found


def get_file_data(dat_filename: str, offset: int):
    dat_file = GAME_DATA_DIR + "\\" + dat_filename
    file = DatEntry(dat_file, offset)
    return file.data()


def write_etp(filename: str, data: bytes):
    os.makedirs("etps", exist_ok=True)
    with open(f"etps/{filename}", "w+b") as f:
        f.write(data)


def get_filename(file_hash: str):
    query = DB_CUR.execute(f'SELECT file, clarity_name, blowfish_key FROM files WHERE file_hash = "{file_hash}" AND dir_hash = "669a9b71"')
    result = query.fetchall()
    if len(result) == 1:
        filename, clarity_name, blowfish_key = result[0][0], result[0][1], result[0][2]
        if filename:
            name = filename
        elif clarity_name:
            name = clarity_name
        else:
            return None
        if blowfish_key:
            name = name + ".rawenc"
        return name


def update_db(file_hash: str, dir_hash: str, dat: str, idx: str):
    query = DB_CUR.execute(f'SELECT file_dir_hash FROM files WHERE file_dir_hash = "{file_hash}{dir_hash}"')
    if not query.fetchone():
        # new file, get it into the db
        DB_CUR.execute(f'INSERT INTO files(file_hash, dir_hash, dat, idx) VALUES("{file_hash}","{dir_hash}", "{dat}", "{idx}")')
        print(f"New file {file_hash} added to db.")
    DB_CONN.commit()


def read_hex_dict(path_to_csv: str):
    csv_list = []
    with open(path_to_csv, encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            csv_list.append(row)
    return csv_list


def get_matching_clarity_name(csv_data: list, file: str):
    """
    Searches all ETP files the way Clarity does,
    which uses 64 bytes from the 80th byte position
    to determine what the file is. Awful way to do it, I know.
    """
    with open(file, "rb") as f:
        f.seek(80)
        indx_bytes = f.read(64).hex(" ").upper()
    for row in csv_data:
        if row["hex_string"] == indx_bytes:
            return row["file"].split("\\")[-1].split(".")[0] + ".etp"  # ex: 'more_login_menus.etp'
    return None
 

def update_db_with_clarity_name(file_hash: str, dir_hash: str, clarity_name: str):
    DB_CUR.execute(f'UPDATE files SET clarity_name = "{clarity_name}" WHERE file_dir_hash = "{file_hash}{dir_hash}"')
    DB_CONN.commit()


def get_known_encrypted_files():
    """
    Pull all known blowfish keys from the database.
    We are only able to decrypt/recrypt files that
    have known keys.
    """
    DB_CUR.execute("SELECT file, blowfish_key FROM files WHERE blowfish_key IS NOT NULL")
    results = DB_CUR.fetchall()
    return results


def decrypt_file(file: str):
    """
    Run dqxcrypt to decrypt an ETP.
    DQX must be open for this to work.
    """
    enc_db_results = get_known_encrypted_files()
    for result in enc_db_results:
        etp_file, key = result
        
        if file.replace(".rawenc", "") == etp_file:
            os.chdir("dqxcrypt")
            run(["../../../venv/Scripts/python.exe", "dqxcrypt.py", "decrypt_raw", f"../etps/{file}", key])
            os.chdir("..")
            return True
    return False


def main():
    etps = find_etps()
    for etp in etps:
        file_data = get_file_data(dat_filename=etp["dat"], offset=etp["dat_offset"])
        if file_data:
            ext = file_data[0:7]
            name = get_filename(etp["file"])
            if name:
                filename = name
            else:
                # we don't know this file. start tracking it in the db
                update_db(file_hash=etp["file"], dir_hash=etp["dir"], dat=etp["dat"], idx=etp["idx"])
                if ext in EXTENSIONS:
                    filename = etp["file"] + EXTENSIONS[ext]
                else:
                    filename = etp["file"] + ".rawenc"  # if we don't know extension in this dir, it's highly likely encrypted
            write_etp(filename=filename, data=file_data)

            # attempt to decrypt file from known blowfish key.
            # if successful, rename it to etp.
            if decrypt_file(file=filename):
                filename = filename.split(".etp")[0] + ".etp"
                os.remove(f"etps/{filename}.rawenc")
                os.replace(src=f"etps/{filename}.rawenc.dec", dst=f"etps/{filename}", )


if __name__ == "__main__":
    main()
