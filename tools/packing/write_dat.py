import glob
import pathlib
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.idx_searcher.main import find_file
from tools.py_globals import GAME_DATA_DIR
from tools.lib.idxfile import IdxFile
from tools.lib.datfile import DatFile


DB_PATH = "../import_sql/dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def get_record(etp_file: str):
    DB_CUR.execute(f'SELECT file_dir_hash, blowfish_key FROM files WHERE file = "{etp_file}" OR clarity_name = "{etp_file}"')
    result = DB_CUR.fetchone()
    if result:
        return result[0], result[1]
    return None


def write_etps():
    etp_files = glob.glob("new_etp/*.etp")
    rps_files = glob.glob("new_rps/*.rps")
    files_to_pack = etp_files + rps_files

    idx_file = IdxFile(f"{GAME_DATA_DIR}/data00000000.win32.idx")
    dat_path = idx_file.create_custom_dat()
    dat_file = DatFile(file=dat_path)


    for file in files_to_pack:
        basename = pathlib.Path(file).name
        db_result = get_record(etp_file=basename)
        if not db_result:
            print(f"Did not find {basename} in the database. Skipping.")
            continue
        file_dir_hash = db_result[0]
        idx_record = idx_file.get_record_by_hash(file_dir_hash)
        if not idx_record:
            print("Could not find hash record. Skipping")
            continue

        dat_file.write_to_dat(idx_offset=idx_record["idx_offset"], file=file)


write_etps()
