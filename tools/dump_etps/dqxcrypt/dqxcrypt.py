import argparse
from collections import namedtuple
import io
import struct
import sys
import frida
from frida_agent import FridaAgent
from managed_package_data_client import ManagedPackageDataClient


CryFile = namedtuple('CryFile', ['magic', 'version', 'unknown', 'data'])


def read_cry_file(filepath: str) -> CryFile:
    with open(filepath, 'rb') as f:
        (magic, data_size, version, unk0) = struct.unpack('<IIII', f.read(16))
        data = f.read(data_size)
        return CryFile(magic, version, unk0, data)


def write_cry_file(cryfile: CryFile) -> bytes:
    out = io.BytesIO()
    out.write(struct.pack('<IIII', cryfile.magic, len(cryfile.data), cryfile.version, cryfile.unknown))
    out.write(cryfile.data)
    return out.getvalue()


def do_encrypt(agent, filepath, encryption_key, rawFile=False):
    with open(filepath, 'rb') as f:
        data = f.read()
        encrypted_data = agent.blowfish_encrypt(encryption_key, data)
        if rawFile:
            return encrypted_data
        else:
            return write_cry_file(CryFile(0x9595243, 16, 0, encrypted_data))


def do_decrypt(agent, filepath, encryption_key, rawFile=False):
    data = None
    if rawFile:
        with open(filepath, 'rb') as f:
            data = f.read()
    else:
        cryfile = read_cry_file(filepath)
        data = cryfile.data

    decrypted_data = agent.blowfish_decrypt(encryption_key, data)
    return (encryption_key, decrypted_data)


def do_bruteforce_decrypt(agent, filepath, managed_package_data_client_path, crib=b'EVTX'):
    # Read the encrypted data + key file
    cryfile = read_cry_file(filepath)
    mpdc = ManagedPackageDataClient()
    mpdc.read_from(managed_package_data_client_path)

    # Print key ranges & groups for debugging.
    group_type = ['smldt_msg_pkg_%s.*.etp', 'eventText%sClient.*.etp', 'subPackage%02dClient.*.etp']
    for i in range(mpdc.group_count):
        print(f"Key Group {i} - used for {group_type[i]} files")
        print('  Ranges:')
        for (ri, range_obj) in enumerate(mpdc.group_ranges[i]):  
            print(f'    Range[{ri}]: {range_obj}')

        print('  Keys:')
        for (ki, key) in enumerate(mpdc.group_keys[i]):  
            print(f'    Key[{ki}]: {key}')

        print('')

    # Try decrypting with all of the keys in the file until we find our crib text.
    for key_group in mpdc.group_keys:
        for key in key_group:
            print("Trying decryption with key: " + key)
            decrypted_data = agent.blowfish_decrypt(key, cryfile.data)
            if decrypted_data[:len(crib)] == crib:
                return (key, decrypted_data)


    return (None, None)


def attach_client() -> object:
    try:
        agent = FridaAgent()
        agent.attach_game()
    except frida.ProcessNotFoundError:
        sys.exit("Could not find process DQXGame.exe. Cannot continue.")

    return agent


def cli_logger(agent: object):
    agent.init_logging()
    agent.install_hash_logger()
    agent.install_blowfish_logger()
    print("[!] Press any to stop logging\n\n")
    sys.stdin.read()


def cli_encrypt(agent: object, filepath: str, encryption_key: str):
    is_raw = True
    if ".win32." in filepath:
        is_raw = False  # etp files with '.win32.' are CRY files. found in the RPS

    print(f'Encrypting {filepath} with key {encryption_key}')
    data = do_encrypt(agent, filepath, encryption_key, rawFile=is_raw)

    output_filepath = filepath + '.enc'
    print(f'Encrypted with key "{encryption_key}". Writing to: {output_filepath}')
    with open(output_filepath, 'wb') as f:
        f.write(data)


def cli_decrypt(agent: object, filepath: str, encryption_key: str):
    is_raw = True
    with open(filepath, "rb") as f:
        data = f.read(4)
        if data == b"\x43\x52\x59\x09": # CRY
            is_raw = False

    (key, decrypted_data) = do_decrypt(agent, filepath, encryption_key, rawFile=is_raw)
    output_filepath = filepath + '.dec'
    print(f'Decrypted with key "{key}". Writing to: {output_filepath}')
    with open(output_filepath, 'wb') as f:
        f.write(decrypted_data)


def cli_bruteforce(agent: object, filepath: str, managed_package_data_client_path: str):
    print(f'Attempting decryption of {filepath} with keys from {managed_package_data_client_path}.')
    (key, data) = do_bruteforce_decrypt(agent, filepath, managed_package_data_client_path)

    # Write file if we managed to decrypt it.
    if key != None:
        output_filepath = filepath + '.dec'
        print(f'Decrypted with key "{key}". Writing to: {output_filepath}')
        with open(output_filepath, 'wb') as f:
            f.write(data)
    else:
        print('Failed to decrypt file with the keys in ManagedPackageDataClient.win32.pkg')


def print_help(parser: object):
    parser.print_help()
    sys.exit(0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="DQX [en|de]cryptor")
    parser.add_argument(
        "action", choices=["encrypt", "decrypt", "bruteforce", "logger"],
        help="Specify an action."
    )
    parser.add_argument(
        "--file", nargs="?", const="arg_not_given",
        help="(opt) File to [en|de]crypt."
    )
    parser.add_argument(
        "--encryption-key", nargs="?", const="arg_not_given",
        help="(opt) Encryption key."
    )
    parser.add_argument(
        "--mpdc", nargs="?", const="arg_not_given",
        help="(opt) Path to the ManagedPackageDataClient file (for CRY files.)"
    )

    args = parser.parse_args()

    if not args.action:
        print_help(parser)

    agent = attach_client()

    if args.action == "encrypt":
        if not args.file or not args.encryption_key:
            print_help(parser)
        cli_encrypt(agent=agent, filepath=args.file, encryption_key=args.encryption_key)

    if args.action == "decrypt":
        if not args.file or not args.encryption_key:
            print_help(parser)
        cli_decrypt(agent=agent, filepath=args.file, encryption_key=args.encryption_key)

    if args.action == "bruteforce":
        if not args.file or not args.mpdc:
            print_help(parser)
        cli_bruteforce(agent=agent, filepath=args.file, managed_package_data_client_path=args.mpdc)

    if args.action == "logger":
        cli_logger(agent=agent)

    agent.detach_game()
