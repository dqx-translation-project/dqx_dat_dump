import glob
import os
from subprocess import run, PIPE
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.datfile import DatEntry
from tools.lib.idxfile import IdxFile
from tools.lib.rpsfile import RpsFile
from tools.globals import GAME_DATA_DIR
from tools.dump_etps.dqxcrypt.dqxcrypt import (
    attach_client,
    bruteforce
)

DB_PATH = "../import_sql/dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def log(text: str):
    with open("log.txt", "a+") as f:
        f.write(text + "\n")


def find_rps_etp():
    idx = f"{GAME_DATA_DIR}\\data00000000.win32.idx"
    dat = f"{GAME_DATA_DIR}\\data00000000.win32.dat0"
    file = IdxFile(idx)
    for record in file.records["records"]:
        if record["filename"] == "800718ca783ff612":  # special RPS that has all initially loaded ETPs in it
            return ({"idx": idx, "dat": dat, "file": record["filename"][0:8], "dir": record["filename"][8:16], "dat_offset": record["dat_offset"]})
    return None


def dump_rps_etp():
    rps = find_rps_etp()
    rps_file = DatEntry(dat_file=rps["dat"], offset=rps["dat_offset"])
    rps_data = rps_file.data()
    os.makedirs("rps", exist_ok=True)
    with open("rps/packageManagerRegistIncludeAutoClient.rps", "w+b") as f:
        f.write(rps_data)


def extract_rps():
    rps = ".\\rps\\packageManagerRegistIncludeAutoClient.rps"
    rps_data = RpsFile(rps)
    rps_data.dump()


def decrypt_cry_files():
    """
    Run dqxcrypt to decrypt encrypted CRY files.
    DQX must be open for this to work.
    """
    agent = attach_client()
    files = glob.glob("rps/packageManagerRegistIncludeAutoClient_rps/*.etp.cry")
    for file in files:
        bruteforce(
            agent=agent,
            filepath=file,
            managed_package_data_client_path="rps/packageManagerRegistIncludeAutoClient_rps/ManagedPackageDataClient.win32.pkg"
        )
        new_name = file.split(".cry")[0]
        os.replace(src=f"{file}.dec", dst=new_name)
        os.remove(file)
    agent.detach_game()


if __name__ == "__main__":
    dump_rps_etp()
    extract_rps()
    decrypt_cry_files()
