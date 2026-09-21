"""机器码编解码与激活码签发（客户端 / 签发台共用算法）。

机器码用项目密钥对 MAC、硬盘序列号、主板 GUID、主机名做可逆封装。
换项目密钥无法反解，签发的激活码也不能互通。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from dataclasses import dataclass
from datetime import date

SIG_LEN = 12
MIN_MACHINE_LEN = 16
_HOST_LEN = 16
_VERSION = 1


@dataclass(frozen=True)
class HardwareInfo:
    mac: str = ""
    disk: str = ""
    guid: str = ""
    host: str = ""

    def display_mac(self) -> str:
        return self.mac if self.mac and self.mac != "00:00:00:00:00:00" else ""

    def display_disk(self) -> str:
        return self.disk if self.disk and self.disk != "00000000" else ""

    def display_guid(self) -> str:
        blank = "00000000-0000-0000-0000-000000000000"
        return self.guid if self.guid and self.guid != blank else ""


def as_secret(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        return value
    return value.encode("utf-8")


def normalize_code(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def format_groups(text: str, size: int = 4) -> str:
    body = normalize_code(text)
    if not body:
        return ""
    return "-".join(body[i : i + size] for i in range(0, len(body), size))


def encode_machine_code(info: HardwareInfo, secret: str | bytes) -> str:
    raw = _pack(info)
    digest = hmac.new(as_secret(secret), raw, hashlib.sha256).digest()[:4]
    token = "M1" + _b32encode(_xor(raw + digest, secret))
    return format_groups(token)


def decode_machine_code(code: str, secret: str | bytes) -> HardwareInfo | None:
    compact = normalize_code(code)
    if not compact.startswith("M1") or len(compact) <= 4:
        return None
    try:
        cipher = _b32decode(compact[2:])
    except ValueError:
        return None
    plain = _xor(cipher, secret)
    if len(plain) < 5:
        return None
    raw, digest = plain[:-4], plain[-4:]
    expected = hmac.new(as_secret(secret), raw, hashlib.sha256).digest()[:4]
    if not hmac.compare_digest(digest, expected):
        return None
    return _unpack(raw)


def generate_activation_code(
    machine: str,
    expire: date | None,
    secret: str | bytes,
) -> str:
    machine_n = normalize_code(machine)
    if len(machine_n) < MIN_MACHINE_LEN:
        raise ValueError("机器码格式不正确")
    expire_s = expire.strftime("%Y%m%d") if expire else "00000000"
    return format_groups(expire_s + sign_machine(machine_n, expire_s, secret))


def sign_machine(machine_n: str, expire_s: str, secret: str | bytes) -> str:
    msg = f"{machine_n}|{expire_s}".encode("utf-8")
    return hmac.new(as_secret(secret), msg, hashlib.sha256).hexdigest()[:SIG_LEN].upper()


def parse_expire_token(expire_s: str) -> date | None:
    if expire_s == "00000000":
        return None
    return date(int(expire_s[:4]), int(expire_s[4:6]), int(expire_s[6:8]))


def _pack(info: HardwareInfo) -> bytes:
    host = (info.host or "").encode("utf-8")[:_HOST_LEN].ljust(_HOST_LEN, b"\x00")
    return bytes([_VERSION]) + _mac_bytes(info.mac) + _disk_bytes(info.disk) + _guid_bytes(info.guid) + host


def _unpack(raw: bytes) -> HardwareInfo | None:
    need = 1 + 6 + 4 + 16 + _HOST_LEN
    if len(raw) < need or raw[0] != _VERSION:
        return None
    mac_b = raw[1:7]
    disk_b = raw[7:11]
    guid_b = raw[11:27]
    host_b = raw[27:27 + _HOST_LEN]
    mac = ":".join(f"{b:02X}" for b in mac_b)
    disk = disk_b.hex().upper()
    try:
        guid = str(uuid.UUID(bytes=guid_b))
    except ValueError:
        guid = guid_b.hex()
    host = host_b.split(b"\x00", 1)[0].decode("utf-8", errors="replace")
    return HardwareInfo(mac=mac, disk=disk, guid=guid, host=host)


def _mac_bytes(mac: str) -> bytes:
    hexed = "".join(ch for ch in (mac or "") if ch.isalnum())
    if len(hexed) != 12:
        return b"\x00" * 6
    try:
        return bytes.fromhex(hexed)
    except ValueError:
        return b"\x00" * 6


def _disk_bytes(disk: str) -> bytes:
    hexed = "".join(ch for ch in (disk or "") if ch.isalnum())
    if not hexed:
        return b"\x00" * 4
    if len(hexed) <= 8:
        try:
            return int(hexed, 16).to_bytes(4, "big")
        except ValueError:
            pass
    return hashlib.sha256((disk or "").encode("utf-8")).digest()[:4]


def _guid_bytes(guid: str) -> bytes:
    text = (guid or "").strip()
    if not text:
        return b"\x00" * 16
    try:
        return uuid.UUID(text).bytes
    except ValueError:
        return hashlib.sha256(text.encode("utf-8")).digest()[:16]


def _xor(data: bytes, secret: str | bytes) -> bytes:
    key = as_secret(secret)
    out = bytearray(len(data))
    counter = 0
    offset = 0
    while offset < len(data):
        block = hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        take = min(len(block), len(data) - offset)
        for i in range(take):
            out[offset + i] = data[offset + i] ^ block[i]
        offset += take
        counter += 1
    return bytes(out)


def _b32encode(data: bytes) -> str:
    return base64.b32encode(data).decode("ascii").rstrip("=")


def _b32decode(text: str) -> bytes:
    pad = "=" * ((8 - len(text) % 8) % 8)
    return base64.b32decode(text + pad)
