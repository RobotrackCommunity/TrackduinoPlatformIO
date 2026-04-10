import argparse
import csv
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from subprocess import CompletedProcess, CalledProcessError

# Constants
STRL_PATH_PIO_EXECUTABLE: list[str] = ["penv", "bin" if sys.platform.startswith("linux") else "Scripts", "pio"]

STR_SPEC_RED_TEXT = "\033[31m"
STR_SPEC_GREEN_TEXT = "\033[32m"
STR_SPEC_BLUE_TEXT = "\033[36m"
STR_SPEC_RESET_TEXT = "\033[0m"

# Variables
session: uuid.UUID = uuid.uuid4()
board: str

ide_path: Path
pio_path: Path
verbose_mode: bool = False
threads: int
excluded_libraries = []

print_lock: threading.Lock = threading.Lock()

results: list[list[str]] = [["Library", "IDE", "PIO"]]
is_win32: bool = sys.platform == "win32"
master_prefix: Path

total_count: int = 0
current_count: int = 0
passed_count: int = 0
passed_pio_count: int = 0
failed_count: int = 0
skipped_count: int = 0

is_aborted: bool = False
is_passed: bool = False


def _process_args():
    global verbose_mode, ide_path, pio_path, board, threads
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="PlatformIO self-test")
    parser.add_argument("-pi", "--path-ide", help="Path to RoboTrack IDE", required=True)
    parser.add_argument("-pp", "--path-pio", help="Path to PlatformIO package", required=True)
    parser.add_argument("-b", "--board", help="Board name", required=True)
    parser.add_argument("-v", "--verbose", action="store_true", help="Saves result of every tests")
    parser.add_argument("-t", "--threads", type=int, default=-1, help="Threads count (default max available)")

    args = parser.parse_args()

    ide_path = Path(args.path_ide)
    pio_path = Path(args.path_pio)
    verbose_mode = args.verbose
    board = args.board
    threads = int(args.threads) if int(args.threads) > 0 else os.cpu_count()


def _load_properties(filepath):
    props: dict = {}
    if not Path(filepath).exists():
        return props

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line: str = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue

            key, value = line.split('=', 1)
            props[key.strip()] = value.strip()
    return props


def _verbose_log(pio: CompletedProcess[str] | CalledProcessError, pio_status: bool,
                 ide: CompletedProcess[str] | CalledProcessError, ide_status: bool,
                 name: str):
    if verbose_mode:
        current_name: str = name.replace('/', '_').replace('\\', '_').strip()
        with open(Path("tests").joinpath(str(session)).joinpath(
                f"{current_name}.log"), "w", encoding="utf-8") as f:
            f.write(f"{name}\n" +
                    f"STDOUT IDE:\n" +
                    f"{'#' * 50}\n" +
                    f"{str(ide.stdout)}" +
                    f"{'#' * 50}\n" +
                    f"\n" +
                    f"STDERR IDE:\n" +
                    f"{'#' * 50}\n" +
                    f"{str(ide.stderr)}" +
                    f"{'#' * 50}" +
                    f"\n" +
                    f"STDOUT PIO:\n" +
                    f"{'#' * 50}\n" +
                    f"{str(pio.stdout)}" +
                    f"{'#' * 50}\n" +
                    f"\n" +
                    f"STDERR PIO:\n" +
                    f"{'#' * 50}\n" +
                    f"{str(pio.stderr)}" +
                    f"{'#' * 50}")
        results.append([name.replace('\\', '/'), str(int(ide_status)), str(int(pio_status))])


def _prepare_project(tmp: Path):
    global board
    _run_pio(tmp, f"init --board {board}")
    _run_pio(tmp, f"project config --json-output")
    _run_pio(tmp, f"project metadata --json-output -e {board} --json-output-path /tmp/pio.json")
    _run_pio(tmp, f"run -t compiledb -e {board}")


def _test_title(name: str):
    with print_lock:
        global total_count, current_count
        current_count += 1
        current_name: str = name.replace('\\', '/')
        print(f"{current_count}/{total_count}. {current_name}... ", end="")


