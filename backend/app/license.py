"""本机机器码与离线激活码。"""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from app.license_codec import (
    HardwareInfo,
    SIG_LEN,
    decode_machine_code,
    encode_machine_code,
    format_groups,
    generate_activation_code as _generate_activation,
    normalize_code,
    parse_expire_token,
    sign_machine,
)

# 每个产品独立密钥；必须与签发台逐字节一致
_SECRET = b"ALBX-VST-LIC-2026-9F4K2M7Q"
_LICENSE_NAME = "license.dat"

DEFAULT_PROJECT_NAME = "AlbumentationsX 训练平台"
DEFAULT_PROJECT_SECRET = _SECRET.decode("ascii")


@dataclass(frozen=True)
class LicenseInfo:
    valid: bool
    machine_code: str
    expire_on: date | None
    message: str
    activation_code: str = ""


def license_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / _LICENSE_NAME
    return Path(__file__).resolve().parents[2] / _LICENSE_NAME


def collect_hardware() -> HardwareInfo:
    return HardwareInfo(
        mac=_mac_address(),
        disk=_volume_serial(),
        guid=_machine_guid(),
        host=os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "",
    )


def machine_code(*, hardware: HardwareInfo | None = None, secret: bytes | None = None) -> str:
    info = hardware if hardware is not None else collect_hardware()
    return encode_machine_code(info, secret or _SECRET)


def generate_activation_code(
    machine: str,
    expire: date | None,
    *,
    secret: bytes | None = None,
) -> str:
    return _generate_activation(machine, expire, secret or _SECRET)


def verify_activation_code(
    code: str,
    *,
    machine: str | None = None,
    today: date | None = None,
    secret: bytes | None = None,
) -> LicenseInfo:
    key = secret or _SECRET
    machine_fmt = machine_code() if machine is None else format_groups(machine)
    machine_n = normalize_code(machine_fmt)
    today = today or date.today()
    compact = normalize_code(code)
    if len(compact) != 8 + SIG_LEN:
        return LicenseInfo(False, machine_fmt, None, "激活码格式不正确")
    expire_s, sig = compact[:8], compact[8:]
    try:
        expire_on = parse_expire_token(expire_s)
    except ValueError:
        return LicenseInfo(False, machine_fmt, None, "激活码格式不正确")
    expected = sign_machine(machine_n, expire_s, key)
    if not hmac.compare_digest(expected, sig):
        return LicenseInfo(False, machine_fmt, None, "激活码与本机机器码不匹配，或激活码无效")
    if expire_on is not None and today > expire_on:
        return LicenseInfo(
            False,
            machine_fmt,
            expire_on,
            f"激活已于 {expire_on.isoformat()} 到期",
            format_groups(compact),
        )
    if expire_on is None:
        message = "已永久激活"
    else:
        message = f"已激活，有效期至 {expire_on.isoformat()}"
    return LicenseInfo(True, machine_fmt, expire_on, message, format_groups(compact))


def current_license(
    *,
    path: Path | None = None,
    machine: str | None = None,
    today: date | None = None,
) -> LicenseInfo:
    machine_fmt = machine_code() if machine is None else format_groups(machine)
    stored = _load_license(path or license_path())
    if not stored:
        return LicenseInfo(False, machine_fmt, None, "未激活")
    return verify_activation_code(stored, machine=machine_fmt, today=today)


def activate(
    code: str,
    *,
    path: Path | None = None,
    machine: str | None = None,
    today: date | None = None,
) -> LicenseInfo:
    info = verify_activation_code(code, machine=machine, today=today)
    if not info.valid:
        return info
    _save_license(info.activation_code, path or license_path())
    return info


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="本机机器码 / 签发激活码")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("machine", help="打印本机机器码")
    sub.add_parser("hardware", help="打印本机 MAC / 硬盘等信息")

    gen = sub.add_parser("generate", help="根据机器码签发激活码")
    gen.add_argument("machine", help="客户机器码")
    exclusive = gen.add_mutually_exclusive_group(required=True)
    exclusive.add_argument("--expire", help="到期日 YYYY-MM-DD")
    exclusive.add_argument("--days", type=int, help="自今日起有效天数")
    exclusive.add_argument("--permanent", action="store_true", help="永久有效")

    check = sub.add_parser("check", help="校验激活码")
    check.add_argument("code", help="激活码")
    check.add_argument("--machine", help="机器码，默认本机")

    args = parser.parse_args(argv)
    if args.cmd == "machine":
        print(machine_code())
        return 0
    if args.cmd == "hardware":
        hw = collect_hardware()
        print(f"MAC: {hw.display_mac() or '—'}")
        print(f"硬盘: {hw.display_disk() or '—'}")
        print(f"GUID: {hw.display_guid() or '—'}")
        print(f"主机: {hw.host or '—'}")
        return 0
    if args.cmd == "generate":
        try:
            expire = _expire_from_args(args)
            code = generate_activation_code(args.machine, expire)
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        print(f"机器码: {format_groups(args.machine)}")
        print(f"到期日: {expire.isoformat() if expire else '永久'}")
        print(f"激活码: {code}")
        return 0
    info = verify_activation_code(args.code, machine=args.machine)
    print(info.message)
    return 0 if info.valid else 1


