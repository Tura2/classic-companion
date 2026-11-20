"""Companion runs below normal priority, so the game always comes first (2026-11-20: it ran at Normal,
the same as the game, using ~19% of a core)."""
import companion


def test_below_normal_is_asked_for():
    asked = []
    assert companion.lower_priority(setter=asked.append) is True
    assert asked == [0x4000]


def test_a_failure_is_not_fatal():
    def fail(cls):
        raise OSError("access denied")
    assert companion.lower_priority(setter=fail) is False


def _windows_priority(set_to=None):
    """This test process's priority class (and set it first, if asked), with proper handle types."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.GetPriorityClass.argtypes = [wintypes.HANDLE]
    k32.GetPriorityClass.restype = wintypes.DWORD
    if set_to is not None:
        k32.SetPriorityClass(k32.GetCurrentProcess(), set_to)
    return k32.GetPriorityClass(k32.GetCurrentProcess())


def test_it_really_lowers_the_priority_on_windows():
    import sys
    import pytest
    if sys.platform != "win32":
        pytest.skip("Windows only")
    try:
        assert _windows_priority(set_to=0x20) == 0x20          # NORMAL first (conftest set below normal)
        assert companion.lower_priority() is True
        assert _windows_priority() == 0x4000
    finally:
        _windows_priority(set_to=0x4000)                        # the suite stays below normal
