#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CONFIG — Load environment variables dari .env atau os.environ
"""

import os
from pathlib import Path

# ══════════════════════════════════════════════════════════════════
#  LOAD .env FILE
# ══════════════════════════════════════════════════════════════════
def load_dotenv(path=".env"):
    """Load .env file ke os.environ."""
    env_path = Path(path)
    if not env_path.exists():
        return False
    
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                
                # Skip komentar & baris kosong
                if not line or line.startswith("#"):
                    continue
                
                # Skip kalo gak ada "="
                if "=" not in line:
                    continue
                
                # Parse key=value
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                
                # Hapus quote
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Set ke os.environ (jangan override yang udah ada)
                if key and key not in os.environ:
                    os.environ[key] = value
        
        return True
    except Exception as e:
        print(f"[CONFIG] Gagal load .env: {e}")
        return False


# Load otomatis pas import
load_dotenv()


# ══════════════════════════════════════════════════════════════════
#  CONFIG VALUES
# ══════════════════════════════════════════════════════════════════
def get(key, default=""):
    """Ambil env variable."""
    return os.environ.get(key, default).strip()


def get_int(key, default=0):
    """Ambil env variable sebagai int."""
    try:
        return int(os.environ.get(key, default))
    except (ValueError, TypeError):
        return default


def get_bool(key, default=False):
    """Ambil env variable sebagai bool."""
    val = os.environ.get(key, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


# ══════════════════════════════════════════════════════════════════
#  EXPORT CONFIG
# ══════════════════════════════════════════════════════════════════
BOT_TOKEN        = get("TG_BOT_TOKEN")
CHAT_ID          = get("TG_CHAT_ID")
OWNER_CHAT_ID    = get("TG_OWNER_CHAT_ID", CHAT_ID)
PERFORMANCE_MODE = get("PEITER_MODE", "balanced")
OUTPUT_DIR       = get("PEITER_OUTPUT_DIR", "")
ADB_PATH         = get("ADB_PATH", "adb")
ADB_DEVICE       = get("ADB_DEVICE", "")
DEBUG            = get_bool("PEITER_DEBUG", False)


# ══════════════════════════════════════════════════════════════════
#  VALIDASI
# ══════════════════════════════════════════════════════════════════
def validate():
    """Validasi config wajib."""
    errors = []
    if not BOT_TOKEN:
        errors.append("TG_BOT_TOKEN kosong")
    if not OWNER_CHAT_ID:
        errors.append("TG_OWNER_CHAT_ID kosong")
    return errors


def print_config():
    """Print config (hide token)."""
    print("=" * 60)
    print("  CONFIG")
    print("=" * 60)
    print(f"  Bot Token  : {BOT_TOKEN[:25]}..." if BOT_TOKEN else "  Bot Token  : (kosong)")
    print(f"  Owner ID   : {OWNER_CHAT_ID}")
    print(f"  Chat ID    : {CHAT_ID}")
    print(f"  Mode       : {PERFORMANCE_MODE}")
    print(f"  Output Dir : {OUTPUT_DIR or '(default)'}")
    print(f"  ADB Path   : {ADB_PATH}")
    print(f"  ADB Device : {ADB_DEVICE or '(auto)'}")
    print(f"  Debug      : {DEBUG}")
    print("=" * 60)


if __name__ == "__main__":
    print_config()
    errs = validate()
    if errs:
        print("\n❌ Error:")
        for e in errs:
            print(f"  - {e}")
    else:
        print("\n✅ Config valid")