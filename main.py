#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MAIN — Entry point PEITER STORE
Dual Engine + Telegram Bot
Powered by @PeiterStore
"""

import sys
import signal
import os

print("=" * 64)
print("  PEITER STORE — DUAL ENGINE BOT")
print("  Powered by @PeiterStore")
print("=" * 64)

# ══════════════════════════════════════════════════════════════════
#  IMPORT ENGINE
# ══════════════════════════════════════════════════════════════════
try:
    import app as _engine
    print("[BOOT] ✅ Engine app.py loaded")
except Exception as e:
    print(f"[FATAL] ❌ Gagal import app.py: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════
#  IMPORT DUAL MENU
# ══════════════════════════════════════════════════════════════════
USE_DUAL = False
try:
    import peiter_dual_menu as _dual
    print("[BOOT] ✅ Dual engine loaded")
    USE_DUAL = True
except Exception as e:
    print(f"[BOOT] ⚠️ Dual engine OFF: {e}")

# ══════════════════════════════════════════════════════════════════
#  PATCH HANDLERS
# ══════════════════════════════════════════════════════════════════
if USE_DUAL:
    _engine.handle_callback = _dual.wrapped_handle_callback
    _engine.start_menu = _dual.start_menu
    _engine.start_kb = _dual.start_kb
    print("[BOOT] ✅ Callback patched → DUAL MENU")
    print("[BOOT] ✅ Start menu patched → DUAL ENGINE")

# ══════════════════════════════════════════════════════════════════
#  SIGNAL HANDLER
# ══════════════════════════════════════════════════════════════════
def _stop_handler(signum, frame):
    print(f"\n[STOP] Signal {signum} received")
    try:
        _engine._BOT_STOP.set()
    except:
        pass

try:
    signal.signal(signal.SIGTERM, _stop_handler)
    signal.signal(signal.SIGINT, _stop_handler)
    print("[BOOT] ✅ Signal handler registered")
except Exception as e:
    print(f"[BOOT] ⚠️ Signal error: {e}")

# ══════════════════════════════════════════════════════════════════
#  LOAD STATE
# ══════════════════════════════════════════════════════════════════
try:
    _engine.load_state()
    print("[BOOT] ✅ State loaded")
except Exception as e:
    print(f"[BOOT] ⚠️ State load error: {e}")

# ══════════════════════════════════════════════════════════════════
#  START BOT
# ══════════════════════════════════════════════════════════════════
print("[BOOT] 🚀 Starting Telegram bot...")
print("=" * 64)
print()

try:
    _engine.bot_poll()
except KeyboardInterrupt:
    print("\n[STOP] Keyboard interrupt")
    try:
        _engine._BOT_STOP.set()
    except:
        pass
except Exception as e:
    print(f"\n[FATAL] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[BOT] Stopped.")
