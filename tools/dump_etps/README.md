# dump_etps

These scripts are written to specifically target ETPs and a single RPS file that houses multiple ETPs.

## Requirements

- Install Python 3.11
- Set up a virtual environment, installing the `requirements.txt` at the root of this repository
- Ensure you've set `GAME_DATA_DIR` in  `tools/globals.py` to your DQX installation's "Data" directory
    - Default: `"C:/Program Files (x86)/SquareEnix/DRAGON QUEST X/Game/Content/Data"`
- Open DQX. This is required as this script will decrypt any ETPs that are encrypted
    - This uses the database in `tools/import_sql/dat_db.db`, which has stored blowfish keys and game file references

### dump_etps.py

- Run: `python dump_etps.py`
- ETP files are written to the `etps` directory

### dump_rps.py

- Run: `python dump_rps.py`
- Extracted RPS file is written to the `rps` directory
