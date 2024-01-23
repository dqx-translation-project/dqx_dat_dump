import argparse
import glob
import os
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.datentry import DatEntry
from tools.lib.extensions import EXTENSIONS
from tools.lib.idxfile import IdxFile
from tools.idx_searcher.main import get_idx_files
from tools.py_globals import GAME_DATA_DIR
from tools.dump_etps.dqxcrypt.dqxcrypt import (
    attach_client,
    decrypt
)

DB_PATH = "../import_sql/dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def find_etps():
    found = []
    idx_list = get_idx_files()
    for idx in idx_list:
        file = IdxFile(idx)
        for record in file.records:
            if record["filename"][8:16] == "669a9b71":  # common/data/eventText/ja/current. all ETP files are here
                idx_file = idx.split("\\")[-1]
                dat_file = idx_file.replace(".win32.idx", f".win32.dat{record['dat_num']}")
                found.append({"idx": idx_file, "dat": dat_file, "file": record["filename"][0:8], "dir": record["filename"][8:16], "dat_offset": record["dat_offset"]})
    return found


def get_file_data(dat_filename: str, offset: int):
    dat_file = "/".join([GAME_DATA_DIR, dat_filename])
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
        DB_CUR.execute(f'INSERT INTO files(file_hash, dir_hash, file_dir_hash) VALUES("{file_hash}","{dir_hash}", "{file_hash}{dir_hash}")')
        print(f"New file {file_hash} added to db.")
    DB_CONN.commit()


def get_blowfish_key(file: str):
    """
    Looks up a file to retrieve the 
    """
    DB_CUR.execute(f"SELECT blowfish_key FROM files WHERE file = \"{file}\" OR clarity_name = \"{file}\"")
    results = DB_CUR.fetchone()
    if results:
        return results[0]
    return None


def decrypt_file(file: str, agent: object):
    """
    Run dqxcrypt to decrypt an ETP.
    DQX must be open for this to work.
    """
    no_rawenc = file.replace(".rawenc", "")  # db doesn't store file as ".rawenc"
    blowfish_key = get_blowfish_key(no_rawenc)
    if blowfish_key:
        decrypt(agent=agent, filepath=f"etps/{file}", encryption_key=blowfish_key)
        return True
    return False


def dump_all_etps():
    etps = find_etps()
    for etp in etps:

        _dat = etp["dat"]
        _offset = etp["dat_offset"]
        _file = etp["file"]
        _dir = etp["dir"]
        _idx = etp["idx"]

        file_data = get_file_data(dat_filename=_dat, offset=_offset)
        if file_data:
            ext = file_data[0:7]
            name = get_filename(_file)
            if name:
                filename = name
            else:
                # we don't know this file. start tracking it in the db
                update_db(file_hash=_file, dir_hash=_dir, dat=_dat, idx=_idx)
                if ext in EXTENSIONS:
                    filename = _file + EXTENSIONS[ext]
                else:
                    filename = _file + ".rawenc"  # if we don't know extension in this dir, it's highly likely encrypted
            print(f"Writing {filename}")
            write_etp(filename=filename, data=file_data)


def decrypt_etps():
    """
    Decrypt all rawenc files in the "etps" folder.
    """
    if not os.path.exists("etps"):
        sys.exit("Dump the ETPs first and then attempt to decrypt.")
    agent = attach_client()
    etps = glob.glob("etps/*.rawenc")
    for etp in etps:
        basename = os.path.basename(etp)
        if decrypt_file(file=basename, agent=agent):
            no_rawenc = basename.replace(".rawenc", "")
            os.replace(src=f"etps/{basename}.dec", dst=f"etps/{no_rawenc}")
            os.remove(etp)
    agent.detach_game()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dumps and unencrypts ETPs.")
    parser.add_argument("-u", default=False, action="store_true", help="Unpack ETPs from the data00000000 DAT.")
    parser.add_argument("-d", default=False, action="store_true", help="Decrypts ETPs ending in \".rawenc\" in the etps folder.")
    args = parser.parse_args(args=None if sys.argv[1:] else ["--help"])

    if args.u and args.d:
        sys.exit("Please specify either one argument or the other; not both.")
    if args.u:
        dump_all_etps()
    elif args.d:
        decrypt_etps()