def _test_skipped():
    with print_lock:
        print(f"{STR_SPEC_BLUE_TEXT}SKIPPED{STR_SPEC_RESET_TEXT}")
        global skipped_count
        skipped_count += 1


def _test_passed(special: bool = False):
    with print_lock:
        print(
            f"{STR_SPEC_GREEN_TEXT}PASSED{'* <Original IDE failed, PIO success>' if special else ''}{STR_SPEC_RESET_TEXT}")
        global passed_count, passed_pio_count
        passed_count += 1
        if special:
            passed_pio_count += 1


def _test_failed():
    with print_lock:
        print(f"{STR_SPEC_RED_TEXT}FAILED{STR_SPEC_RESET_TEXT}")
        global failed_count
        failed_count += 1


def _run_pio(library: Path, command: str):
    global pio_path, verbose_mode, STRL_PATH_PIO_EXECUTABLE, session
    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            str(pio_path.parent.parent.joinpath(*STRL_PATH_PIO_EXECUTABLE).absolute()) + " " + command,
            cwd=str(library.absolute()),
            shell=True,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result
    except subprocess.CalledProcessError as e:
        return False, e


def _get_board_id() -> str:
    global ide_path, board
    for hardware in [f for f in
                     ide_path.joinpath("hardware").iterdir() if
                     f.is_dir()]:
        for framework in [f for f in
                          hardware.iterdir() if
                          f.is_dir()]:
            boards: Path = list(framework.glob("boards.txt"))[0] if len(list(framework.glob("boards.txt"))) else None
            with open(boards, "r", encoding="utf-8") as f:
                if f"{board.lower()}" in f.read():
                    return f"{hardware.name}:{framework.name}:{board.lower()}"
    return ""


def _gen_master_prefix(prefix: Path):
    global master_prefix, ide_path

    prefix.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["WINEPREFIX"] = str(prefix.absolute())
    env["WINEDEBUG"] = "-all"

    cmd = ["wineboot", "--init"]
    subprocess.run(cmd,
                   env=env,
                   check=True,
                   shell=True,
                   capture_output=True,
                   text=True)
    shutil.copytree(ide_path, prefix.joinpath("drive_c").joinpath(ide_path.name))
    master_prefix = prefix.absolute()


def _test_ide(ino_path: Path):
    global master_prefix, is_win32, ide_path
    full_board_name: str = _get_board_id()
    with tempfile.TemporaryDirectory() as pre_sketch_dir:
        sketch_dir = Path(pre_sketch_dir).joinpath(ino_path.stem)
        shutil.copytree(ino_path.parent, sketch_dir)
        target_ino = sketch_dir.joinpath(ino_path.name)

        with tempfile.TemporaryDirectory() as local_prefix_dir:
            if not is_win32:
                local_prefix = Path(local_prefix_dir)
                shutil.copytree(master_prefix, local_prefix, dirs_exist_ok=True, symlinks=True)
            ide_executable = \
                [f for f in
                 (ide_path.iterdir() if is_win32 else local_prefix.joinpath("drive_c").joinpath(
                     ide_path.relative_to(ide_path.parent).name).iterdir())
                 if f.name.endswith("(debug).exe")][0]

            if not is_win32:
                env = os.environ.copy()
                env["WINEPREFIX"] = str(local_prefix.absolute())
                env["WINEDEBUG"] = "-all"

            prefix = f'{str(ide_executable.absolute())}' if is_win32 else f'{ide_executable.absolute()}'
            z_drive = 'Z:' if not is_win32 else ''
            target_path = f"{'' if is_win32 else z_drive}{target_ino.absolute()}"
            if is_win32:
                cmd = [prefix, "--verify", "--board", full_board_name, target_path]
            else:
                cmd = ["wine", prefix, "--verify", "--board", full_board_name, target_path]

            try:
                if is_win32:
                    result = subprocess.run(
                        cmd,
                        check=True,
                        cwd=str(ide_path.absolute()),
                        capture_output=True,
                        text=True
                    )
                else:
                    result = subprocess.run(
                        cmd,
                        cwd=str(local_prefix.joinpath("drive_c").joinpath(
                            ide_path.relative_to(ide_path.parent).name).absolute()),
                        check=True,
                        capture_output=True,
                        text=True,
                        env=env
                    )
                return "exit status 1" not in str(result.stderr), result
            except subprocess.CalledProcessError as e:
                return False, e


