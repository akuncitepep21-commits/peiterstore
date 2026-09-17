#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OUTPUT NAMER — Nama file rapih & berurut
Format: {prefix}-{count}-{urut:03d}.{ext}
Contoh: valid-50-001.txt
"""

import os, re, time, threading
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ_WIB = timezone(timedelta(hours=7))
_LOCK = threading.Lock()

# Cache nomor urut per prefix (biar cepet)
_NUM_CACHE = {}
_CACHE_LOCK = threading.Lock()


def _scan_max_number(dir_path, prefix, ext_clean):
    """Scan folder buat cari nomor urut tertinggi."""
    max_n = 0
    try:
        pat = re.compile(rf"^{re.escape(prefix)}-(\d+)\.{re.escape(ext_clean)}$", re.I)
        for f in dir_path.iterdir():
            if not f.is_file():
                continue
            m = pat.match(f.name)
            if m:
                try:
                    n = int(m.group(1))
                    if n > max_n:
                        max_n = n
                except Exception:
                    pass
    except Exception:
        pass
    return max_n


def next_number(dir_path, prefix, ext=".txt"):
    """
    Cari nomor urut berikutnya.
    Contoh: valid-50-001.txt → next = 002
    """
    dir_path = Path(dir_path)
    dir_path.mkdir(parents=True, exist_ok=True)
    ext_clean = ext.lstrip(".")

    cache_key = f"{dir_path}:{prefix}:{ext_clean}"

    with _CACHE_LOCK:
        cached = _NUM_CACHE.get(cache_key)
        if cached is not None:
            # Cek apakah file terakhir masih ada
            last_file = dir_path / f"{prefix}-{cached-1:03d}.{ext_clean}"
            if cached == 1 or last_file.exists():
                _NUM_CACHE[cache_key] = cached + 1
                return cached

    # Scan folder
    max_n = _scan_max_number(dir_path, prefix, ext_clean)
    next_n = max_n + 1

    with _CACHE_LOCK:
        _NUM_CACHE[cache_key] = next_n + 1

    return next_n


def make_filename(dir_path, prefix, count, ext=".txt"):
    """Bikin nama file: {prefix}-{count}-{urut:03d}.{ext}"""
    with _LOCK:
        n = next_number(dir_path, prefix, ext)
    return Path(dir_path) / f"{prefix}-{count}-{n:03d}{ext}"


def write_with_header(path, lines, header_lines=None):
    """Tulis file dengan header timestamp."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(TZ_WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
    with open(path, "w", encoding="utf-8") as f:
        if header_lines:
            for h in header_lines:
                f.write(f"# {h}\n")
            f.write(f"# Generated: {ts}\n")
            f.write(f"# Total: {len(lines)}\n")
            f.write("#" + "=" * 60 + "\n\n")
        for line in lines:
            f.write(str(line).rstrip() + "\n")
    return path


def append_with_lock(path, line):
    """Append 1 baris, thread-safe."""
    with _LOCK:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(str(line).rstrip() + "\n")
            f.flush()


def clear_cache(dir_path=None, prefix=None):
    """Clear cache nomor urut."""
    with _CACHE_LOCK:
        if dir_path is None and prefix is None:
            _NUM_CACHE.clear()
        else:
            keys_to_remove = [
                k for k in _NUM_CACHE
                if (dir_path is None or str(dir_path) in k)
                and (prefix is None or prefix in k)
            ]
            for k in keys_to_remove:
                _NUM_CACHE.pop(k, None)


def list_files(dir_path, prefix=None):
    """List file di folder (sorted by name)."""
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return []
    files = sorted(dir_path.iterdir(), key=lambda f: f.name)
    if prefix:
        files = [f for f in files if f.name.startswith(prefix)]
    return [f for f in files if f.is_file()]


def latest_file(dir_path, prefix=None):
    """Ambil file terbaru (by mtime)."""
    files = list_files(dir_path, prefix)
    if not files:
        return None
    return max(files, key=lambda f: f.stat().st_mtime)


def total_size_mb(dir_path):
    """Total size folder dalam MB."""
    dir_path = Path(dir_path)
    if not dir_path.exists():
        return 0
    total = 0
    for f in dir_path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except Exception:
                pass
    return total / (1024 * 1024)


def safe_filename(name, max_len=100):
    """Bikin nama file aman (buang karakter aneh)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name))
    name = name.strip(". ")
    if len(name) > max_len:
        name = name[:max_len]
    if not name:
        name = f"file_{int(time.time())}"
    return name


# ══════════════════════════════════════════════════════════════════
#  TEST
# ══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "output_test"
    tmp.mkdir(exist_ok=True)

    # Clean
    for f in tmp.glob("*"):
        f.unlink()

    print("=" * 60)
    print("  OUTPUT NAMER — TEST")
    print("=" * 60)

    print("\n[1] Bikin 3 file valid-50:")
    for i in range(3):
        p = make_filename(tmp, "valid", 50, ".txt")
        write_with_header(p, [f"line {j}" for j in range(5)],
                          header_lines=["PEITER STORE TEST"])
        print(f"    {p.name}")

    print("\n[2] Bikin 2 file detail-20:")
    for i in range(2):
        p = make_filename(tmp, "detail", 20, ".txt")
        write_with_header(p, [f"data {j}" for j in range(3)])
        print(f"    {p.name}")

    print("\n[3] List files:")
    for f in list_files(tmp):
        print(f"    {f.name}")

    print("\n[4] Latest file:")
    latest = latest_file(tmp, "valid")
    print(f"    {latest.name if latest else 'None'}")

    print("\n[5] Total size:")
    print(f"    {total_size_mb(tmp):.3f} MB")

    print("\n[6] Safe filename:")
    print(f"    {safe_filename('test/file:name?.txt')}")

    # Cleanup
    for f in tmp.glob("*"):
        f.unlink()
    tmp.rmdir()

    print("\n" + "=" * 60)
    print("  TEST SELESAI")
    print("=" * 60)