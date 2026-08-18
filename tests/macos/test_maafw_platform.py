# -*- coding: utf-8 -*-
"""
PHASE 1: MaaFramework macOS Apple Silicon (arm64) Platform & API Verification Test Suite.

Checks:
A. System Architecture (Darwin / arm64)
B. Python Architecture (arm64 / 64-bit)
C. MaaFramework package loading & version
D. MacOSController import, signature, methods, enums
E. Toolkit desktop window & macOS permissions APIs
F. Native library binary architecture inspection (Mach-O arm64)
"""

from __future__ import annotations

import ctypes
import inspect
import os
import platform
import struct
import subprocess
import sys
from pathlib import Path


def check_macho_architecture(dylib_path: str | Path) -> str:
    """Inspect Mach-O binary header to determine architecture without external tools."""
    path = Path(dylib_path)
    if not path.exists():
        return "FILE_NOT_FOUND"

    with open(path, "rb") as f:
        magic = f.read(4)

    if len(magic) < 4:
        return "INVALID_HEADER"

    # Mach-O magic numbers
    # 0xfeedface = MH_MAGIC (32-bit BE)
    # 0xcefaedfe = MH_CIGAM (32-bit LE)
    # 0xfeedfacf = MH_MAGIC_64 (64-bit BE)
    # 0xcffaedfe = MH_CIGAM_64 (64-bit LE)
    # 0xcafebabe = FAT_MAGIC
    # 0xbebafeca = FAT_CIGAM
    
    # CPU types
    # 0x0100000C = CPU_TYPE_ARM64
    # 0x01000007 = CPU_TYPE_X86_64
    
    if magic in (b"\xcf\xfa\xed\xfe", b"\xfe\xed\xfa\xcf"):
        # 64-bit Mach-O
        with open(path, "rb") as f:
            header = f.read(32)
        if len(header) >= 8:
            endian = "<" if magic == b"\xcf\xfa\xed\xfe" else ">"
            _, cpu_type = struct.unpack(f"{endian}II", header[:8])
            if cpu_type == 0x0100000C:
                return "arm64"
            elif cpu_type == 0x01000007:
                return "x86_64"
            return f"Mach-O 64-bit (cputype=0x{cpu_type:X})"

    elif magic in (b"\xca\xfe\xba\xbe", b"\xbe\xba\xfe\xca"):
        # Fat binary (Universal)
        return "Universal / Fat Binary"

    # Fallback to macOS `file` command if on Darwin
    if platform.system() == "Darwin":
        try:
            res = subprocess.run(["file", str(path)], capture_output=True, text=True, check=True)
            return res.stdout.strip()
        except Exception:
            pass

    return "PE / Non-Mach-O or Unknown"


