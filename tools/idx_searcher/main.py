"""
This script is used to search a hashed file + dir name
and search for where the file exists within all game dats.
It returns a dictionary with the matching idx and dat file.
"""

import argparse
import glob
import sys
sys.path.append("../../")  # hack to use tools
from tools.lib.idxfile import IdxFile
from tools.py_globals import GAME_DATA_DIR


def get_idx_files() -> list:
    # idx files are found in base Data and xpac Data folders
    idx_files = glob.glob(f"{GAME_DATA_DIR}/*.idx")
    idx_files = idx_files + (glob.glob(f"{GAME_DATA_DIR}/../*/Data/*.idx"))
    return idx_files


def find_file(filename: str):
    found = []
    idx_list = get_idx_files()
    for idx in idx_list:
        file = IdxFile(idx)
        for record in file.records:
            if filename.lower() == record["filename"]:
                idx_file = idx.split("\\")[-1]
                dat_file = idx_file.replace(".win32.idx", f".win32.dat{record['dat_num']}")
                return {"idx": idx_file, "idx_offset": record["idx_offset"], "dat": dat_file, "dat_offset": record["dat_offset"]}
    return {}


def reverse_hex_string_le(hex_str: str):
    file = hex_str[0:8]
    dirname = hex_str[8:16]
    file_r = "".join(reversed([file[i:i+2] for i in range(0, len(file), 2)]))
    dirname_r = "".join(reversed([dirname[i:i+2] for i in range(0, len(dirname), 2)]))
    return file_r + dirname_r


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Return idx file that contains matching file+folder hash.")
    parser.add_argument("hashed_name", type=str, help="Name of file hash + folder hash. ex: dd2d262c3b39fbd1")
    parser.add_argument("-r", action=argparse.BooleanOptionalAction, help="Read the file and folder name as little endian. Useful if you're grabbing hashes directly from dqxcrypt.")
    args = parser.parse_args()

    filename = args.hashed_name
    if args.r:
        filename = reverse_hex_string_le(hex_str=args.hashed_name)

    result = find_file(filename=filename)
    if result:
        print(result)
    else:
        print("Did not find a match.")
