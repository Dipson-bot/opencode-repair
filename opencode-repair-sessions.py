# -*- coding: utf-8 -*-
"""opencode-repair-sessions.py

A helper for when OpenCode misbehaves. Your chats are always saved on disk,
so this tool can fix, back up, save, or restart around them without losing
anything.

Options (also usable as first argument):
  1 repair   -> my chats stopped loading  =>  fix them
  2 backup   -> make a safety copy
  3 export   -> save a chat to a file so I can keep the conversation elsewhere
  4 reset    -> the app is stuck/frozen  =>  close it safely

Examples:
  python opencode-repair-sessions.py        (shows the menu)
  python opencode-repair-sessions.py repair
  python opencode-repair-sessions.py backup
  python opencode-repair-sessions.py export [session_id]
  python opencode-repair-sessions.py reset
"""

import sqlite3, shutil, os, datetime, sys, json, subprocess, re, html

SEP = os.sep
TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_DIR = os.path.join(TOOLS_DIR, "backups")
TRANSCRIPT_DIR = os.path.join(TOOLS_DIR, "transcripts")
HOME = os.environ.get("USERPROFILE") or os.path.expanduser("~")
OC_DATA = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.join(HOME, ".local", "share"), "opencode")
OC_CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.join(HOME, ".config"), "opencode")
DB = os.path.join(OC_DATA, "opencode.db")

# Executable names used by the OpenCode desktop app and CLI.
OC_PROCESS_NAMES = ("opencode.exe", "opencode-cli.exe")


class Cancelled(Exception):
    pass