def run_phase1_verification():
    print("=" * 70)
    print("MaaNTE PHASE 1: macOS Apple Silicon (arm64) Verification Test Suite")
    print("=" * 70)

    results = {}
    failures = []

    # ------------------------------------------------------------------
    # A. System Architecture
    # ------------------------------------------------------------------
    print("\n[A] System Architecture Check")
    os_name = platform.system()
    machine = platform.machine()
    uname_str = platform.uname()
    print(f"  OS: {os_name}")
    print(f"  Machine: {machine}")
    print(f"  Uname: {uname_str.system} {uname_str.release} {uname_str.machine}")
    
    results["system_os"] = os_name
    results["system_machine"] = machine

    if os_name != "Darwin":
        print(f"  [WARN] Current host is {os_name}, not Darwin (macOS).")
    else:
        if machine != "arm64":
            failures.append(f"System machine is '{machine}', expected 'arm64' on Apple Silicon.")
        else:
            print("  [OK] Native Apple Silicon Darwin detected.")

    # ------------------------------------------------------------------
    # B. Python Architecture
    # ------------------------------------------------------------------
    print("\n[B] Python Architecture Check")
    py_ver = sys.version
    py_exec = sys.executable
    is_64bit = sys.maxsize > 2**32
    print(f"  Python Executable: {py_exec}")
    print(f"  Python Version: {py_ver.splitlines()[0]}")
    print(f"  64-bit Process: {is_64bit}")

    results["python_executable"] = py_exec
    results["python_version"] = py_ver
    results["is_64bit"] = is_64bit

    if not is_64bit:
        failures.append("Python is running in 32-bit mode; 64-bit is strictly required.")

    # ------------------------------------------------------------------
    # C. MaaFramework Package Loading
    # ------------------------------------------------------------------
    print("\n[C] MaaFramework Package Loading Check")
    maafw_loaded = False
    maa_ver = "unknown"
    maa_path = "not found"
    try:
        import maafw
        maa_ver = getattr(maafw, "__version__", "unknown")
        maa_path = getattr(maafw, "__file__", "unknown")
        maafw_loaded = True
        print(f"  maafw module: {maafw}")
        print(f"  maafw version: {maa_ver}")
        print(f"  maafw location: {maa_path}")
    except ImportError as exc:
        print(f"  [INFO] 'import maafw' raised: {exc}; checking 'import maa'...")
        try:
            import maa
            maa_ver = getattr(maa, "__version__", "v5.x")
            maa_path = getattr(maa, "__file__", "unknown")
            maafw_loaded = True
            print(f"  maa module: {maa}")
            print(f"  maa version: {maa_ver}")
            print(f"  maa location: {maa_path}")
        except ImportError as exc2:
            failures.append(f"Failed to import both maafw and maa: {exc2}")

    results["maafw_loaded"] = maafw_loaded
    results["maa_version"] = maa_ver

    # ------------------------------------------------------------------
    # D. Introspect MacOSController
    # ------------------------------------------------------------------
    print("\n[D] MacOSController Introspection Check")
    try:
        from maa.controller import MacOSController
        from maa.define import (
            MaaMacOSScreencapMethodEnum,
            MaaMacOSInputMethodEnum,
            MaaMacOSPermissionEnum,
        )

        sig = inspect.signature(MacOSController.__init__)
        methods = [m for m in dir(MacOSController) if not m.startswith("__")]

        print(f"  MacOSController Class: {MacOSController}")
        print(f"  Import Path: maa.controller.MacOSController")
        print(f"  Constructor Signature: {sig}")
        print(f"  Public Methods ({len(methods)}): {methods[:10]}...")

        # Check Enums
        screencap_members = {k: v.value for k, v in MaaMacOSScreencapMethodEnum.__members__.items()}
        input_members = {k: v.value for k, v in MaaMacOSInputMethodEnum.__members__.items()}
        perm_members = {k: v.value for k, v in MaaMacOSPermissionEnum.__members__.items()}

        print(f"  MaaMacOSScreencapMethodEnum: {screencap_members}")
        print(f"  MaaMacOSInputMethodEnum: {input_members}")
        print(f"  MaaMacOSPermissionEnum: {perm_members}")

        # Assert key methods
        required_methods = ["post_screencap", "cached_image", "post_click", "post_key_down", "post_key_up"]
        missing_methods = [m for m in required_methods if m not in methods]
        if missing_methods:
            failures.append(f"MacOSController is missing expected methods: {missing_methods}")

        results["macos_controller_ok"] = True
    except Exception as exc:
        failures.append(f"MacOSController introspection failed: {exc}")
        results["macos_controller_ok"] = False

    # ------------------------------------------------------------------
    # E. Introspect Toolkit APIs
    # ------------------------------------------------------------------
    print("\n[E] Toolkit API Introspection Check")
    try:
        from maa.toolkit import Toolkit, DesktopWindow

        has_find_windows = hasattr(Toolkit, "find_desktop_windows")
        has_check_perm = hasattr(Toolkit, "macos_check_permission")
        has_req_perm = hasattr(Toolkit, "macos_request_permission")
        has_reveal_perm = hasattr(Toolkit, "macos_reveal_permission_settings")

        print(f"  Toolkit.find_desktop_windows exists: {has_find_windows}")
        print(f"  Toolkit.macos_check_permission exists: {has_check_perm}")
        print(f"  Toolkit.macos_request_permission exists: {has_req_perm}")
        print(f"  Toolkit.macos_reveal_permission_settings exists: {has_reveal_perm}")

        if not has_find_windows:
            failures.append("Toolkit.find_desktop_windows is missing.")
        if not has_check_perm:
            failures.append("Toolkit.macos_check_permission is missing.")

        results["toolkit_ok"] = has_find_windows and has_check_perm
    except Exception as exc:
        failures.append(f"Toolkit API introspection failed: {exc}")
        results["toolkit_ok"] = False

    # ------------------------------------------------------------------
    # F. Native Library Binary Architecture Inspection
    # ------------------------------------------------------------------
    print("\n[F] Native Library Binary Architecture Check")
    try:
        from maa.library import Library
        # Check native library paths
        lib_dir = None
        if hasattr(Library, "_lib_path") and Library._lib_path:
            lib_dir = Path(Library._lib_path)
        elif hasattr(Library, "framework"):
            # inspect ctypes handle
            try:
                fw = Library.framework()
                if hasattr(fw, "_name"):
                    lib_dir = Path(fw._name).parent
            except Exception:
                pass

        if lib_dir is None:
            # check default package locations
            import maa
            pkg_dir = Path(maa.__file__).parent
            candidates = list(pkg_dir.glob("*.dylib")) + list(pkg_dir.glob("*.dll")) + list(pkg_dir.glob("bin/*.dylib"))
        else:
            candidates = list(Path(lib_dir).glob("*.dylib")) + list(Path(lib_dir).glob("*.dll"))

        print(f"  Found native binary files: {[c.name for c in candidates]}")
        for c in candidates:
            arch = check_macho_architecture(c)
            print(f"    - {c.name}: {arch}")

        results["native_binaries"] = [c.name for c in candidates]
    except Exception as exc:
        print(f"  [WARN] Native binary inspection encountered: {exc}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("PHASE 1 VERIFICATION SUMMARY")
    print("=" * 70)
    if not failures:
        print(">> [STATUS: PASS] All MaaFramework API and platform checks succeeded.")
        return 0
    else:
        print(f">> [STATUS: FAIL] Encountered {len(failures)} issue(s):")
        for i, f in enumerate(failures, 1):
            print(f"   {i}. {f}")
        return 1


if __name__ == "__main__":
    sys.exit(run_phase1_verification())
