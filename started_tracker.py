#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
STARTED TRACKER — Simpen semua user yang pernah /start
Plus notif ke owner & admin kalo ada user baru
"""

import json, threading, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

TZ_WIB = timezone(timedelta(hours=7))

_LOCK = threading.Lock()


class StartedTracker:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        if not self.path.exists():
            return {"users": {}, "total": 0}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if "users" not in data:
                data["users"] = {}
            return data
        except Exception:
            # Backup corrupt file
            try:
                backup = self.path.with_suffix(f".corrupt.{int(time.time())}")
                self.path.rename(backup)
            except: pass
            return {"users": {}, "total": 0}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
            tmp.replace(self.path)
        except Exception:
            pass

    def add(self, cid, username="User", first_name="", last_name="", username_tg=""):
        """Tambah user ke database. Kalau udah ada, update info."""
        cid = str(cid)
        with self.lock:
            if cid not in self.data["users"]:
                self.data["users"][cid] = {
                    "cid": cid,
                    "username": username,
                    "first_name": first_name,
                    "last_name": last_name,
                    "username_tg": username_tg,
                    "first_start": time.time(),
                    "last_start": time.time(),
                    "start_count": 1,
                    "blocked": False,
                }
                self.data["total"] = len(self.data["users"])
            else:
                u = self.data["users"][cid]
                u["last_start"] = time.time()
                u["start_count"] = u.get("start_count", 0) + 1
                if username_tg:
                    u["username_tg"] = username_tg
                if first_name:
                    u["first_name"] = first_name
            self._save()
            return self.data["users"][cid]

    def add_with_notif(self, cid, username, first_name, last_name,
                       username_tg, tg_send, owner_id, admin_ids=None,
                       is_new=True):
        """Tambah user + notif ke owner & admin."""
        user = self.add(cid, username, first_name, last_name, username_tg)

        if not is_new:
            return user

        # Notif ke OWNER (lengkap)
        try:
            stats = self.stats()
            owner_msg = (
                f"🆕 <b>USER BARU START</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"👤 Nama     : <b>{first_name} {last_name}</b>\n"
                f"📛 Username : @{username_tg or '-'}\n"
                f"🆔 Chat ID  : <code>{cid}</code>\n"
                f"🕒 Waktu    : {datetime.now(TZ_WIB).strftime('%Y-%m-%d %H:%M:%S WIB')}\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📊 Total user: <b>{stats['total']}</b>\n"
                f"✅ Aktif     : <b>{stats['active']}</b>\n"
                f"📅 Last 24h  : <b>{stats['last_24h']}</b>\n"
                f"📆 Last 7d   : <b>{stats['last_7d']}</b>\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🎭 Role: <b>USER</b>"
            )
            tg_send(owner_id, owner_msg)
        except Exception as e:
            print(f"[NOTIF OWNER ERR] {e}")

        # Notif ke ADMIN (ringkas)
        if admin_ids:
            admin_msg = (
                f"🆕 <b>User Baru</b>\n"
                f"👤 {first_name} {last_name}\n"
                f"📛 @{username_tg or '-'}\n"
                f"🆔 <code>{cid}</code>\n"
                f"🕒 {datetime.now(TZ_WIB).strftime('%H:%M WIB')}"
            )
            for admin_id in admin_ids:
                try:
                    tg_send(admin_id, admin_msg)
                    time.sleep(0.1)
                except Exception:
                    pass

        return user

    def get_all(self):
        """Return semua user yang pernah start."""
        with self.lock:
            return list(self.data["users"].values())

    def get_all_cids(self):
        """Return list of Chat ID."""
        with self.lock:
            return list(self.data["users"].keys())

    def get_user(self, cid):
        """Return user by cid."""
        cid = str(cid)
        with self.lock:
            return self.data["users"].get(cid)

    def count(self):
        with self.lock:
            return len(self.data["users"])

    def mark_blocked(self, cid):
        """Tandai user yang udah block bot."""
        cid = str(cid)
        with self.lock:
            u = self.data["users"].get(cid)
            if u:
                u["blocked"] = True
                self._save()

    def unmark_blocked(self, cid):
        """Hapus tanda blocked."""
        cid = str(cid)
        with self.lock:
            u = self.data["users"].get(cid)
            if u:
                u["blocked"] = False
                self._save()

    def remove(self, cid):
        """Hapus user dari database."""
        cid = str(cid)
        with self.lock:
            if cid in self.data["users"]:
                del self.data["users"][cid]
                self.data["total"] = len(self.data["users"])
                self._save()
                return True
        return False

    def search(self, keyword):
        """Cari user by username/nama."""
        keyword = str(keyword).lower()
        with self.lock:
            return [
                u for u in self.data["users"].values()
                if keyword in u.get("username_tg", "").lower()
                or keyword in u.get("first_name", "").lower()
                or keyword in u.get("username", "").lower()
                or keyword in u.get("cid", "")
            ]

    def stats(self):
        """Statistik lengkap."""
        with self.lock:
            users = list(self.data["users"].values())
            total = len(users)
            blocked = sum(1 for u in users if u.get("blocked"))
            active = total - blocked
            now = time.time()
            last_24h = sum(1 for u in users if now - u.get("last_start", 0) < 86400)
            last_7d = sum(1 for u in users if now - u.get("last_start", 0) < 604800)
            return {
                "total": total,
                "active": active,
                "blocked": blocked,
                "last_24h": last_24h,
                "last_7d": last_7d,
            }

    def clear(self):
        """Hapus semua data."""
        with self.lock:
            self.data = {"users": {}, "total": 0}
            self._save()
            return True

    def export_csv(self, path):
        """Export ke CSV."""
        import csv
        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["CID", "Username", "First Name", "Last Name",
                            "TG Username", "First Start", "Last Start",
                            "Start Count", "Blocked"])
                for u in self.get_all():
                    w.writerow([
                        u.get("cid", ""),
                        u.get("username", ""),
                        u.get("first_name", ""),
                        u.get("last_name", ""),
                        u.get("username_tg", ""),
                        datetime.fromtimestamp(u.get("first_start", 0), TZ_WIB).strftime("%Y-%m-%d %H:%M"),
                        datetime.fromtimestamp(u.get("last_start", 0), TZ_WIB).strftime("%Y-%m-%d %H:%M"),
                        u.get("start_count", 0),
                        "YES" if u.get("blocked") else "NO",
                    ])
            return True
        except:
            return False


def broadcast_to_started(tracker, message, tg_send, delay=0.35, skip_blocked=True):
    """
    Kirim pesan ke semua user yang pernah start.
    Return (sukses, gagal, blocked).
    """
    users = tracker.get_all()
    success = 0
    fail = 0
    blocked_new = 0
    consecutive_fails = 0

    for u in users:
        cid = u.get("cid")
        if not cid:
            continue
        if skip_blocked and u.get("blocked"):
            continue

        try:
            ok = tg_send(cid, message)
            if ok:
                success += 1
                consecutive_fails = 0
            else:
                fail += 1
                # Track fail streak
                fail_streak = u.get("_fail_streak", 0) + 1
                u["_fail_streak"] = fail_streak
                if fail_streak >= 3:
                    tracker.mark_blocked(cid)
                    blocked_new += 1
                consecutive_fails += 1
                if consecutive_fails >= 5:
                    # Kemungkinan kena rate limit Telegram
                    time.sleep(30)
                    consecutive_fails = 0
        except Exception:
            fail += 1
            tracker.mark_blocked(cid)
            blocked_new += 1
            consecutive_fails += 1
            if consecutive_fails >= 5:
                time.sleep(30)
                consecutive_fails = 0

        time.sleep(delay)

    return success, fail, blocked_new


def get_stats_text(tracker):
    """Format statistik ke text."""
    if not tracker:
        return "❌ StartedTracker OFF"
    st = tracker.stats()
    return (
        f"👥 <b>STARTED USERS</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 Total   : <b>{st['total']}</b>\n"
        f"✅ Aktif   : <b>{st['active']}</b>\n"
        f"🚫 Blocked : <b>{st['blocked']}</b>\n"
        f"📅 Last 24h: <b>{st['last_24h']}</b>\n"
        f"📆 Last 7d : <b>{st['last_7d']}</b>"
    )


def get_list_text(tracker, max_show=50):
    """Format list user ke text."""
    if not tracker:
        return "❌ StartedTracker OFF"
    users = tracker.get_all()
    if not users:
        return "📭 Kosong"
    txt = f"👥 <b>List ({len(users)})</b>\n\n"
    for u in users[:max_show]:
        emoji = "🚫" if u.get("blocked") else "✅"
        uname = f"@{u.get('username_tg')}" if u.get("username_tg") else u.get("first_name", "?")
        txt += f"{emoji} <code>{u['cid']}</code> — {uname}\n"
    if len(users) > max_show:
        txt += f"\n<i>... +{len(users)-max_show} lainnya</i>"
    return txt


if __name__ == "__main__":
    # Test
    import tempfile
    tmp = Path(tempfile.gettempdir()) / "started_test.json"
    t = StartedTracker(tmp)
    t.add("123456", "User1", "Budi", "", "budi_tg")
    t.add("789012", "User2", "Ani", "", "ani_tg")
    print("Total:", t.count())
    print("Stats:", t.stats())
    print("All:", t.get_all_cids())
    print()
    print(get_stats_text(t))
    print()
    print(get_list_text(t))
    tmp.unlink(missing_ok=True)