from pathlib import Path
import json
import argparse
import shutil

# Dynamic information
IDE_NAME: str = "RoboTrack IDE"
IDE_INSTALL_URL: str = "https://robotrack-rus.ru/wiki/doku.php/po/robotrekide"
IDE_EXECUTABLE: str = "Robotrack IDE.exe"
IDE_PLATFORM: str = "robotrack"

BOARD_NAME: str = "Trackduino"
BOARD_INFO_URL: str = "https://robotrack-rus.ru/wiki/doku.php/ehlektronika/trekduino"
BOARD_ID: str = "trackduino"
BOARD_VENDOR: str = "Brain Development"

EXCLUDED_LIBRARIES: list[tuple[str, str]] = [  # ("Library Folder Name", "Excluding reason")
    ("RobotrackIoTClient", "https://github.com/RobotrackCommunity/TrackduinoPlatformIO/issues/1"),
    ("Adafruit_Circuit_Playground", f"Fully broken for {BOARD_NAME}"),
    ("Robot_Control", f"Fully broken for {BOARD_NAME}"),
    ("Esplora", f"Fully broken for {BOARD_NAME}"),
    ("GSM", f"Fully broken for {BOARD_NAME}"),
    ("Servo", f"Fully broken for {BOARD_NAME}"),
    ("Firmata", f"Fully broken for {BOARD_NAME}")
]

# PIO info
PACKAGE_NAME: str = f"framework-arduino-avr-{BOARD_ID}"
BOARD_JSON: dict = {
    "name": BOARD_NAME,
    "url": BOARD_INFO_URL,
    "vendor": BOARD_VENDOR,
    "build": {
        "extra_flags": "-DARDUINO_AVR_MEGA2560",
        "f_cpu": "16000000L",
        "mcu": "atmega2560",
        "core": BOARD_ID,
        "variant": BOARD_ID
    },
    "frameworks": [
        "arduino"
    ],
    "platforms": ["atmelavr"],
    "package": PACKAGE_NAME,
    "bootloader": {
        "unlock_bits": "0x3F",
        "lock_bits": "0x0F",
        "low_fuses": "0xFF",
        "high_fuses": "0xD8",
        "extended_fuses": "0xFD",
        "file": "stk500v2/stk500boot_v2_mega2560.hex"
    },
    "upload": {
        "maximum_ram_size": 8192,
        "maximum_size": 253952,
        "protocol": "wiring",
        "require_upload_port": True,
        "speed": 115200
    }
}

PLATFORM_JSON: dict = {
    "type": "framework",
    "optional": True
}

PACKAGE_JSON: dict = {
    "name": f"{PACKAGE_NAME}",
    "version": "%IDE_VERSION%",
    "description": f"Modified Arduino AVR framework for working with {BOARD_NAME}",
    "keywords": [
        "framework",
        "arduino",
        "microchip",
        "avr"
    ],
    "homepage": f"{IDE_INSTALL_URL}"
}

# Constants strings
STR_PIO_INSTALL_URL: str = "https://docs.platformio.org/en/latest/core/installation/methods/installer-script.html"

STRL_PATH_PIO_PLATFORM: list[str] = ["platforms", "atmelavr"]
STRL_PATH_PIO_PACKAGES: list[str] = ["packages"]

STRL_PATH_IDE_PLATFORM: list[str] = ["hardware", IDE_PLATFORM, "avr"]

STR_SPEC_RED_TEXT = "\033[31m"
STR_SPEC_GREEN_TEXT = "\033[32m"
STR_SPEC_BLUE_TEXT = "\033[36m"
STR_SPEC_RESET_TEXT = "\033[0m"

# Variables
ide_path: Path
pio_path: Path

test_verbose: bool = False
test_threads: int = -1

ide_version: str

skip_check: bool


def process_args():
    global ide_path, skip_check, test_verbose, test_threads
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description=f"{BOARD_NAME} for PlatformIO converter")
    parser.add_argument("-p", "--path", help=f"Path to {IDE_NAME}", required=True)
    parser.add_argument("-s", "--skip-check", action="store_true", help="Skip automatic check of PlatformIO board")
    parser.add_argument("-v", "--verbose", action="store_true", help="(For test) Saves result of every tests")
    parser.add_argument("-t", "--threads", type=int, default=-1,
                        help="(For test) Threads count (default max available)")

    args = parser.parse_args()

    ide_path = get_ide_path(args.path)
    skip_check = args.skip_check

    test_verbose = args.verbose
    test_threads = args.threads


def get_ide_path(ide_location: str) -> Path:
    path: Path = Path(ide_location)
    if not path.exists():
        print(f"{STR_SPEC_RED_TEXT}{IDE_NAME} not installed ({IDE_INSTALL_URL}){STR_SPEC_RESET_TEXT}")
        exit(1)
    elif not path.joinpath(IDE_EXECUTABLE).exists():
        print(f"{STR_SPEC_RED_TEXT}{IDE_NAME} install broken ({IDE_INSTALL_URL}){STR_SPEC_RESET_TEXT}")
        exit(1)
    return Path(ide_location).absolute()


def get_ide_version(ide_location: Path) -> str:
    with open(ide_location.joinpath("revisions.txt"), "r", encoding="ISO-8859-1") as revisions_file:
        return revisions_file.readline()[14:].strip()


def get_pio_path() -> Path:
    path: Path = Path.home().joinpath(".platformio")
    if not path.exists():
        print(f"{STR_SPEC_RED_TEXT}PlatformIO not installed ({STR_PIO_INSTALL_URL}){STR_SPEC_RESET_TEXT}")
        exit(1)
    elif not path.joinpath("penv").exists():
        print(f"{STR_SPEC_RED_TEXT}PlatformIO install broken ({STR_PIO_INSTALL_URL}){STR_SPEC_RESET_TEXT}")
        exit(1)
    return path.absolute()