def ask(prompt):
    """input() that turns Ctrl+C / closed input into a clean cancel."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Cancelled()


def banner():
    print("==================================================")
    print("  OpenCode helper  -  fixes, backups & more")
    print("==================================================")
    print()


def norm_to_windows(path):
    return path.replace("/", SEP) if path else path


def now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def fmt_time(ms):
    if not ms:
        return "-"
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M")


def safe_filename(s, limit=60):
    s = (s or "untitled").strip()
    for ch in '<>:"/\\|?*':
        s = s.replace(ch, "_")
    s = " ".join(s.split())
    return s[:limit].rstrip(" .") or "untitled"


def db_missing():
    if os.path.isfile(DB):
        return False
    print("[ERROR] opencode database not found at:\n        %s" % DB)
    return True


# --------------------------------------------------------------------------
# Common helpers
# --------------------------------------------------------------------------

def connect_ro():
    # Listing/export never writes. A plain connection is used because WAL
    # allows concurrent readers while OpenCode is open.
    return sqlite3.connect(DB, timeout=5)


def list_sessions(conn):
    rows = conn.execute(
        """SELECT id, slug, title, directory, model, time_created, time_updated,
                  tokens_input, tokens_output, cost, parent_id
           FROM session ORDER BY time_updated DESC"""
    ).fetchall()
    out = []
    for r in rows:
        sid, slug, title, directory, model, created, updated, tin, tout, cost, parent = r
        try:
            m = json.loads(model)
            label = "%s/%s" % (m.get("providerID", "?"), m.get("id", "?"))
        except Exception:
            label = model or "?"
        out.append(
            {
                "id": sid,
                "slug": slug,
                "title": title or "(no title)",
                "directory": directory,
                "model": label,
                "created": fmt_time(created),
                "updated": fmt_time(updated),
                "tokens_in": tin,
                "tokens_out": tout,
                "cost": cost,
                "subagent": bool(parent),
            }
        )
    return out


def pick_session(conn):
    sessions = list_sessions(conn)
    if not sessions:
        print("  No sessions found in the database.")
        return None
    print("  Your chats (most recent first):\n")
    for i, s in enumerate(sessions, 1):
        print("  [%2d] %s%s" % (i, s["updated"], "  (helper sub-chat)" if s["subagent"] else ""))
        print("       %s" % (s["title"][:70]))
        print("       %s  assistant=%s  size=%d / %d"
              % (s["directory"] or "(no folder)", s["model"], s["tokens_in"] or 0, s["tokens_out"] or 0))
    print()
    while True:
        ans = ask("  Which chat? Type its number, or 0 to cancel -> ")
        if ans == "0":
            return None
        if ans.isdigit() and 1 <= int(ans) <= len(sessions):
            return sessions[int(ans) - 1]
        print("  Invalid choice.")


def sqlite_copy(dest):
    """Consistent copy of the live database (includes unflushed WAL data)."""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    src = sqlite3.connect(DB, timeout=5)
    dst = sqlite3.connect(dest)
    try:
        with dst:
            src.backup(dst)
    finally:
        dst.close()
        src.close()


# --------------------------------------------------------------------------
# Mode 1: repair sessions whose folder is missing
# --------------------------------------------------------------------------

def clean_user_path(answer):
    # "Copy as path" and drag-and-drop wrap paths in quotes.
    p = answer.strip().strip('"').strip("'").strip()
    if not p:
        return ""
    p = os.path.expandvars(os.path.expanduser(p))
    p = os.path.abspath(p).rstrip("\\/")
    if re.match(r"^[A-Za-z]:$", p):
        p += SEP
    return p


def find_candidates(missing_dir):
    """Existing sibling folders that look like the renamed/moved one."""
    parent = os.path.dirname(norm_to_windows(missing_dir))
    base = os.path.basename(norm_to_windows(missing_dir))
    if not parent or not os.path.isdir(parent):
        return []
    base_stripped = base.split(" - ")[0].split(" (")[0].lower()
    exact, similar = [], []
    try:
        entries = sorted(os.listdir(parent))
    except OSError:
        return []
    for entry in entries:
        full = os.path.join(parent, entry)
        if not os.path.isdir(full):
            continue
        if entry.lower() == base.lower():
            exact.append(full)
        elif base_stripped and entry.lower().startswith(base_stripped):
            similar.append(full)
    return exact + similar


def pick_dir(prompt, candidates=()):
    """Ask for an existing folder. Returns None if the user gives up."""
    print()
    if candidates:
        print("  Found these existing folders that look like the right one:")
        for i, c in enumerate(candidates, 1):
            print("    [%d] %s" % (i, c))
        print()
    while True:
        if candidates:
            answer = ask("  Type a number, a full folder path, or Enter to use [1] (0 = skip) -> ")
        else:
            answer = ask(prompt + " (type the full folder path, or Enter to skip) -> ")
        if answer == "0" or (not answer and not candidates):
            return None
        if not answer:
            return candidates[0]
        if answer.isdigit() and candidates:
            i = int(answer)
            if 1 <= i <= len(candidates):
                return candidates[i - 1]
            print("  Invalid number.")
            continue
        path = clean_user_path(answer)
        if os.path.isdir(path):
            return path
        print("  [WARN] That folder does not exist: %s" % path)
        print("         Please check the spelling and try again.")


def to_db_dir(path):
    # OpenCode stores "C:/Users/me/proj"
    return path.replace("\\", "/")


def to_db_path(db_dir):
    # ...and the same path without drive and leading slash: "Users/me/proj"
    return re.sub(r"^[A-Za-z]:", "", db_dir).lstrip("/")


def resolve_project_id(cur, db_dir):
    for sql in (
        "SELECT project_id FROM project_directory WHERE lower(directory) = lower(?)",
        "SELECT id FROM project WHERE lower(worktree) = lower(?)",
        "SELECT project_id FROM workspace WHERE lower(directory) = lower(?)",
    ):
        row = cur.execute(sql, (db_dir,)).fetchone()
        if row:
            return row[0]
    return None


def mode_repair():
    if db_missing():
        return

    print("[NOTE] This fixes chats by pointing them at the folder they belong to.")
    print("[IMPORTANT] Close OpenCode completely FIRST (all windows).")
    print("[NOTE] A safety backup is made before any change.\n")

    if opencode_processes():
        print("[WARN] OpenCode is still running. It may undo the fix or the")
        print("       database may be busy. Close it first (or use option 4).")
        if ask("  Continue anyway? [y/N] -> ").lower() != "y":
            print("Cancelled. Nothing was changed.")
            return

    conn = connect_ro()
    rows = conn.execute("SELECT id, directory, title FROM session").fetchall()
    conn.close()

    broken_dirs = {}
    for sid, directory, title in rows:
        if not directory:
            continue
        if not os.path.isdir(norm_to_windows(directory)):
            broken_dirs.setdefault(directory, []).append((sid, title))

    if not broken_dirs:
        print("[OK] No broken chats found. Nothing needs fixing.")
        return

    print("[FOUND] The following chats point to a folder that doesn't exist:\n")
    for d, sessions in broken_dirs.items():
        print("  Missing folder: %s  (%d chat(s))" % (d, len(sessions)))
        for sid, title in sessions[:5]:
            print("      - %s  |  %s" % (sid, (title or "(no title)")[:60]))
        if len(sessions) > 5:
            print("      ... and %d more" % (len(sessions) - 5))
    print()

    # Collect all decisions first; change nothing until the user confirms.
    plan = []  # (list of session ids, new folder)
    same = len(broken_dirs) > 1 and ask("  Should they ALL go to the same folder? [y/N] -> ").lower() == "y"
    if same:
        candidates = []
        for d in broken_dirs:
            candidates += find_candidates(d)
        candidates = list(dict.fromkeys(candidates))
        new_dir = pick_dir("  Move ALL these chats to which folder?", candidates)
        if new_dir:
            plan.append(([s[0] for ss in broken_dirs.values() for s in ss], new_dir))
    else:
        for d, sessions in broken_dirs.items():
            print("\n  Chats from the missing folder: %s" % d)
            new_dir = pick_dir("  Which folder should these chats go to?", find_candidates(d))
            if new_dir:
                plan.append(([s[0] for s in sessions], new_dir))
            else:
                print("      Skipped.")

    if not plan:
        print("\nNothing was changed.")
        return

    print("\n  About to fix:")
    for ids, new_dir in plan:
        print("    %d chat(s) -> %s" % (len(ids), new_dir))
    if ask("  Go ahead? [Y/n] -> ").lower() not in ("", "y", "yes"):
        print("Cancelled. Nothing was changed.")
        return

    backup = os.path.join(BACKUP_DIR, "before-repair-%s.db" % now_stamp())
    sqlite_copy(backup)
    print("\n[OK] Safety copy saved -> %s" % backup)

    conn = sqlite3.connect(DB, timeout=10)
    try:
        cur = conn.cursor()
        for ids, new_dir in plan:
            apply_repoint(cur, ids, new_dir)
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        print("[ERROR] Could not update the chats (%s). Nothing was changed." % e)
        print("        Make sure OpenCode is fully closed and try again.")
        return
    finally:
        conn.close()
    print("\n[OK] All set. Start OpenCode again and open the folder above --")
    print("     your chats are back where you left them.")


def apply_repoint(cur, ids, new_dir):
    db_dir = to_db_dir(new_dir)
    db_path = to_db_path(db_dir)
    project_id = resolve_project_id(cur, db_dir)
    if project_id:
        cur.executemany(
            "UPDATE session SET directory=?, path=?, project_id=? WHERE id=?",
            [(db_dir, db_path, project_id, sid) for sid in ids],
        )
    else:
        # Unknown folder: keep each chat's project. For a moved/renamed git
        # repo OpenCode recomputes the same project id from the repo itself.
        cur.executemany(
            "UPDATE session SET directory=?, path=? WHERE id=?",
            [(db_dir, db_path, sid) for sid in ids],
        )
    print("      Fixed %d chat(s) -> now pointing at: %s" % (len(ids), db_dir))


# --------------------------------------------------------------------------
# Mode 2: backup opencode data
# --------------------------------------------------------------------------

def mode_backup():
    if db_missing():
        return

    dest = os.path.join(BACKUP_DIR, "opencode-backup-" + now_stamp())
    db_dest = os.path.join(dest, "opencode.db")
    sqlite_copy(db_dest)
    print("[OK] Safety copy of your chats saved -> %s" % db_dest)

    log_src = os.path.join(OC_DATA, "log")
    if os.path.isdir(log_src):
        shutil.copytree(log_src, os.path.join(dest, "log"))
        print("[OK] Activity logs copied.")

    for folder, f in ((OC_DATA, "auth.json"),
                      (OC_CONFIG, "opencode.jsonc"),
                      (OC_CONFIG, "opencode.json"),
                      (OC_CONFIG, "AGENTS.md")):
        p = os.path.join(folder, f)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(dest, f))
            print("[OK] Login/settings file copied: %s" % f)

    print("\n[OK] Backup complete. Keep this folder safe:\n     %s" % dest)


# --------------------------------------------------------------------------
# Mode 3: export a chat transcript
# --------------------------------------------------------------------------

def part_md(part):
    kind = part.get("type", "")
    if kind == "text":
        if part.get("ignored"):
            return ""
        text = part.get("text", "") or ""
        return "\n\n" + text.strip("\n")
    if kind == "reasoning":
        text = (part.get("text", "") or "").strip()
        if not text:
            return ""
        summary = text.split("\n", 1)[0][:120]
        return "\n\n<details><summary>reasoning: %s</summary>\n\n> %s\n\n</details>\n" % (
            html.escape(summary),
            text.replace("\n", "\n> "),
        )
    if kind == "tool":
        tool = part.get("tool", "?")
        state = part.get("state", {}) or {}
        status = state.get("status", "ok")
        input_str = json.dumps(state.get("input", {}), ensure_ascii=False)[:200].replace("`", "'")
        return "\n\n**[tool: %s | %s]** `%s`" % (tool, status, input_str)
    if kind == "file":
        return "\n\n*[file: %s]*" % (part.get("filename") or part.get("url", "?")[:100])
    return ""


def message_md(data, parts_md):
    try:
        meta = json.loads(data)
    except Exception:
        meta = {}
    role = meta.get("role", "?")
    model = meta.get("modelID") or ""
    provider = meta.get("providerID") or ""
    hdr = "## %s" % ("You" if role == "user" else "Assistant")
    if role == "assistant" and (provider or model):
        hdr += "  (`%s/%s`)" % (provider, model)
    return hdr + parts_md + "\n"


def mode_export(explicit=None):
    if db_missing():
        return

    conn = connect_ro()
    try:
        if explicit:
            session = next((s for s in list_sessions(conn) if s["id"] == explicit), None)
            if not session:
                print("[ERROR] No session with id %s" % explicit)
                return
        else:
            session = pick_session(conn)
            if not session:
                return

        msgs = conn.execute(
            "SELECT id, data FROM message WHERE session_id=? ORDER BY time_created, id",
            (session["id"],),
        ).fetchall()
        if not msgs:
            print("[WARN] No messages found in that session.")
            return

        by_msg = {}
        for mid, data in conn.execute(
            "SELECT message_id, data FROM part WHERE session_id=? ORDER BY time_created, id",
            (session["id"],),
        ):
            try:
                by_msg.setdefault(mid, []).append(json.loads(data))
            except Exception:
                pass
    finally:
        conn.close()

    lines = [
        "# %s" % session["title"],
        "",
        "- Session: `%s`" % session["id"],
        "- Folder: `%s`" % (session["directory"] or "-"),
        "- Model: `%s`" % session["model"],
        "- Created: %s  |  Updated: %s" % (session["created"], session["updated"]),
    ]
    if session["tokens_in"] or session["tokens_out"]:
        lines.append("- Tokens: in %s, out %s" % (session["tokens_in"], session["tokens_out"]))
    if session["cost"]:
        lines.append("- Cost: $%.4f" % session["cost"])
    lines += ["", "_Exported by opencode-repair-sessions.py on %s._" % now_stamp(), ""]

    body = []
    for mid, data in msgs:
        parts_md = "".join(part_md(p) for p in by_msg.get(mid, []))
        if parts_md.strip():
            body.append(message_md(data, parts_md))

    os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
    fname = "%s-%s-%s.md" % (session["slug"] or "chat", safe_filename(session["title"]), session["id"][-6:])
    fpath = os.path.join(TRANSCRIPT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines + body))

    print("\n[OK] Your chat was saved to a file:\n     %s" % fpath)
    print("     (%d messages)" % len(body))
    print("\n[NOTE] You can open that file anytime. To continue the conversation")
    print("       while the assistant is unavailable, copy your last reply + your")
    print("       next question into a fresh chat here or in another assistant.")
    print("       Nothing is lost either way.")


# --------------------------------------------------------------------------
# Mode 4: force-quit / reset a stuck OpenCode
# --------------------------------------------------------------------------

def opencode_processes():
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception:
        return []
    found = []
    for line in out.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[0].lower() in OC_PROCESS_NAMES:
            found.append((parts[0], parts[1]))
    return found


def mode_kill():
    procs = opencode_processes()
    if not procs:
        print("[OK] OpenCode is not running right now. Nothing to close.")
        return
    print("[FOUND] OpenCode is still open with these parts running:")
    for name, pid in procs:
        print("      %s (PID %s)" % (name, pid))
    print("\n  If OpenCode looks stuck/frozen, closing it is safe:")
    print("  ALL your chats are saved and will open again next time.")
    if ask("  Close OpenCode now? [y/N] -> ").lower() != "y":
        print("Cancelled.")
        return
    cmd = ["taskkill", "/F", "/T"]
    for _, pid in procs:
        cmd += ["/PID", pid]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        print("[ERROR] Could not close it: %s" % e)
        return
    left = opencode_processes()
    if left:
        print("[ERROR] Some parts of OpenCode are still running:")
        for name, pid in left:
            print("      %s (PID %s)" % (name, pid))
        print("        Try again, or close it from Task Manager.")
        return
    print("\n[OK] OpenCode closed. Your chats are saved and will be there")
    print("     next time you open the app.")


# --------------------------------------------------------------------------
# Main menu
# --------------------------------------------------------------------------

def run(fn, *args):
    try:
        fn(*args)
    except Cancelled:
        print("Cancelled.")
    except sqlite3.OperationalError as e:
        print("[ERROR] The chat database is busy or unreadable (%s)." % e)
        print("        Close OpenCode and try again.")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    mode = sys.argv[1].lower() if len(sys.argv) > 1 else None

    if mode == "repair":
        banner(); run(mode_repair); return
    if mode == "backup":
        banner(); run(mode_backup); return
    if mode == "export":
        banner(); run(mode_export, sys.argv[2] if len(sys.argv) > 2 else None); return
    if mode in ("kill", "reset"):
        banner(); run(mode_kill); return
    if mode in ("-h", "--help", "help"):
        print(__doc__); return
    if mode:
        print("Unknown option: %s\n" % mode)
        print(__doc__); return

    banner()
    print("  What's wrong? Pick the one that matches you:\n")
    print("  1. My chats won't load anymore  ->  FIX dead tabs")
    print("       (my chats 'stopped working' after I renamed/moved/deleted")
    print("        the project folder)")
    print("  2. Nothing is wrong, I just feel safer  ->  BACKUP my chats")
    print("       (save a safety copy before trying something)")
    print("  3. I can't use the assistant right now  ->  SAVE a chat to a file")
    print("       (the assistant is unavailable for a while, but I still need")
    print("        my conversation to continue it elsewhere)")
    print("  4. The app is stuck/frozen  ->  RESTART the app safely")
    print("       (close it without losing any chats)")
    print("  q. Quit")
    print()
    while True:
        try:
            choice = ask("  Type a number and press Enter -> ").lower()
        except Cancelled:
            choice = "q"
        if choice == "q":
            print("Bye.")
            return
        if choice == "1":
            run(mode_repair)
        elif choice == "2":
            run(mode_backup)
        elif choice == "3":
            run(mode_export)
        elif choice == "4":
            run(mode_kill)
        else:
            print("  Invalid choice.")
        print()


if __name__ == "__main__":
    main()
