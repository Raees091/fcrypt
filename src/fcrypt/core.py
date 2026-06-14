"""
fcrypt core: password-based authenticated file encryption.

Format (.fcr):
    magic        : 8 bytes  b"FCRYPT01"
    salt         : 16 bytes (scrypt salt)
    nonce        : 12 bytes (AES-GCM nonce)
    name_len     : 2 bytes  big-endian (length of original filename, utf-8)
    name_ct      : name_len bytes (encrypted original filename, part of ciphertext)
    ciphertext   : remainder (AES-256-GCM, includes 16-byte tag)

Crypto:
    KDF      : scrypt (n=2**15, r=8, p=1) -> 32-byte key
    Cipher   : AES-256-GCM (authenticated; tampering is detected)

The original filename is stored encrypted inside the AEAD ciphertext as
associated plaintext so it is both confidential and tamper-protected.
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"FCRYPT01"
SALT_LEN = 16
NONCE_LEN = 12
KEY_LEN = 32

# scrypt parameters
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1

ENC_SUFFIX = ".fcr"


class FcryptError(Exception):
    """Base error for fcrypt operations."""


class WrongPasswordError(FcryptError):
    """Raised when decryption fails (bad password or corrupted file)."""


class BadFileError(FcryptError):
    """Raised when a file is not a valid fcrypt container."""


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=KEY_LEN, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P)
    return kdf.derive(password.encode("utf-8"))


@dataclass
class CryptoResult:
    out_path: str
    original_name: str
    in_bytes: int
    out_bytes: int


def is_encrypted_file(path: str) -> bool:
    """Return True if the file starts with the fcrypt magic header."""
    try:
        with open(path, "rb") as f:
            return f.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def encrypt_file(
    in_path: str,
    password: str,
    out_path: str | None = None,
    overwrite: bool = False,
) -> CryptoResult:
    """Encrypt a file. Returns info about the produced container."""
    if not os.path.isfile(in_path):
        raise FcryptError(f"Not a file: {in_path}")

    original_name = os.path.basename(in_path)
    if out_path is None:
        out_path = in_path + ENC_SUFFIX

    if os.path.exists(out_path) and not overwrite:
        raise FcryptError(f"Output already exists: {out_path}")

    with open(in_path, "rb") as f:
        data = f.read()

    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    key = _derive_key(password, salt)
    aes = AESGCM(key)

    name_bytes = original_name.encode("utf-8")
    # payload = name_len(2) + name + filedata, all encrypted together
    payload = struct.pack(">H", len(name_bytes)) + name_bytes + data
    ciphertext = aes.encrypt(nonce, payload, MAGIC)

    tmp_path = out_path + ".part"
    with open(tmp_path, "wb") as f:
        f.write(MAGIC)
        f.write(salt)
        f.write(nonce)
        f.write(ciphertext)
    os.replace(tmp_path, out_path)

    return CryptoResult(
        out_path=out_path,
        original_name=original_name,
        in_bytes=len(data),
        out_bytes=os.path.getsize(out_path),
    )


def peek_original_name(in_path: str, password: str) -> str:
    """Decrypt only enough to recover the original filename."""
    name, _ = _decrypt_payload(in_path, password)
    return name


def _decrypt_payload(in_path: str, password: str) -> tuple[str, bytes]:
    with open(in_path, "rb") as f:
        blob = f.read()

    header = len(MAGIC) + SALT_LEN + NONCE_LEN
    if len(blob) < header or blob[: len(MAGIC)] != MAGIC:
        raise BadFileError("Not an fcrypt file (bad magic header).")

    off = len(MAGIC)
    salt = blob[off : off + SALT_LEN]
    off += SALT_LEN
    nonce = blob[off : off + NONCE_LEN]
    off += NONCE_LEN
    ciphertext = blob[off:]

    key = _derive_key(password, salt)
    aes = AESGCM(key)
    try:
        payload = aes.decrypt(nonce, ciphertext, MAGIC)
    except Exception as exc:  # InvalidTag etc.
        raise WrongPasswordError(
            "Decryption failed: wrong password or corrupted file."
        ) from exc

    if len(payload) < 2:
        raise BadFileError("Corrupted container payload.")
    name_len = struct.unpack(">H", payload[:2])[0]
    name = payload[2 : 2 + name_len].decode("utf-8", errors="replace")
    data = payload[2 + name_len :]
    return name, data


def decrypt_file(
    in_path: str,
    password: str,
    out_path: str | None = None,
    overwrite: bool = False,
) -> CryptoResult:
    """Decrypt an fcrypt container back to the original file."""
    if not os.path.isfile(in_path):
        raise FcryptError(f"Not a file: {in_path}")

    original_name, data = _decrypt_payload(in_path, password)

    if out_path is None:
        directory = os.path.dirname(os.path.abspath(in_path))
        if in_path.endswith(ENC_SUFFIX):
            candidate = in_path[: -len(ENC_SUFFIX)]
        else:
            candidate = os.path.join(directory, original_name)
        out_path = candidate

    if os.path.exists(out_path) and not overwrite:
        out_path = _unique_path(out_path)

    tmp_path = out_path + ".part"
    with open(tmp_path, "wb") as f:
        f.write(data)
    os.replace(tmp_path, out_path)

    return CryptoResult(
        out_path=out_path,
        original_name=original_name,
        in_bytes=os.path.getsize(in_path),
        out_bytes=len(data),
    )


def _unique_path(path: str) -> str:
    base, ext = os.path.splitext(path)
    i = 1
    while os.path.exists(f"{base} ({i}){ext}"):
        i += 1
    return f"{base} ({i}){ext}"
