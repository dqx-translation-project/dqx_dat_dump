# packing

A series of tools to unpack + pack ETPs, RPS and write packed files to DAT.

## Requirements

- Install Python 3.11
- Set up a virtual environment, installing the `requirements.txt` at the root of this repository
- Ensure you've set `GAME_DATA_DIR` in  `tools/globals.py` to your DQX installation's "Data" directory
    - Default: `"C:/Program Files (x86)/SquareEnix/DRAGON QUEST X/Game/Content/Data"`
- If re-encrypting files, DQX must be open

## Usage

Typically, you run these tools in this order:

- unpack_etp.py > port_translations.py > pack_etp.py > pack_rps.py > write_dat.py

### unpack_etp.py

Reads an ETP and unpacks it into JSON format.

- Run: `python unpack_etp.py -a` to unpack all files from `tools/dump_etps`
    - Optionally, you can target a single ETP with `python unpack_etp.py -e <path_to_etp>`
- This writes all JSONs to the `json/en` and `json/ja` directory. These are split up to be used in a translation platform like Weblate

### port_translations.py

Downloads a zip of the `dqx_translations` repository and ports the existing json translations into the new JSONs that were just dumped from `unpack_etp.py`.

- Run: `python port_translations.py`
- Ported JSONs can be found in `new_json/en` and `new_json/ja`. During patches, the files in these directories should be written back to the `dqx_translations` repository for translators to use the latest files

### pack_etp.py

Packs an new ETP with the text from the JSONs that were dumped.

If you want to pack a single file:

- Run: `python pack_etp.py -e <path_to_original_etp> -j <path_to_translated_json>` 

If you want to pack all files in `new_json/en`:

- Run: `python pack_etp.py -a`

Optionally, you can re-encrypt the files the same way they were decrypted by passing the `-r` flag. Although several files are stored encrypted, they do not need to be written back to the game as encrypted. The game will read the decrypted files naturally.

### pack_rps.py

Uses the translated ETPs and packs a new RPS.

- Run: `python pack_rps.py`
- Outputs an edited RPS file in `new_rps`

### write_dat.py

Reads all files in the `new_etp` and `new_rps` directories and writes them to the DAT.

NOTE: This will write to your LIVE dat file in your game directory. Ensure you take a backup of the original `data00000000.win32.dat0` and `data00000000.win32.idx` if you prefer. 

- Run: `python write_dat.py`
- This appends the packed ETPs and RPS to your live DAT file in your game directory
