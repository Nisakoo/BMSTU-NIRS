# /// script
# requires-python = ">=3.12"
# dependencies = ["cryptography==50.0.2"]
# ///
"""Шифрование локальных данных RAG: ``data/`` <-> ``encrypted/data.enc``.

Каталог ``data/`` игнорируется Git, в репозиторий попадает только
зашифрованный архив. Ключ выводится из кодовой фразы через scrypt, архив
шифруется AES-256-GCM. Кодовая фраза никогда не печатается и не сохраняется.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import hashlib
import io
import os
import secrets
import shutil
import sys
import tarfile
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

DATA_DIR = "data"
ENCRYPTED_FILE = PurePosixPath("encrypted/data.enc")

MAGIC = b"SMSHAI-DATA"
FORMAT_VERSION = 1
SCRYPT_LOG2_N = 17
SCRYPT_R = 8
SCRYPT_P = 1
SALT_SIZE = 16
NONCE_SIZE = 12
KEY_SIZE = 32
TAG_SIZE = 16
HEADER_SIZE = len(MAGIC) + 4 + SALT_SIZE + NONCE_SIZE
MIN_PASSPHRASE_LENGTH = 12
SKIPPED_NAMES = frozenset({".DS_Store", ".git"})
MAX_LISTED_PATHS = 20

WRONG_PASSPHRASE = "Неверная кодовая фраза или файл повреждён."

# Снимок каталога: путь -> SHA-256 файла или None для каталога.
Snapshot = dict[str, str | None]


class DataCryptError(Exception):
    """Ожидаемая ошибка: сообщение показывается пользователю как есть."""


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


# --- Ключ и шифрование ---------------------------------------------------


def _derive_key(passphrase: str, salt: bytes, log2_n: int, r: int, p: int) -> bytes:
    n = 1 << log2_n
    return hashlib.scrypt(
        _nfc(passphrase).encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=256 * r * (n + p),
        dklen=KEY_SIZE,
    )


def encrypt_payload(payload: bytes, passphrase: str) -> bytes:
    salt = secrets.token_bytes(SALT_SIZE)
    nonce = secrets.token_bytes(NONCE_SIZE)
    header = (
        MAGIC
        + bytes([FORMAT_VERSION, SCRYPT_LOG2_N, SCRYPT_R, SCRYPT_P])
        + salt
        + nonce
    )
    key = _derive_key(passphrase, salt, SCRYPT_LOG2_N, SCRYPT_R, SCRYPT_P)
    return header + AESGCM(key).encrypt(nonce, payload, header)


def decrypt_payload(blob: bytes, passphrase: str) -> bytes:
    if len(blob) < HEADER_SIZE + TAG_SIZE or not blob.startswith(MAGIC):
        raise DataCryptError(f"{ENCRYPTED_FILE} не является архивом данных.")
    offset = len(MAGIC)
    version, log2_n, r, p = blob[offset : offset + 4]
    if version != FORMAT_VERSION:
        raise DataCryptError(
            f"Версия формата {version} не поддерживается, ожидается {FORMAT_VERSION}."
        )
    if not (14 <= log2_n <= 20 and 1 <= r <= 16 and 1 <= p <= 4):
        raise DataCryptError(f"{ENCRYPTED_FILE}: недопустимые параметры ключа.")
    offset += 4
    salt = blob[offset : offset + SALT_SIZE]
    nonce = blob[offset + SALT_SIZE : HEADER_SIZE]
    key = _derive_key(passphrase, salt, log2_n, r, p)
    try:
        return AESGCM(key).decrypt(nonce, blob[HEADER_SIZE:], blob[:HEADER_SIZE])
    except InvalidTag:
        raise DataCryptError(WRONG_PASSPHRASE) from None


# --- Каталог data/ -------------------------------------------------------


def _collect(data_dir: Path) -> list[tuple[str, Path]]:
    """Пути каталога в детерминированном порядке; ссылки и спецфайлы — ошибка."""
    entries: list[tuple[str, Path]] = []
    for current, dirs, files in os.walk(data_dir):
        base = Path(current)
        dirs[:] = sorted(name for name in dirs if name not in SKIPPED_NAMES)
        for name in [*dirs, *sorted(files)]:
            if name in SKIPPED_NAMES:
                continue
            path = base / name
            relative = _nfc(path.relative_to(data_dir).as_posix())
            if path.is_symlink():
                raise DataCryptError(
                    f"{DATA_DIR}/{relative}: символьные ссылки не поддерживаются."
                )
            if not (path.is_dir() or path.is_file()):
                raise DataCryptError(
                    f"{DATA_DIR}/{relative}: поддерживаются только файлы и папки."
                )
            entries.append((relative, path))
    entries.sort(key=lambda entry: entry[0])
    return entries


def _check_data_dir(data_dir: Path) -> None:
    if data_dir.is_symlink():
        raise DataCryptError(f"{DATA_DIR}/ не может быть символьной ссылкой.")


def snapshot_dir(data_dir: Path) -> Snapshot:
    if not data_dir.exists():
        return {}
    _check_data_dir(data_dir)
    return {
        relative: (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )
        for relative, path in _collect(data_dir)
    }


def build_archive(data_dir: Path) -> tuple[bytes, Snapshot]:
    """Детерминированный tar.gz содержимого data/ и его снимок."""
    if not data_dir.is_dir():
        raise DataCryptError(f"Папка {DATA_DIR}/ не найдена.")
    _check_data_dir(data_dir)
    entries = _collect(data_dir)
    if not any(path.is_file() for _, path in entries):
        raise DataCryptError(f"Папка {DATA_DIR}/ пуста: шифровать нечего.")

    snapshot: Snapshot = {}
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for relative, path in entries:
            info = tarfile.TarInfo(relative)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                tar.addfile(info)
                snapshot[relative] = None
            else:
                content = path.read_bytes()
                info.mode = 0o644
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
                snapshot[relative] = hashlib.sha256(content).hexdigest()
    return gzip.compress(raw.getvalue(), mtime=0), snapshot


def _open_archive(payload: bytes) -> tarfile.TarFile:
    try:
        return tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz")
    except (tarfile.TarError, OSError, EOFError):
        raise DataCryptError(WRONG_PASSPHRASE) from None


def snapshot_archive(payload: bytes) -> Snapshot:
    snapshot: Snapshot = {}
    with _open_archive(payload) as tar:
        for member in tar.getmembers():
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts:
                raise DataCryptError(f"Архив содержит недопустимый путь: {name}.")
            if member.isdir():
                snapshot[_nfc(member.name)] = None
            elif member.isfile():
                extracted = tar.extractfile(member)
                assert extracted is not None
                digest = hashlib.sha256(extracted.read()).hexdigest()
                snapshot[_nfc(member.name)] = digest
            else:
                raise DataCryptError(
                    f"Архив содержит неподдерживаемый элемент: {name}."
                )
    return snapshot


def _differences(left: Snapshot, right: Snapshot) -> list[str]:
    return sorted(
        path
        for path in left.keys() | right.keys()
        if left.get(path, "missing") != right.get(path, "missing")
    )


def _format_paths(paths: list[str]) -> str:
    shown = [f"  {DATA_DIR}/{path}" for path in paths[:MAX_LISTED_PATHS]]
    if len(paths) > MAX_LISTED_PATHS:
        shown.append(f"  … и ещё {len(paths) - MAX_LISTED_PATHS}")
    return "\n".join(shown)


# --- Кодовая фраза -------------------------------------------------------


def read_passphrase(*, from_stdin: bool, confirm: bool) -> str:
    if from_stdin:
        passphrase = sys.stdin.readline().rstrip("\r\n")
    else:
        if not sys.stdin.isatty():
            raise DataCryptError(
                "Нет терминала для ввода кодовой фразы. Запустите команду в терминале."
            )
        passphrase = getpass.getpass("Кодовая фраза: ")
        if confirm and getpass.getpass("Повторите кодовую фразу: ") != passphrase:
            raise DataCryptError("Кодовые фразы не совпадают.")
    if not passphrase:
        raise DataCryptError("Кодовая фраза пуста.")
    return passphrase


# --- Команды -------------------------------------------------------------


def encrypt(root: Path, *, from_stdin: bool) -> str:
    payload, snapshot = build_archive(root / DATA_DIR)
    passphrase = read_passphrase(from_stdin=from_stdin, confirm=True)
    if len(passphrase) < MIN_PASSPHRASE_LENGTH:
        raise DataCryptError(f"Кодовая фраза короче {MIN_PASSPHRASE_LENGTH} символов.")

    target = root / ENCRYPTED_FILE
    if target.is_file():
        try:
            previous = snapshot_archive(
                decrypt_payload(target.read_bytes(), passphrase)
            )
        except DataCryptError:
            print(
                f"Внимание: прежний {ENCRYPTED_FILE} не открывается этой фразой "
                "и будет перезаписан.",
                file=sys.stderr,
            )
        else:
            if previous == snapshot:
                return f"Данные не изменились: {ENCRYPTED_FILE} не перезаписан."

    blob = encrypt_payload(payload, passphrase)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
        temporary.write(blob)
    os.chmod(temporary.name, 0o644)
    os.replace(temporary.name, target)
    files = sum(1 for digest in snapshot.values() if digest is not None)
    return f"Записан {ENCRYPTED_FILE}: файлов — {files}."


def decrypt(root: Path, *, from_stdin: bool, force: bool) -> str:
    source = root / ENCRYPTED_FILE
    if not source.is_file():
        raise DataCryptError(f"{ENCRYPTED_FILE} не найден.")
    data_dir = root / DATA_DIR
    current = snapshot_dir(data_dir)

    passphrase = read_passphrase(from_stdin=from_stdin, confirm=False)
    payload = decrypt_payload(source.read_bytes(), passphrase)
    expected = snapshot_archive(payload)

    if current == expected:
        return f"{DATA_DIR}/ уже совпадает с {ENCRYPTED_FILE}."
    if current and not force:
        raise DataCryptError(
            f"{DATA_DIR}/ отличается от {ENCRYPTED_FILE}:\n"
            f"{_format_paths(_differences(current, expected))}\n"
            "Сохраните изменения командой make data-encrypt или замените "
            "папку командой make data-decrypt FORCE=1."
        )

    workspace = Path(tempfile.mkdtemp(dir=root, prefix=".data-decrypt-"))
    try:
        restored = workspace / DATA_DIR
        restored.mkdir()
        with _open_archive(payload) as tar:
            tar.extractall(restored, filter="data")
        if data_dir.exists():
            for name in SKIPPED_NAMES:
                if (data_dir / name).exists():
                    os.replace(data_dir / name, restored / name)
            os.replace(data_dir, workspace / "previous")
        os.replace(restored, data_dir)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    files = sum(1 for digest in expected.values() if digest is not None)
    return f"{DATA_DIR}/ восстановлена из {ENCRYPTED_FILE}: файлов — {files}."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="data_crypt",
        description="Шифрование data/ в encrypted/data.enc и обратно.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="корень репозитория (по умолчанию текущий каталог)",
    )
    parser.add_argument(
        "--passphrase-stdin",
        action="store_true",
        help="читать кодовую фразу из первой строки stdin (для автоматизации)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("encrypt", help="зашифровать data/")
    decrypt_parser = commands.add_parser("decrypt", help="восстановить data/")
    decrypt_parser.add_argument(
        "--force",
        action="store_true",
        help="заменить data/, даже если она отличается от архива",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()

    try:
        if args.command == "encrypt":
            message = encrypt(root, from_stdin=args.passphrase_stdin)
        else:
            message = decrypt(root, from_stdin=args.passphrase_stdin, force=args.force)
    except DataCryptError as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    print(message)
    return 0


if __name__ == "__main__":
    sys.exit(main())
