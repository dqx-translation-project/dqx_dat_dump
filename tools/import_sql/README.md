# import_sql

Used in conjunction with [dqxcrypt's](https://github.com/Andoryuuta/dqxcrypt) `logger` functionality.

Ports logs dumped from `dqxcrypt` into `dat_db.db`. Can be used to lookup hashed file/folder names inside of dats.

## Requirements

- Install Python 3.11
- Set up a virtual environment, installing the `requirements.txt` at the root of this repository

### main.py

- Run `python main.py -c <path_to_blowfish_log_OR_hash_log>`

NOTE: If you're importing both logs from a game session, import the hashlog first, then the blowfish log. Doing them in reverse order is pointless as the blowfish log may be referencing data that isn't yet in the database as the hashlog has this information.
