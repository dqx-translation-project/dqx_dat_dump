# idqx_searcher

Script to search idx files for a matching hash.

## Requirements

- Install Python 3.11
- Set up a virtual environment, installing the `requirements.txt` at the root of this repository
- Ensure you've set `GAME_DATA_DIR` in  `tools/globals.py` to your DQX installation's "Data" directory
    - Default: `"C:/Program Files (x86)/SquareEnix/DRAGON QUEST X/Game/Content/Data"`

### main.py

- Run `python main.py <hash>`
- Returns a dict of the location of the hash (idx, dat, offsets)
