#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DONATE — Sistem donasi via QRIS + Auto-License + Mode Setting + Tombol Approval
Merchant: PeiterStore | NMID: ID1025417261910
"""

import time, json, threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from io import BytesIO

TZ_WIB = timezone(timedelta(hours=7))


# ══════════════════════════════════════════════════════════════════
#  REWARD TIERS — Donasi → License (MAX ADMIN)
# ══════════════════════════════════════════════════════════════════
REWARD_TIERS = [
    (150_000, "admin", None, "🔧 Admin PERMANEN"),
    (100_000, "admin", 90,   "🔧 Admin 3 Bulan"),
    (50_000,  "admin", 30,   "🔧 Admin 30 Hari"),
    (30_000,  "admin", 7,    "🔧 Admin 7 Hari"),
    (20_000,  "user",  7,    "👤 User 7 Hari"),
    (10_000,  "user",  3,    "👤 User 3 Hari"),
    (5_000,   "user",  1,    "👤 User 1 Hari"),
]

HYBRID_THRESHOLD = 50000


def get_reward(amount):
    for min_amt, role, days, label in REWARD_TIERS:
        if amount >= min_amt:
            return {
                "role": role,
                "days": days,
                "hours": None if days is None else days * 24,
                "label": label,
            }
    return None


# ══════════════════════════════════════════════════════════════════
#  QRIS CONFIG
# ══════════════════════════════════════════════════════════════════
class QRISConfig:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        default = {
            "qris_static": "",
            "merchant_name": "PeiterStore",
            "nmid": "ID1025417261910",
            "owner_name": "Owner",
            "bank_name": "BCA",
            "bank_account": "-",
            "bank_holder": "-",
            "ewallet_name": "DANA",
            "ewallet_number": "-",
            "ewallet_holder": "-",
            "min_donate": 1000,
            "presets": [5000, 10000, 20000, 50000, 100000, 150000],
            "thank_you_msg": "Terima kasih atas donasinya! 🙏",
            "auto_license": True,
            "donate_mode": "auto",
        }
        if not self.path.exists():
            return default
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except:
            return default

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except: pass

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def set(self, key, value):
        with self.lock:
            self.data[key] = value
            self.save()

    def update(self, **kwargs):
        with self.lock:
            for k, v in kwargs.items():
                self.data[k] = v
            self.save()


# ══════════════════════════════════════════════════════════════════
#  CRC16 & QRIS PARSER
# ══════════════════════════════════════════════════════════════════
def crc16(data: str) -> str:
    crc = 0xFFFF
    for char in data:
        crc ^= ord(char) << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return format(crc, '04X')


def parse_qris(qris_string: str) -> dict:
    result = {}
    i = 0
    while i < len(qris_string):
        if i + 2 > len(qris_string): break
        tag = qris_string[i:i+2]
        i += 2
        if i + 2 > len(qris_string): break
        try:
            length = int(qris_string[i:i+2])
        except:
            break
        i += 2
        value = qris_string[i:i+length]
        i += length
        result[tag] = value
    return result


def build_qris(tags: dict) -> str:
    result = ""
    for tag in sorted(tags.keys(), key=lambda x: int(x)):
        if tag == "63": continue
        value = str(tags[tag])
        result += f"{tag}{len(value):02d}{value}"
    result += "6304"
    result += crc16(result)
    return result


def make_dynamic_qris(static_qris: str, amount: int) -> str:
    if not static_qris:
        return ""
    tags = parse_qris(static_qris)
    tags["54"] = str(amount)
    tags["01"] = "12"
    return build_qris(tags)


def validate_qris(qris_string: str) -> tuple:
    if not qris_string:
        return False, "QRIS kosong"
    if not qris_string.startswith("000201"):
        return False, "QRIS tidak valid"
    tags = parse_qris(qris_string)
    if "63" not in tags:
        return False, "QRIS tidak punya CRC"
    test = qris_string[:-4] + "6304"
    expected_crc = crc16(test)
    actual_crc = qris_string[-4:]
    if expected_crc != actual_crc:
        return False, "CRC salah"
    merchant = tags.get("59", "Unknown")
    city = tags.get("60", "-")
    return True, f"✅ Valid — {merchant} ({city})"


def get_qris_info(qris_string: str) -> dict:
    tags = parse_qris(qris_string)
    return {
        "merchant": tags.get("59", "-"),
        "city": tags.get("60", "-"),
        "postal": tags.get("61", "-"),
        "currency": tags.get("53", "-"),
        "country": tags.get("58", "-"),
        "nmid": tags.get("51", "-"),
    }


# ══════════════════════════════════════════════════════════════════
#  QR IMAGE — LOKAL + FALLBACK ONLINE (with cache)
# ══════════════════════════════════════════════════════════════════
_QR_CACHE = {}
_QR_CACHE_LOCK = threading.Lock()


def qris_to_image_bytes_local(qris_string: str, size: int = 400):
    try:
        import qrcode
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(qris_string)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as e:
        print(f"[QRIS-LOCAL] Error: {e}")
        return None


def qris_to_image_bytes_online(qris_string: str, size: int = 400):
    import requests, urllib.parse
    encoded = urllib.parse.quote(qris_string)
    sources = [
        f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={encoded}",
        f"https://quickchart.io/qr?text={encoded}&size={size}",
    ]
    for url in sources:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.content) > 100:
                return r.content
        except: continue
    return None


def qris_to_image_bytes(qris_string: str, size: int = 400):
    # Cache check
    cache_key = f"{qris_string[:50]}:{size}"
    with _QR_CACHE_LOCK:
        if cache_key in _QR_CACHE:
            return _QR_CACHE[cache_key]
    
    local = qris_to_image_bytes_local(qris_string, size)
    if local:
        print("[QRIS] Generated LOCALLY ✅")
        with _QR_CACHE_LOCK:
            _QR_CACHE[cache_key] = local
            if len(_QR_CACHE) > 100:
                _QR_CACHE.clear()
        return local
    print("[QRIS] Local fail, trying online...")
    online = qris_to_image_bytes_online(qris_string, size)
    if online:
        print("[QRIS] Generated ONLINE ✅")
        with _QR_CACHE_LOCK:
            _QR_CACHE[cache_key] = online
        return online
    print("[QRIS] ALL SOURCES FAILED ❌")
    return None


# ══════════════════════════════════════════════════════════════════
#  DONATION TRACKER (with atomic write)
# ══════════════════════════════════════════════════════════════════
class DonationTracker:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        if not self.path.exists():
            return {"donations": [], "totals": {"count": 0, "amount": 0}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except:
            # Backup corrupt file
            try:
                backup = self.path.with_suffix(f".corrupt.{int(time.time())}")
                self.path.rename(backup)
            except: pass
            return {"donations": [], "totals": {"count": 0, "amount": 0}}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except: pass

    def add(self, cid, username, amount, method="qris", note=""):
        with self.lock:
            entry = {
                "ts": datetime.now(TZ_WIB).isoformat(),
                "cid": str(cid),
                "username": username,
                "amount": int(amount),
                "method": method,
                "note": note,
                "confirmed": False,
                "license_key": None,
            }
            self.data["donations"].append(entry)
            self.data["totals"]["count"] += 1
            self.data["totals"]["amount"] += int(amount)
            self._save()
            return entry

    def set_license(self, cid, license_key):
        with self.lock:
            for d in reversed(self.data["donations"]):
                if d["cid"] == str(cid) and not d.get("license_key"):
                    d["license_key"] = license_key
                    self._save()
                    return True
        return False

    def list_recent(self, n=10):
        with self.lock:
            return self.data["donations"][-n:]

    def totals(self):
        with self.lock:
            return dict(self.data["totals"])

    def top_donors(self, n=5):
        with self.lock:
            donors = {}
            for d in self.data["donations"]:
                cid = d["cid"]
                if cid not in donors:
                    donors[cid] = {"username": d["username"], "total": 0, "count": 0}
                donors[cid]["total"] += d["amount"]
                donors[cid]["count"] += 1
            sorted_donors = sorted(donors.items(), key=lambda x: x[1]["total"], reverse=True)
            return sorted_donors[:n]

    def clear(self):
        with self.lock:
            self.data = {"donations": [], "totals": {"count": 0, "amount": 0}}
            self._save()
            return True


# ══════════════════════════════════════════════════════════════════
#  ACTIVE QRIS (with auto-cleanup)
# ══════════════════════════════════════════════════════════════════
_ACTIVE_QRIS = {}
_QRIS_LOCK = threading.Lock()


def register_qris(cid, message_id, amount):
    with _QRIS_LOCK:
        _ACTIVE_QRIS[str(cid)] = {
            "message_id": message_id,
            "amount": amount,
            "ts": time.time(),
        }


def get_active_qris(cid):
    with _QRIS_LOCK:
        item = _ACTIVE_QRIS.get(str(cid))
        if item and time.time() - item["ts"] > 600:
            _ACTIVE_QRIS.pop(str(cid), None)
            return None
        return item


def clear_qris(cid):
    with _QRIS_LOCK:
        _ACTIVE_QRIS.pop(str(cid), None)


def _cleanup_qris_loop():
    """Auto cleanup QRIS expired."""
    while True:
        try:
            time.sleep(300)
            now = time.time()
            with _QRIS_LOCK:
                expired = [k for k, v in _ACTIVE_QRIS.items() if now - v["ts"] > 600]
                for k in expired:
                    _ACTIVE_QRIS.pop(k, None)
        except: pass

threading.Thread(target=_cleanup_qris_loop, daemon=True).start()


# ══════════════════════════════════════════════════════════════════
#  PENDING APPROVAL (with auto-cleanup)
# ══════════════════════════════════════════════════════════════════
_PENDING_APPROVAL = {}
_PENDING_LOCK = threading.Lock()


def register_pending(cid, username, amount, message_id):
    with _PENDING_LOCK:
        _PENDING_APPROVAL[str(cid)] = {
            "username": username,
            "amount": amount,
            "message_id": message_id,
            "ts": time.time(),
        }


def get_pending(cid):
    with _PENDING_LOCK:
        return _PENDING_APPROVAL.get(str(cid))


def clear_pending(cid):
    with _PENDING_LOCK:
        _PENDING_APPROVAL.pop(str(cid), None)


def list_pending():
    with _PENDING_LOCK:
        return dict(_PENDING_APPROVAL)


def _cleanup_pending_loop():
    """Auto cleanup pending expired (>1 jam)."""
    while True:
        try:
            time.sleep(600)
            now = time.time()
            with _PENDING_LOCK:
                expired = [k for k, v in _PENDING_APPROVAL.items() if now - v["ts"] > 3600]
                for k in expired:
                    _PENDING_APPROVAL.pop(k, None)
        except: pass

threading.Thread(target=_cleanup_pending_loop, daemon=True).start()


# ══════════════════════════════════════════════════════════════════
#  MODE DONASI
# ══════════════════════════════════════════════════════════════════
def get_donate_mode(cfg):
    return cfg.get("donate_mode", "auto")


def set_donate_mode(cfg, mode):
    if mode not in ("auto", "manual", "hybrid"):
        return False
    cfg.set("donate_mode", mode)
    return True


def should_require_approval(cfg, amount):
    mode = get_donate_mode(cfg)
    if mode == "auto":
        return False
    elif mode == "manual":
        return True
    elif mode == "hybrid":
        return amount >= HYBRID_THRESHOLD
    return False


# ══════════════════════════════════════════════════════════════════
#  FORMAT PESAN — MENU & QRIS
# ══════════════════════════════════════════════════════════════════
def format_donate_menu(cfg) -> str:
    presets = cfg.get("presets", [5000, 10000, 20000, 50000, 100000, 150000])
    preset_text = " | ".join(f"<code>{p:,}</code>" for p in presets)
    min_d = cfg.get("min_donate", 1000)

    reward_lines = []
    for min_amt, role, days, label in REWARD_TIERS:
        star = " ⭐" if days is None else ""
        reward_lines.append(f"  💰 <b>Rp {min_amt:,}</b> → {label}{star}")
    reward_text = "\n".join(reward_lines)

    return (
        f"💰 <b>DONASI</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Terima kasih telah mendukung bot ini! 🙏\n\n"
        f"<b>📌 Cara Donasi:</b>\n"
        f"1️⃣ Pilih nominal di bawah\n"
        f"2️⃣ Scan QRIS yang muncul\n"
        f"3️⃣ Bayar via e-wallet/banking\n"
        f"4️⃣ Klik <b>✅ Sudah Bayar</b>\n"
        f"5️⃣ License otomatis aktif! 🎁\n\n"
        f"<b>💵 Nominal Cepat:</b>\n"
        f"{preset_text}\n\n"
        f"<b>📊 Minimal:</b> <code>Rp {min_d:,}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎁 <b>BONUS LICENSE:</b>\n"
        f"{reward_text}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🌏 <b>Cross-Border Support:</b>\n"
        f"🇸🇬 SG | 🇲🇾 MY | 🇹🇭 TH\n"
        f"🇯🇵 JP | 🇰🇷 KR | 🇨🇳 CN\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💡 Ketik <code>/donate NOMINAL</code>"
    )


def format_donate_qris(cfg, amount: int, cid: str) -> str:
    merchant = cfg.get("merchant_name", "PeiterStore")
    nmid = cfg.get("nmid", "-")
    ts = datetime.now(TZ_WIB).strftime("%Y-%m-%d %H:%M WIB")
    reward = get_reward(amount)
    reward_text = ""
    if reward:
        durasi = "♾ PERMANEN" if reward["days"] is None else reward['label']
        reward_text = (
            f"━━━━━━━━━━━━━━━\n"
            f"🎁 <b>BONUS LICENSE:</b>\n"
            f"🎭 Role   : <b>{reward['role'].upper()}</b>\n"
            f"📅 Durasi : <b>{durasi}</b>\n"
        )
    return (
        f"💳 <b>QRIS DONASI</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🏪 Merchant : <b>{merchant}</b>\n"
        f"🆔 NMID     : <code>{nmid}</code>\n"
        f"💰 Nominal  : <b>Rp {amount:,}</b>\n"
        f"🕒 Waktu    : {ts}\n"
        f"🆔 Order ID : <code>DON-{cid}-{int(time.time())}</code>\n"
        f"{reward_text}"
        f"━━━━━━━━━━━━━━━\n"
        f"📱 <b>Scan QR untuk bayar</b>\n"
        f"🌏 Support cross-border\n"
        f"⌛ QRIS berlaku <b>5 menit</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ Setelah bayar, klik <b>✅ Sudah Bayar</b>"
    )


def format_donate_paid(amount, cid, license_key=None, reward=None):
    ts = datetime.now(TZ_WIB).strftime("%Y-%m-%d %H:%M WIB")
    reward_text = ""
    if reward and license_key:
        durasi = "♾ PERMANEN" if reward["days"] is None else reward['label']
        reward_text = (
            f"━━━━━━━━━━━━━━━\n"
            f"🎁 <b>BONUS LICENSE AKTIF!</b>\n"
            f"🎭 Role   : <b>{reward['role'].upper()}</b>\n"
            f"📅 Durasi : <b>{durasi}</b>\n"
            f"🔑 Key    : <code>{license_key}</code>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✅ Akses kamu sudah aktif!\n"
            f"Ketik /menu untuk mulai 🚀"
        )
    else:
        reward_text = (
            f"━━━━━━━━━━━━━━━\n"
            f"<i>Terima kasih! 🙏</i>\n"
            f"<i>Owner akan konfirmasi setelah cek mutasi.</i>"
        )
    return (
        f"✅ <b>DONASI DIKONFIRMASI</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Nominal  : <b>Rp {amount:,}</b>\n"
        f"🆔 Order ID : <code>DON-{cid}-{int(time.time())}</code>\n"
        f"🕒 Waktu    : {ts}\n"
        f"{reward_text}"
    )


def format_donate_cancelled(amount: int) -> str:
    return (
        f"❌ <b>DONASI DIBATALKAN</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Nominal  : <s>Rp {amount:,}</s>\n"
        f"🚫 Status   : <b>CANCELLED</b>\n"
        f"🕒 Waktu    : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M WIB')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>QRIS sudah tidak berlaku</i>\n\n"
        f"Ketik /donate untuk donasi lagi."
    )


def format_donate_expired(amount: int) -> str:
    return (
        f"⌛ <b>QRIS EXPIRED</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Nominal  : <s>Rp {amount:,}</s>\n"
        f"🚫 Status   : <b>EXPIRED</b>\n"
        f"🕒 Waktu    : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M WIB')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<i>QRIS berlaku 5 menit</i>\n\n"
        f"Ketik /donate untuk donasi lagi."
    )


def format_donate_manual(cfg) -> str:
    bank = cfg.get("bank_name", "BCA")
    bank_acc = cfg.get("bank_account", "-")
    bank_holder = cfg.get("bank_holder", "-")
    ewallet = cfg.get("ewallet_name", "DANA")
    ewallet_num = cfg.get("ewallet_number", "-")
    ewallet_holder = cfg.get("ewallet_holder", "-")
    return (
        f"🏦 <b>DONASI MANUAL</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>🏦 Bank Transfer:</b>\n"
        f"  Bank    : {bank}\n"
        f"  No. Rek : <code>{bank_acc}</code>\n"
        f"  Nama    : {bank_holder}\n\n"
        f"<b>📱 E-Wallet:</b>\n"
        f"  Wallet  : {ewallet}\n"
        f"  No. HP  : <code>{ewallet_num}</code>\n"
        f"  Nama    : {ewallet_holder}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ <i>Setelah transfer, kirim bukti ke owner</i>"
    )


def format_donate_owner_notif(cid, username, amount, method="qris",
                               license_key=None, reward=None):
    ts = datetime.now(TZ_WIB).strftime("%Y-%m-%d %H:%M:%S WIB")
    reward_text = ""
    if reward:
        durasi = "♾ PERMANEN" if reward["days"] is None else reward['label']
        key_line = f"🔑 Key    : <code>{license_key}</code>\n" if license_key else "🔑 Key    : <i>pending</i>\n"
        reward_text = (
            f"━━━━━━━━━━━━━━━\n"
            f"🎁 <b>REWARD INFO:</b>\n"
            f"🎭 Role   : <b>{reward['role'].upper()}</b>\n"
            f"📅 Durasi : <b>{durasi}</b>\n"
            f"{key_line}"
        )
    return (
        f"💰 <b>DONASI MASUK</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 User    : <b>{username}</b>\n"
        f"🆔 Chat ID : <code>{cid}</code>\n"
        f"💵 Nominal : <b>Rp {amount:,}</b>\n"
        f"📱 Metode  : <b>{method.upper()}</b>\n"
        f"🕒 Waktu   : {ts}\n"
        f"{reward_text}"
        f"━━━━━━━━━━━━━━━\n"
        f"✅ Donasi tercatat!"
    )


def format_donate_stats(tracker) -> str:
    totals = tracker.totals()
    top = tracker.top_donors(5)
    txt = (
        f"📊 <b>Donasi Stats</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📦 Total    : <b>{totals.get('count', 0)}</b> donasi\n"
        f"💰 Amount   : <b>Rp {totals.get('amount', 0):,}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>🏆 Top Donors:</b>\n"
    )
    if not top:
        txt += "<i>Belum ada donatur</i>"
    else:
        for cid, info in top:
            txt += f"• <b>{info['username']}</b> — Rp {info['total']:,} ({info['count']}x)\n"
    return txt


def format_donate_list(tracker, n=15) -> str:
    recent = tracker.list_recent(n)
    if not recent:
        return "📭 Belum ada donasi"
    txt = f"📋 <b>Donasi Terakhir</b>\n\n"
    for d in recent:
        status = "✅" if d.get("confirmed") else "⏳"
        ts = d['ts'][:16].replace('T', ' ')
        lic = d.get("license_key", "")
        lic_text = f"\n   🔑 <code>{lic}</code>" if lic else ""
        txt += (f"{status} <b>{d['username']}</b> — Rp {d['amount']:,}\n"
                f"   <i>{ts} | {d['method']}</i>{lic_text}\n")
    return txt


def format_rewards_table() -> str:
    lines = ["🎁 <b>REWARD TIERS</b>", "━━━━━━━━━━━━━━━"]
    for min_amt, role, days, label in REWARD_TIERS:
        lines.append(f"💰 Rp {min_amt:,} → {label}")
    lines.append("━━━━━━━━━━━━━━━")
    lines.append("⭐ = PERMANEN")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  FORMAT PESAN — MODE & APPROVAL
# ══════════════════════════════════════════════════════════════════
def format_mode_info(cfg) -> str:
    mode = get_donate_mode(cfg)
    mode_text = {
        "auto": "⚡ AUTO — User klik 'Sudah Bayar' → langsung dapat license",
        "manual": "🔒 MANUAL — User klik 'Sudah Bayar' → owner harus approve",
        "hybrid": f"⚖️ HYBRID — Auto < Rp {HYBRID_THRESHOLD:,}, Manual ≥ Rp {HYBRID_THRESHOLD:,}",
    }.get(mode, "❓ Unknown")

    return (
        f"⚙️ <b>MODE DONASI</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📌 Mode: <b>{mode.upper()}</b>\n"
        f"{mode_text}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>📋 Pilihan:</b>\n"
        f"• <code>/donatemode auto</code> — Instan\n"
        f"• <code>/donatemode manual</code> — Aman\n"
        f"• <code>/donatemode hybrid</code> — Campuran\n"
        f"━━━━━━━━━━━━━━━\n"
        f"<b>🔧 Approval Commands:</b>\n"
        f"• <code>/donatepending</code> — Lihat pending\n"
        f"• Tombol di notif → Approve/Reject"
    )


def format_pending_notif(cid, username, amount) -> str:
    reward = get_reward(amount)
    reward_text = ""
    if reward:
        durasi = "♾ PERMANEN" if reward["days"] is None else reward["label"]
        reward_text = (
            f"━━━━━━━━━━━━━━━\n"
            f"🎁 <b>Reward:</b>\n"
            f"🎭 Role   : <b>{reward['role'].upper()}</b>\n"
            f"📅 Durasi : <b>{durasi}</b>\n"
        )
    return (
        f"💰 <b>DONASI PENDING APPROVAL</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 User    : <b>{username}</b>\n"
        f"🆔 Chat ID : <code>{cid}</code>\n"
        f"💵 Nominal : <b>Rp {amount:,}</b>\n"
        f"🕒 Waktu   : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
        f"{reward_text}"
        f"━━━━━━━━━━━━━━━\n"
        f"⚠️ <b>Cek mutasi DANA dulu!</b>"
    )


def format_waiting_approval(amount: int) -> str:
    return (
        f"⏳ <b>MENUNGGU KONFIRMASI OWNER</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Nominal : <b>Rp {amount:,}</b>\n"
        f"🕒 Waktu   : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M WIB')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Owner akan cek mutasi & konfirmasi.\n"
        f"<i>Estimasi: 5-30 menit</i>"
    )


def format_approved(amount, reward, license_key) -> str:
    durasi = "♾ PERMANEN" if reward["days"] is None else reward["label"]
    return (
        f"✅ <b>DONASI DIKONFIRMASI!</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Nominal : <b>Rp {amount:,}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"🎁 <b>BONUS LICENSE AKTIF!</b>\n"
        f"🎭 Role   : <b>{reward['role'].upper()}</b>\n"
        f"📅 Durasi : <b>{durasi}</b>\n"
        f"🔑 Key    : <code>{license_key}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"✅ Ketik /menu untuk mulai 🚀"
    )


def format_rejected(amount) -> str:
    return (
        f"❌ <b>DONASI DITOLAK</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"💰 Nominal : <b>Rp {amount:,}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"Owner tidak menemukan pembayaran di mutasi.\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📞 Hubungi owner jika ini kesalahan."
    )


def format_approved_owner(cid, username, amount, reward, license_key):
    durasi = "♾ PERMANEN" if reward["days"] is None else reward["label"]
    return (
        f"✅ <b>DONASI DI-APPROVE</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 User    : <b>{username}</b>\n"
        f"🆔 Chat ID : <code>{cid}</code>\n"
        f"💵 Nominal : <b>Rp {amount:,}</b>\n"
        f"🎭 Reward  : <b>{reward['role'].upper()}</b>\n"
        f"📅 Durasi  : <b>{durasi}</b>\n"
        f"🔑 Key     : <code>{license_key}</code>\n"
        f"🕒 Waktu   : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M WIB')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"✅ License sudah dikirim ke user"
    )


def format_rejected_owner(cid, username, amount):
    return (
        f"❌ <b>DONASI DI-REJECT</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👤 User    : <b>{username}</b>\n"
        f"🆔 Chat ID : <code>{cid}</code>\n"
        f"💵 Nominal : <b>Rp {amount:,}</b>\n"
        f"🕒 Waktu   : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M WIB')}\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📭 Notif sudah dikirim ke user"
    )


# ══════════════════════════════════════════════════════════════════
#  KEYBOARDS
# ══════════════════════════════════════════════════════════════════
def kb_donate(cfg):
    presets = cfg.get("presets", [5000, 10000, 20000, 50000, 100000, 150000])
    kb = []
    row = []
    for p in presets[:6]:
        row.append({"text": f"💵 {p:,}", "callback_data": f"don_{p}"})
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    kb.append([
        {"text": "✏️ Custom", "callback_data": "don_custom"},
        {"text": "🏦 Manual", "callback_data": "don_manual"},
    ])
    kb.append([{"text": "« Kembali", "callback_data": "menu_main"}])
    return kb


def kb_donate_back():
    return [[{"text": "« Kembali", "callback_data": "don_menu"}]]


def kb_qris_active(cid):
    return [
        [{"text": "✅ Sudah Bayar", "callback_data": "don_paid"}],
        [{"text": "❌ Batal Donasi", "callback_data": "don_cancel"}],
        [{"text": "« Menu Utama", "callback_data": "menu_main"}],
    ]


def kb_qris_cancelled():
    return [
        [{"text": "💰 Donasi Lagi", "callback_data": "don_menu"}],
        [{"text": "« Menu Utama", "callback_data": "menu_main"}],
    ]


def kb_qris_expired():
    return [
        [{"text": "🔄 Buat QRIS Baru", "callback_data": "don_menu"}],
        [{"text": "« Menu Utama", "callback_data": "menu_main"}],
    ]


def kb_pending_approval(user_cid):
    return [
        [{"text": "✅ APPROVE", "callback_data": f"don_appr_{user_cid}"},
         {"text": "❌ REJECT", "callback_data": f"don_rej_{user_cid}"}],
        [{"text": "👤 Lihat User", "callback_data": f"don_info_{user_cid}"}],
    ]