import argparse
import csv
import sqlite3
import sys
sys.path.append("../../")  # hack to use tools
from tools.idx_searcher.main import find_file, reverse_hex_string_le


DB_PATH = "./dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def read_csv(file: str):
    record_list = []
    with open(file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # handle hashlog.csv
            if "hash_type" in row:
                clean_hash_output = row["hash_output"].replace("0x", "")

                # hash_output sometimes comes over with < 8 characters, which means it isn't adding
                # leading zeroes for the hash in a 4 byte address.
                while len(clean_hash_output) < 8:
                    clean_hash_output = "0" + clean_hash_output

                # dqxcrypt logs the hashed file/dir name as BE. convert this to LE for ease of use.
                le_hash_output = reverse_hex_string_le(hex_str=clean_hash_output)

                # dqxcrypt logs dir and file on separate lines, but they're always grouped in pairs.
                if row["hash_type"] == "dir":
                    record_list.append({"dir": row["hash_input"], "dir_hash": le_hash_output})
                elif row["hash_type"] == "file":
                    dir_item = record_list.pop()
                    dir_item.update({"file": row["hash_input"], "file_hash": le_hash_output})
                    record_list.append(dir_item)
            # handle blowfish_log.csv
            elif "blowfish_key" in row:
                file = row["filepath"].split("/")[-1].replace(".*", "")
                record_list.append({"file": file, "key": row["blowfish_key"]})
    return record_list


def update_idx_dats():
    rows = DB_CUR.execute(f'SELECT file_dir_hash FROM files WHERE dat IS NULL')
    for row in rows.fetchall():
        file = find_file(filename=row[0])
        if file:
            DB_CUR.execute(f'UPDATE files SET (idx, dat) = ("{file["idx"]}", "{file["dat"]}") WHERE file_dir_hash = "{row[0]}"')
    DB_CONN.commit()


def update_db(records: list):
    updated = 0
    for record in records:
        # handle hashlog.csv
        if 'dir' in record:
            result = DB_CUR.execute(f'SELECT file_dir_hash FROM files WHERE "file_dir_hash" = "{record["file_hash"]}{record["dir_hash"]}"')
            if not result.fetchone():
                DB_CUR.execute(f'INSERT INTO files(file,directory,file_dir_hash,file_hash,dir_hash) VALUES("{record["file"]}","{record["dir"]}","{record["file_hash"]}{record["dir_hash"]}","{record["file_hash"]}","{record["dir_hash"]}")')
                updated += 1
            else:
                # etps were manually added to the database. if we see them, make sure the row has
                # all of the appropriate columns
                if record["dir"] == "common/data/eventText/ja/current":
                    DB_CUR.execute(f'UPDATE files SET file = "{record["file"]}", directory = "{record["dir"]}" WHERE file_dir_hash = "{record["file_hash"]}{record["dir_hash"]}"')
                    updated += 1
        # handle blowfish_log.csv
        elif 'key' in record:
            result = DB_CUR.execute(f'SELECT file FROM files WHERE "file" = "{record["file"]}"')
            if not result.fetchone():
                DB_CUR.execute(f'INSERT INTO files(file,blowfish_key) VALUES("{record["file"]}","{record["key"]}")')
                updated += 1
            else:
                DB_CUR.execute(f'UPDATE files SET blowfish_key = "{record["key"]}" WHERE file = "{record["file"]}"')
                updated += 1
    DB_CONN.commit()
    return updated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dedupe and insert/update CSV log entries into a SQLite database.")
    parser.add_argument("-c", help="Specify a blowfish_log.csv or hashlog.csv file to import into a SQLite database.")
    parser.add_argument("-u", action=argparse.BooleanOptionalAction, help="Scans all records without a dat/idx reference and attempts to find them, writing them to the database.")
    args = parser.parse_args()

    if args.c:
        results = read_csv(file=args.c)
        print(f"Found {len(results)} rows.")
        updated = update_db(records=results)
        print(f"Inserted/updated {updated} record(s).")

    if args.u:
        print("Updating rows with unknown dat/idx references.")
        update_idx_dats()
        print("Complete.")
