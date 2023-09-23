import argparse
import glob
import os
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.datentry import DatEntry
from tools.lib.idxfile import IdxFile
from tools.lib.rpsfile import RpsFile
from tools.py_globals import GAME_DATA_DIR
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
    for record in file.records:
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
    if not os.path.exists("rps"):
        sys.exit("Dump the RPS first and then attempt to decrypt.")
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
    parser = argparse.ArgumentParser(description="Unpack and unencrypts a specific RPS file that contains game ETP files.")
    parser.add_argument("-u", default=False, action="store_true", help="Unpack and extract the RPS.")
    parser.add_argument("-d", default=False, action="store_true", help="Decrypts all CRY files in the RPS. Note that this is usually not necessary to perform as the files in this RPS are also found in the \"etps\" folder.")
    args = parser.parse_args(args=None if sys.argv[1:] else ["--help"])

    if args.u and args.d:
        sys.exit("Please specify either one argument or the other; not both.")
    if args.u:
        dump_rps_etp()
        extract_rps()
    elif args.d:
        decrypt_cry_files()