def _remove_comments(code: str) -> str:
    result = []
    i = 0
    n = len(code)

    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False

    while i < n:
        c = code[i]
        nxt = code[i + 1] if i + 1 < n else ''

        if in_line_comment:
            if c == '\n':
                in_line_comment = False
                result.append(c)
            i += 1
            continue

        if in_block_comment:
            if c == '*' and nxt == '/':
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue

        if in_single:
            result.append(c)
            if c == '\\':
                if i + 1 < n:
                    result.append(code[i + 1])
                    i += 2
                    continue
            elif c == "'":
                in_single = False
            i += 1
            continue

        if in_double:
            result.append(c)
            if c == '\\':
                if i + 1 < n:
                    result.append(code[i + 1])
                    i += 2
                    continue
            elif c == '"':
                in_double = False
            i += 1
            continue

        if c == '/' and nxt == '/':
            in_line_comment = True
            i += 2
            continue

        if c == '/' and nxt == '*':
            in_block_comment = True
            i += 2
            continue

        if c == "'":
            in_single = True
            result.append(c)
            i += 1
            continue

        if c == '"':
            in_double = True
            result.append(c)
            i += 1
            continue

        result.append(c)
        i += 1

    return ''.join(result)


def _fix_ino_to_cpp(unfiltered_content: str):
    content: str = _remove_comments(unfiltered_content)

    pattern = r'^\s*(?!if\b|else\b|for\b|while\b|switch\b)([a-zA-Z_][a-zA-Z0-9_*&:\s]+)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(([^)]*)\)\s*\{'

    prototypes: list[str] = []

    for m in re.finditer(pattern, content, re.MULTILINE):
        func_name = m.group(2)
        full = m.group(0).strip()
        if func_name in ("setup", "loop"):
            continue

        if full.startswith(("if", "else", "for", "while", "switch")):
            continue

        proto: str = m.group(0).split('{')[0].strip() + ";"
        prototypes.append(proto)

    header_parts = []

    if "#include <Arduino.h>" not in content:
        header_parts.append("#include <Arduino.h>")

    header_parts.append("// --- INO to CPP fix ---")
    header_parts.extend(prototypes)
    header_parts.append("// -------------------------------\n")

    header = "\n".join(header_parts)

    include_matches = list(re.finditer(r'^\s*#include[^\n]*', content, re.MULTILINE))
    if include_matches:
        last_include = include_matches[-1]
        insert_pos = last_include.end()
        result = content[:insert_pos] + "\n\n" + header + content[insert_pos:]
    else:
        result = header + "\n\n" + content

    return result


def _test_example(example: Path, library: Path):
    global board
    with tempfile.TemporaryDirectory() as example_dir:
        ide_status, ide_result = _test_ide(example.joinpath(f"{example.name}.ino"))
        tmp = Path(example_dir)
        _prepare_project(tmp)

        with open(tmp.joinpath("src").joinpath("main.cpp"), "w") as main:
            with open(example.joinpath(f"{example.name}.ino"), "r") as ino:
                main.write(_fix_ino_to_cpp(ino.read()))

        shutil.copytree(example, tmp.joinpath("src"), dirs_exist_ok=True)
        for ino in tmp.joinpath("src").rglob("*.ino"):
            Path(ino).unlink()

        _prepare_project(tmp)
        pio_status, pio_result = _run_pio(tmp, f"run -e {board}")
        name: str = f"{library.name}/{example.relative_to(library.joinpath('examples'))}"
        _test_title(name)
        if (not ide_status) and (not pio_status):
            _test_skipped()
        elif ide_status and (not pio_status):
            _test_failed()
        elif (not ide_status) and pio_status:
            _test_passed(True)
        elif ide_status and pio_status:
            _test_passed()
        _verbose_log(pio_result, pio_status, ide_result, ide_status, name)


