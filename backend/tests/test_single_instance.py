"""Only one Keptwise window per data folder (desktop/single_instance.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "desktop"))

import single_instance  # noqa: E402

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="the lock is a Windows mutex")


def test_lock_name_ignores_case_and_differs_by_folder(tmp_path):
    a = single_instance.lock_name(tmp_path / "One")
    assert a == single_instance.lock_name(Path(str(tmp_path / "One").upper())) or sys.platform != "win32"
    assert a != single_instance.lock_name(tmp_path / "Two")
    assert a.startswith("Local\\Keptwise-")


@windows_only
def test_a_second_copy_for_the_same_folder_is_refused_until_the_first_lets_go(tmp_path):
    try:
        assert single_instance.claim(tmp_path / "data") is True
        assert single_instance.claim(tmp_path / "data") is False
        assert single_instance.claim(tmp_path / "other") is True  # a different folder may run alongside
    finally:
        single_instance.release()
    assert single_instance.claim(tmp_path / "data") is True
    single_instance.release()


@windows_only
def test_show_existing_gives_up_quietly_when_no_window_is_open():
    assert single_instance.show_existing("Keptwise test window that does not exist", wait_s=0) is False