def _expire_from_args(args: argparse.Namespace) -> date | None:
    if args.permanent:
        return None
    if args.days is not None:
        if args.days <= 0:
            raise ValueError("有效天数必须为正整数")
        return date.today() + timedelta(days=args.days)
    try:
        return date.fromisoformat(args.expire)
    except ValueError as exc:
        raise ValueError("到期日格式应为 YYYY-MM-DD") from exc


def _machine_guid() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import winreg

        access = winreg.KEY_READ
        if sys.maxsize <= 2**32:
            access |= getattr(winreg, "KEY_WOW64_64KEY", 0)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            access,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return str(value)
    except OSError:
        return ""


def _volume_serial() -> str:
    if sys.platform != "win32":
        return ""
    try:
        import ctypes

        serial = ctypes.c_uint()
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            "C:\\", None, 0, ctypes.byref(serial), None, None, None, 0
        )
        if not ok:
            return ""
        return f"{serial.value:08X}"
    except OSError:
        return ""


def _mac_address() -> str:
    for mac in _windows_macs():
        return mac
    return _uuid_mac()


def _uuid_mac() -> str:
    node = uuid.getnode()
    return ":".join(f"{(node >> 8 * i) & 0xFF:02X}" for i in range(5, -1, -1))


def _windows_macs() -> list[str]:
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import POINTER, Structure, byref, c_char, c_uint, c_ulong, sizeof, windll

        class IP_ADDR_STRING(Structure):
            pass

        IP_ADDR_STRING._fields_ = [
            ("Next", POINTER(IP_ADDR_STRING)),
            ("IpAddress", c_char * 16),
            ("IpMask", c_char * 16),
            ("Context", c_ulong),
        ]

        class IP_ADAPTER_INFO(Structure):
            pass

        IP_ADAPTER_INFO._fields_ = [
            ("Next", POINTER(IP_ADAPTER_INFO)),
            ("ComboIndex", c_ulong),
            ("AdapterName", c_char * 260),
            ("Description", c_char * 132),
            ("AddressLength", c_uint),
            ("Address", ctypes.c_ubyte * 8),
            ("Index", c_ulong),
            ("Type", c_uint),
            ("DhcpEnabled", c_uint),
            ("CurrentIpAddress", POINTER(IP_ADDR_STRING)),
            ("IpAddressList", IP_ADDR_STRING),
            ("GatewayList", IP_ADDR_STRING),
            ("DhcpServer", IP_ADDR_STRING),
            ("HaveWins", c_uint),
            ("PrimaryWinsServer", IP_ADDR_STRING),
            ("SecondaryWinsServer", IP_ADDR_STRING),
            ("LeaseObtained", c_ulong),
            ("LeaseExpires", c_ulong),
        ]

        get_info = windll.iphlpapi.GetAdaptersInfo
        buflen = c_ulong(sizeof(IP_ADAPTER_INFO) * 16)
        buf = ctypes.create_string_buffer(buflen.value)
        ret = get_info(buf, byref(buflen))
        if ret == 111:
            buf = ctypes.create_string_buffer(buflen.value)
            ret = get_info(buf, byref(buflen))
        if ret != 0:
            return []
        adapter = ctypes.cast(buf, POINTER(IP_ADAPTER_INFO)).contents
        skip = ("virtual", "vmware", "hyper-v", "loopback", "vpn", "tap", "pseudo", "bluetooth")
        macs: list[str] = []
        while True:
            desc = adapter.Description.decode("mbcs", errors="ignore").lower()
            if adapter.Type in (6, 71) and adapter.AddressLength >= 6:
                if not any(word in desc for word in skip):
                    mac = ":".join(f"{adapter.Address[i]:02X}" for i in range(6))
                    if mac != "00:00:00:00:00:00" and mac not in macs:
                        macs.append(mac)
            if not adapter.Next:
                break
            adapter = adapter.Next.contents
        return macs
    except (OSError, ValueError, AttributeError):
        return []


def _load_license(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("activation_code") or "").strip()


def _save_license(code: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"activation_code": code}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


__all__ = [
    "DEFAULT_PROJECT_NAME",
    "DEFAULT_PROJECT_SECRET",
    "HardwareInfo",
    "LicenseInfo",
    "activate",
    "collect_hardware",
    "current_license",
    "decode_machine_code",
    "format_groups",
    "generate_activation_code",
    "machine_code",
    "main",
    "normalize_code",
]


if __name__ == "__main__":
    raise SystemExit(main())