# Adding package and board to PIO
def add_package_to_platforms():
    global pio_path, STRL_PATH_PIO_PLATFORM
    path: Path = pio_path.joinpath(*STRL_PATH_PIO_PLATFORM).joinpath("platform.json")
    with open(path, "r", encoding="UTF-8") as json_file:
        json_data: dict = json.load(json_file)
    packages: dict = json_data["packages"]
    if PACKAGE_NAME not in packages.keys():
        packages[PACKAGE_NAME] = PLATFORM_JSON
    json_data["packages"] = packages
    with open(path, "w", encoding="UTF-8") as json_file:
        json.dump(json_data, json_file, indent=4)


def copy_package():
    global ide_path, pio_path, STRL_PATH_IDE_PLATFORM, STRL_PATH_PIO_PACKAGES, PACKAGE_NAME
    source: Path = ide_path.joinpath(*STRL_PATH_IDE_PLATFORM)
    destination: Path = pio_path.joinpath(*STRL_PATH_PIO_PACKAGES).joinpath(PACKAGE_NAME)

    shutil.copytree(source, destination, dirs_exist_ok=True)
    destination.joinpath("cores").joinpath("arduino").rename(destination.joinpath("cores").joinpath(BOARD_ID))


def copy_libraries():
    global ide_path, pio_path, STRL_PATH_IDE_PLATFORM, STRL_PATH_PIO_PACKAGES, PACKAGE_NAME
    source: Path = ide_path.joinpath("libraries")
    destination: Path = pio_path.joinpath(*STRL_PATH_PIO_PACKAGES).joinpath(PACKAGE_NAME).joinpath("libraries")

    for item in source.iterdir():
        if item.is_dir():
            dest_item = destination.joinpath(item.name)
            if not dest_item.exists():
                shutil.copytree(item, dest_item)

    for library in [f for f in destination.iterdir() if f.is_dir()]:
        if not library.joinpath("src").exists():
            continue
        shutil.copytree(library.joinpath("src"), library, dirs_exist_ok=True)
        shutil.rmtree(library.joinpath("src"))


def add_package_json():
    global pio_path, STRL_PATH_PIO_PACKAGES, PACKAGE_NAME, PACKAGE_JSON
    file: Path = pio_path.joinpath(*STRL_PATH_PIO_PACKAGES).joinpath(PACKAGE_NAME).joinpath("package.json")
    PACKAGE_JSON["version"] = ide_version
    with open(file, "w", encoding="UTF-8") as json_file:
        json.dump(PACKAGE_JSON, json_file, indent=4)


def add_board():
    global pio_path, STRL_PATH_PIO_PLATFORM, BOARD_JSON
    path: Path = pio_path.joinpath(*STRL_PATH_PIO_PLATFORM).joinpath("boards").joinpath(f"{BOARD_ID}.json")
    with open(path, "w", encoding="UTF-8") as json_file:
        json.dump(BOARD_JSON, json_file, indent=4)


# Removing package and board from PIO
def remove_package_to_platforms():
    global pio_path, STRL_PATH_PIO_PLATFORM
    path: Path = pio_path.joinpath(*STRL_PATH_PIO_PLATFORM).joinpath("platform.json")
    with open(path, "r", encoding="UTF-8") as json_file:
        json_data: dict = json.load(json_file)
    packages: dict = json_data["packages"]
    packages.pop(PACKAGE_NAME, None)
    json_data["packages"] = packages
    with open(path, "w", encoding="UTF-8") as json_file:
        json.dump(json_data, json_file, indent=4)


def delete_package():
    global ide_path, pio_path, STRL_PATH_PIO_PACKAGES, PACKAGE_NAME
    destination: Path = pio_path.joinpath(*STRL_PATH_PIO_PACKAGES).joinpath(PACKAGE_NAME)
    shutil.rmtree(destination, ignore_errors=True)


def delete_board():
    global pio_path, STRL_PATH_PIO_PLATFORM, BOARD_JSON
    pio_path.joinpath(*STRL_PATH_PIO_PLATFORM).joinpath("boards").joinpath(f"{BOARD_ID}.json").unlink(missing_ok=True)


# Highest functions
def new_install():
    print("Installing new...")
    print("- Registering package...")
    add_package_to_platforms()
    print("- Copying package...")
    copy_package()
    print("- Copying libraries...")
    copy_libraries()
    print("- Adding package file...")
    add_package_json()
    print("- Adding board...")
    add_board()
    print("Install done!", end="\n\n")


def cleanup():
    print(f"Cleaning current installation...")
    print("- Unregistering package...")
    remove_package_to_platforms()
    print("- Deleting package...")
    delete_package()
    print("- Deleting board...")
    delete_board()
    print("Current installation deleted!", end="\n\n")


def main():
    global ide_path, ide_version, pio_path, skip_check
    process_args()
    ide_version = get_ide_version(ide_path)
    print(f"{IDE_NAME} path: {ide_path}")
    print(f"{IDE_NAME} version: {ide_version}")

    pio_path = get_pio_path()
    print(f"PlatformIO path: {pio_path}", end="\n\n")

    cleanup()
    new_install()

    if not skip_check:
        import test
        test.run(ide_path, pio_path.joinpath(*STRL_PATH_PIO_PACKAGES).joinpath(PACKAGE_NAME), BOARD_ID,
                 EXCLUDED_LIBRARIES, test_verbose, test_threads)
    else:
        print("Self test skipped")

    print("Everything is done!")


if __name__ == '__main__':
    main()
