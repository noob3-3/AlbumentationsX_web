"""拷到项目后把 import 改成目标包（例如 src.config.license）。"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from app.license import (
    HardwareInfo,
    activate,
    current_license,
    decode_machine_code,
    format_groups,
    generate_activation_code,
    main,
    machine_code,
    normalize_code,
    verify_activation_code,
    _SECRET,
)
from app.license_codec import encode_machine_code


def _hw(**overrides: str) -> HardwareInfo:
    data = dict(
        mac="AA:BB:CC:DD:EE:FF",
        disk="1A2B3C4D",
        guid="12345678-1234-1234-1234-1234567890ab",
        host="TEST-PC",
    )
    data.update(overrides)
    return HardwareInfo(**data)


def _machine() -> str:
    return machine_code(hardware=_hw())


def test_machine_code_stable_and_decodable():
    first = machine_code(hardware=_hw())
    second = machine_code(hardware=_hw())
    assert first == second
    assert first.startswith("M1")
    got = decode_machine_code(first, _SECRET)
    assert got is not None
    assert got.display_mac() == "AA:BB:CC:DD:EE:FF"
    assert got.display_disk() == "1A2B3C4D"
    assert got.host == "TEST-PC"
    other = machine_code(hardware=_hw(mac="11:22:33:44:55:66"))
    assert other != first


def test_decode_wrong_project_secret():
    code = encode_machine_code(_hw(), b"project-a")
    assert decode_machine_code(code, b"project-a") is not None
    assert decode_machine_code(code, b"project-b") is None


def test_generate_and_verify_roundtrip():
    machine = _machine()
    code = generate_activation_code(machine, date(2027, 1, 1))
    info = verify_activation_code(code, machine=machine, today=date(2026, 8, 31))
    assert info.valid
    assert info.expire_on == date(2027, 1, 1)
    assert "2027-01-01" in info.message


def test_accepts_spaces_and_lowercase():
    machine = _machine()
    code = generate_activation_code(machine, date(2027, 6, 1))
    messy = code.lower().replace("-", " ")
    info = verify_activation_code(messy, machine=machine.lower(), today=date(2026, 1, 1))
    assert info.valid


def test_reject_other_machine():
    code = generate_activation_code(_machine(), date(2027, 1, 1))
    other = machine_code(hardware=_hw(disk="FFFFFFFF"))
    info = verify_activation_code(code, machine=other, today=date(2026, 1, 1))
    assert not info.valid
    assert "不匹配" in info.message


def test_reject_expired():
    machine = _machine()
    code = generate_activation_code(machine, date(2026, 8, 1))
    info = verify_activation_code(code, machine=machine, today=date(2026, 8, 31))
    assert not info.valid
    assert "到期" in info.message
    assert info.expire_on == date(2026, 8, 1)


def test_permanent_license():
    machine = _machine()
    code = generate_activation_code(machine, None)
    info = verify_activation_code(code, machine=machine, today=date(2099, 1, 1))
    assert info.valid
    assert info.expire_on is None
    assert "永久" in info.message


def test_invalid_format():
    info = verify_activation_code("1234", machine=_machine())
    assert not info.valid
    assert "格式" in info.message


def test_generate_rejects_bad_machine():
    with pytest.raises(ValueError, match="机器码"):
        generate_activation_code("ABC", date(2027, 1, 1))


def test_activate_persists(tmp_path: Path):
    path = tmp_path / "license.dat"
    machine = _machine()
    code = generate_activation_code(machine, date(2027, 6, 1))
    info = activate(code, path=path, machine=machine, today=date(2026, 1, 1))
    assert info.valid
    loaded = current_license(path=path, machine=machine, today=date(2026, 8, 31))
    assert loaded.valid
    assert loaded.expire_on == date(2027, 6, 1)


def test_current_license_missing_file(tmp_path: Path):
    info = current_license(path=tmp_path / "missing.dat", machine=_machine())
    assert not info.valid
    assert info.message == "未激活"


def test_cli_generate(capsys):
    machine = _machine()
    rc = main(["generate", machine, "--expire", "2027-12-31"])
    assert rc == 0
    out = capsys.readouterr().out
    assert format_groups(machine) in out
    assert "2027-12-31" in out
    assert "激活码:" in out


def test_cli_generate_bad_machine():
    assert main(["generate", "xx", "--permanent"]) == 2


def test_legacy_hash_machine_cannot_decode():
    assert decode_machine_code("A547-FB16-BA8C-DF5A", _SECRET) is None
    assert len(normalize_code("A547-FB16-BA8C-DF5A")) == 16