def _test():
    global pio_path, results, master_prefix, is_aborted, failed_count, passed_count, passed_pio_count, skipped_count, total_count, is_passed, threads, excluded_libraries
    if verbose_mode:
        Path("tests").joinpath(str(session)).mkdir(parents=True, exist_ok=True)
    tasks = []
    for library in [f for f in
                    pio_path.joinpath("libraries").iterdir() if
                    f.is_dir()]:
        if library.name in [f[0] for f in excluded_libraries]:
            continue
        examples_path = library.joinpath("examples")
        if examples_path.exists():
            found_examples = [
                f for f in examples_path.rglob("*")
                if f.is_dir() and any(f.glob("*.ino"))
            ]
            for ex in found_examples:
                tasks.append((ex, library))

    total_count = len(tasks)

    print()
    print("=" * 50)
    print("Session Id:", session)
    print("Verbose Mode:", verbose_mode)
    print("Use wine:", not is_win32)
    print("Threads:", threads)
    print("Sketches count:", total_count)
    if len(excluded_libraries) > 0:
        print("Excluded libraries:", end=" ")
        print(*[f[0] for f in excluded_libraries], sep=", ")
    print("=" * 50)
    print()

    if len(excluded_libraries) > 0:
        print("Excluding reasons")
        for ex in excluded_libraries:
            print(f'- {ex[0]}: {ex[1]}')
        print()

    if not is_win32:
        print("+ Preparing WINE master prefix...")
        _gen_master_prefix(Path(tempfile.gettempdir()).joinpath(f"__master_wine_{session}"))
        print("+ WINE master prefix generated!")
        print()

    print(f"Libraries self test (It can take few minutes)...")
    executor = None
    try:
        executor = ThreadPoolExecutor(max_workers=threads)
        futures = [executor.submit(_test_example, *p) for p in tasks]

        for future in futures:
            try:
                future.result()
            except Exception as e:
                print(f"Thread crash: {e}")
    except KeyboardInterrupt:
        is_aborted = True
        if executor:
            executor.shutdown(wait=False, cancel_futures=True)

    if verbose_mode:
        with open(Path("tests").joinpath(str(session)).joinpath("__result.cvs"), "w", newline='',
                  encoding="utf-8") as f:
            csv.writer(f).writerows(results)

    result_text: str
    if is_aborted:
        result_text = f"{STR_SPEC_RED_TEXT}ABORTED{STR_SPEC_RESET_TEXT}"
    elif failed_count > 0:
        result_text = f"{STR_SPEC_RED_TEXT}FAILED{STR_SPEC_RESET_TEXT}"
    elif failed_count == 0 and passed_count == 0:
        result_text = f"{STR_SPEC_BLUE_TEXT}SKIPPED{STR_SPEC_RESET_TEXT}"
    else:
        is_passed = True
        result_text = f"{STR_SPEC_GREEN_TEXT}PASSED{STR_SPEC_RESET_TEXT}"

    print(
        f"\nTest result: {result_text} <{total_count} total, {skipped_count} skipped, {passed_pio_count} passed*/{passed_count} passed{f', {failed_count} failed' if failed_count > 0 else ''}, {len(excluded_libraries)} excluded>")
    if not is_win32:
        shutil.rmtree(master_prefix, ignore_errors=True)
    return is_passed


def run(l_ide_path: Path, l_pio_path: Path, l_board: str, l_excluded_libraries: list, l_verbose_mode: bool = False,
        l_threads: int = -1):
    global verbose_mode, ide_path, pio_path, board, threads, excluded_libraries

    verbose_mode = l_verbose_mode
    ide_path = l_ide_path
    pio_path = l_pio_path
    board = l_board
    threads = l_threads if l_threads > 0 else os.cpu_count()
    excluded_libraries = l_excluded_libraries

    return _test()


if __name__ == '__main__':
    _process_args()
    exit(int(not _test()))
