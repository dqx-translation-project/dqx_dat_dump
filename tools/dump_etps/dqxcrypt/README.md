# dqxcrypt
A DQX file [en|de]cryptor

## Setup:

```
git clone https://github.com/andoryuuta/dqxcrypt.git
pip install frida
```

## Usage:
```sh
dqxcrypt.py encrypt <path to unencrypted CRY file> <encryption key string>
dqxcrypt.py encrypt_raw <path to unencrypted raw file> <encryption key string> 
dqxcrypt.py decrypt <path to encrypted CRY file> <encryption key string>
dqxcrypt.py decrypt_raw <path to encrypted raw file> <encryption key string>
dqxcrypt.py bruteforce <path to encrypted CRY file> <path to ManagedPackageDataClient.win32.pkg> 
dqxcrypt.py logger
```

# Encrypting & Decrypting files
## With known keys
There are four separate commands for encrypting/decrypting files with known keys.

* For files with a `CRY\0x9` header, use the `encrypt` and `decrypt` commands.
* For files without a header, use the `encrypt_raw` and `decrypt_raw` commands.
   * CutScene/Event files will require this.

## With unknown keys
For CRY files without a known encryption key, you can use the `bruteforce` command to try decrypting a file with all the possible blowfish keys in `ManagedPackageDataClient.win32.pkg`.

For files that cannot be bruteforced via the `bruteforce` command, see the below section for running the blowfish logger.

# Logger
The `logger` command installs two hooks into the open client for logging purposes:
### 1. Blowfish keys
Blowfish key logging is required for some specific files, as the key is kept server-side, and only sent to the client when requested.

These are outputted to the console as well as the CSV file in `./logs/blowfish_log.csv`

### 2. Directory/File hashes
Directory/File hash logging allows for mapping real filepath strings to the hashes listed in the the client's main .dat file(s) file entries.

NOTE: The output hashes are essentially reversed from how `dqx_data_dump` names it's extracted files.
* Example mapping between dqx_data_dump and hash log output:
    |||
    |-|-|
    |original filepath/name|`common/data/eventText/ja/current/eventTextCsT13Client.etp`|
    |dqx_data_dump filepath/name|`861bd798669a9b71`|
    |hash logger input|`common/data/eventText/ja/current`|
    |hash logger output|`0x719b9a66`|
    |hash logger input|`eventTextCsT13Client.etp`|
    |hash logger output|`0x98d71b86`|

These are outputted to the console as well as the CSV file in `./logs/hashlog.csv`