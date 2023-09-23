import glob
import json
import io
from io import BytesIO
import os
import requests
from shutil import copy
import sqlite3
from zipfile import ZipFile as zfile
import sys
sys.path.append("../../")  # hack to use tools
from tools.py_globals import GITHUB_URL


DB_PATH = "../import_sql/dat_db.db"
DB_CONN = sqlite3.connect(DB_PATH)
DB_CUR = DB_CONN.cursor()


def get_latest_translation_files():
    """
    Downloads a zip of the latest weblate translation files and processes the files in memory,
    returning a dictionary of {"<file>": {"<file_contents>"}}.
    """
    translated_data = {}
    request = requests.get(GITHUB_URL, timeout=15)
    if request.status_code == 200:
        z_file = zfile(BytesIO(request.content))
        for obj in z_file.infolist():
            if obj.filename[-1] == "/":  # don't parse directories
                continue
            if "json/_lang/en" in obj.filename:
                filename = os.path.basename(obj.filename)
                with io.TextIOWrapper(z_file.open(obj.filename), encoding="utf-8") as f:
                    translated_data[filename] = json.loads(f.read())
    return translated_data


def read_json_file(file):
    """Reads JSON file and returns content."""
    try:
        with open(file, "r", encoding="utf-8") as json_data:
            return json.loads(json_data.read())
    except:
        return None


def search_string(json_dict: dict, text: str):
    """
    Search for a text string (should be Japanese). If an English
    result is found, return the English result. If no English result
    exists, return None.
    """
    values = iter(json_dict.values())
    for value in values:
        result = value.get(text, None)
        if result:
            return result
    return None


def create_directories():
    os.makedirs("new_json", exist_ok=True)
    os.makedirs("new_json/en", exist_ok=True)
    os.makedirs("new_json/ja", exist_ok=True)


def migrate_jsons():
    json_data = get_latest_translation_files()

    jsons = glob.glob("json/en/*.json")

    for new_file in jsons:
        basename = os.path.basename(new_file)
        old_data = json_data.get(basename, None)
        if old_data:
            new_data = read_json_file(new_file)
            if not new_data:
                print(f"Did not find a file named {basename} in json/en.")
                continue

            # search the new json file for matching keys in the old file.
            print(f"Porting {basename}.")

            for str_id in new_data:
                search_key = next(iter(new_data.get(str_id).keys()))

                # for each record, get the existing key value.
                existing_record = search_string(json_dict=old_data, text=search_key)

                if not existing_record:
                    continue

                new_data[str_id][search_key] = existing_record

            with open(f"new_json/en/{basename}", "w+", encoding="utf-8") as f:
                f.write(json.dumps(new_data, ensure_ascii=False, indent=2))
                copy(src=f"json/ja/{basename}", dst=f"new_json/ja/{basename}")
        else:
            print(f"Did not find an existing json file, so migration will not happen. Moving {basename} as-is.")
            copy(src=new_file, dst=f"new_json/en/{basename}")
            copy(src=new_file.replace("json/en", "json/ja"), dst=f"new_json/ja/{basename}")


# TO DO: cli menu to individually port? for now, `python port_translations.py` just runs through all of this
create_directories()
migrate_jsons()
