import json
import os
import re
import urllib.request
import urllib.error
from datetime import datetime
import hashlib

API_URL = "https://jecnarozvrh.jzitnik.dev/versioned/v3"
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
TIMETABLE_FILE = os.path.join(os.path.dirname(__file__), "timetable_c3a.json")

PERIOD_TIMES = [
    ("1. hodina", "07:30 – 08:15"),
    ("2. hodina", "08:25 – 09:10"),
    ("3. hodina", "09:20 – 10:05"),
    ("4. hodina", "10:20 – 11:05"),
    ("5. hodina", "11:15 – 12:00"),
    ("6. hodina", "12:10 – 12:55"),
    ("7. hodina", "13:05 – 13:50"),
    ("8. hodina", "14:00 – 14:45"),
    ("9. hodina", "14:50 – 15:35"),
    ("10. hodina", "15:40 – 16:25"),
]

WEEKDAYS_CZ = {
    0: "Pondělí",
    1: "Úterý",
    2: "Středa",
    3: "Čtvrtek",
    4: "Pátek",
    5: "Sobota",
    6: "Neděle"
}


def load_timetable():
    if os.path.exists(TIMETABLE_FILE):
        try:
            with open(TIMETABLE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Chyba při čtení timetable_c3a.json: {e}")
    return {}


def load_config():
    cfg = {
        "target_class": "C3a",
        "discord_webhook_url": "",
        "check_interval_seconds": 300,
        "port": 8080,
        "notify_on_in_work": True,
        "selected_group": "all",
        "last_sent_hashes": {}
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            print(f"Chyba při čtení config.json: {e}")

    env_webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if env_webhook:
        cfg["discord_webhook_url"] = env_webhook.strip()

    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Chyba při ukládání config.json: {e}")


def format_czech_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        w_name = WEEKDAYS_CZ.get(dt.weekday(), "")
        return f"{w_name} {dt.day}. {dt.month}. {dt.year}"
    except Exception:
        return date_str


def format_regular_lesson(lesson_data):
    if not lesson_data:
        return None
    if isinstance(lesson_data, list):
        parts = []
        for item in lesson_data:
            g = f"[{item.get('group', '')}]" if item.get('group') else ""
            parts.append(f"{g} {item.get('subject')} ({item.get('teacher')}, uč. {item.get('room')})")
        return " / ".join(parts)
    elif isinstance(lesson_data, dict):
        return f"{lesson_data.get('subject')} ({lesson_data.get('teacher')}, uč. {lesson_data.get('room')})"
    return str(lesson_data)


def fetch_raw_api_data():
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": "JecnaSuplMonitor/1.0 (Student Tool for C3a)"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse_schedule_for_class(raw_data, target_class="C3a"):
    status = raw_data.get("status", {})
    schedule_data = raw_data.get("schedule", {})
    announcements = raw_data.get("announcements", {})
    timetable_info = load_timetable()
    tt_days = timetable_info.get("timetable", {})
    subjects_map = timetable_info.get("subjects", {})

    parsed_days = []

    for date_key, day_data in schedule_data.items():
        info = day_data.get("info", {})
        in_work = info.get("inWork", False)
        all_changes = day_data.get("changes", {})
        c3a_changes = all_changes.get(target_class, [None] * 10)
        takes_place = day_data.get("takesPlace", "") or ""
        absence = day_data.get("absence", []) or []
        reserved_rooms = day_data.get("reservedRooms", []) or []
        day_announcements = announcements.get(date_key, []) or []

        # Determine weekday 0..6
        try:
            dt = datetime.strptime(date_key, "%Y-%m-%d")
            w_idx = str(dt.weekday())
        except Exception:
            w_idx = "-1"

        regular_day_timetable = tt_days.get(w_idx, {}).get("periods", {})

        # Find specific changes for target class
        changes_list = []
        for period_idx, cell in enumerate(c3a_changes):
            p_num = period_idx + 1
            p_label, p_time = PERIOD_TIMES[period_idx]
            reg_lesson = regular_day_timetable.get(str(p_num))
            reg_lesson_formatted = format_regular_lesson(reg_lesson)

            if cell is not None:
                text = cell.get("text", "").strip()
                bg = cell.get("backgroundColor", "")
                fg = cell.get("foregroundColor", "")

                # Detect type of change
                change_type = "info"
                lower_text = text.lower()
                if "odpadá" in lower_text:
                    change_type = "cancelled"
                elif "exkurze" in lower_text or "akce" in lower_text:
                    change_type = "event"
                elif "spoj" in lower_text:
                    change_type = "merged"
                else:
                    change_type = "substitute"

                changes_list.append({
                    "period_index": p_num,
                    "period_label": p_label,
                    "period_time": p_time,
                    "regular_lesson": reg_lesson,
                    "regular_formatted": reg_lesson_formatted,
                    "raw_text": text,
                    "clean_text": " ".join(text.split()),
                    "bg_color": bg,
                    "fg_color": fg,
                    "type": change_type
                })

        # Check if target class is mentioned in takes_place
        class_pattern = rf"\b{re.escape(target_class)}\b"
        class_actions = []
        other_actions = []

        if takes_place:
            for line in takes_place.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if re.search(class_pattern, line, re.IGNORECASE):
                    class_actions.append(line)
                else:
                    other_actions.append(line)

        has_changes = len(changes_list) > 0 or len(class_actions) > 0

        # Build state hash to detect modifications
        state_repr = json.dumps({
            "in_work": in_work,
            "changes": changes_list,
            "class_actions": class_actions
        }, sort_keys=True)
        day_hash = hashlib.md5(state_repr.encode("utf-8")).hexdigest()

        # Build complete 10-periods grid with regular lesson info
        periods_grid = []
        for idx in range(10):
            p_num = idx + 1
            reg_lesson = regular_day_timetable.get(str(p_num))
            change_obj = next((c for c in changes_list if c["period_index"] == p_num), None)

            periods_grid.append({
                "period": p_num,
                "label": PERIOD_TIMES[idx][0],
                "time": PERIOD_TIMES[idx][1],
                "regular": reg_lesson,
                "regular_formatted": format_regular_lesson(reg_lesson),
                "change": change_obj
            })

        parsed_days.append({
            "date": date_key,
            "formatted_date": format_czech_date(date_key),
            "in_work": in_work,
            "has_changes": has_changes,
            "changes": changes_list,
            "class_actions": class_actions,
            "all_actions": other_actions,
            "full_takes_place": takes_place,
            "absence": absence,
            "announcements": day_announcements,
            "day_hash": day_hash,
            "periods_grid": periods_grid
        })

    return {
        "status": status,
        "target_class": target_class,
        "subjects": subjects_map,
        "last_checked": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "days": parsed_days
    }


def create_discord_payload(day_info, target_class="C3a", is_test=False):
    date_str = day_info["formatted_date"]
    in_work = day_info["in_work"]
    has_changes = day_info["has_changes"]
    changes = day_info["changes"]
    class_actions = day_info["class_actions"]

    if not has_changes:
        color = 0x2ECC71  # Green
        status_text = "Žádné suplování 🎉"
    elif in_work:
        color = 0xF39C12  # Orange
        status_text = "⚠️ Rozvrh v přípravě (předběžný)"
    else:
        color = 0x3498DB  # Blue
        status_text = "Definitivní rozvrh suplování"

    test_prefix = "🧪 [TEST] " if is_test else ""
    title = f"{test_prefix}Suplování {target_class} – {date_str}"

    description_parts = []
    if in_work:
        description_parts.append("*(Tento rozvrh je vedením školy označen jako „příprava“, může se ještě změnit.)*")

    fields = []

    # Format class specific events/excursions
    if class_actions:
        actions_formatted = "\n".join([f"🚩 **{act}**" for act in class_actions])
        fields.append({
            "name": "📌 Mimořádné akce a exkurze třídy",
            "value": actions_formatted,
            "inline": False
        })

    # Format period changes comparing with regular timetable
    if changes:
        changes_lines = []
        for ch in changes:
            p_num = ch["period_index"]
            p_time = ch["period_time"]
            new_text = ch["clean_text"]
            orig_text = ch.get("regular_formatted")

            orig_str = f" *(původně: {orig_text})*" if orig_text else ""

            if ch["type"] == "cancelled":
                icon = "🔴"
                changes_lines.append(f"{icon} **{p_num}. hod** ({p_time}):{orig_str} ➡️ **ODPADÁ**")
            elif ch["type"] == "event":
                icon = "🚩"
                changes_lines.append(f"{icon} **{p_num}. hod** ({p_time}): `{new_text}`")
            else:
                icon = "🟡"
                changes_lines.append(f"{icon} **{p_num}. hod** ({p_time}):{orig_str} ➡️ **{new_text}**")

        fields.append({
            "name": f"⚡ Změny v hodinách ({len(changes)})",
            "value": "\n".join(changes_lines),
            "inline": False
        })
    elif not class_actions:
        fields.append({
            "name": " Rozvrh bez změn",
            "value": "Třída se učí podle běžného stálého rozvrhu hodin.",
            "inline": False
        })

    # Absences summary if any
    absences = day_info.get("absence", [])
    if absences:
        abs_names = []
        for ab in absences[:5]:
            t_name = ab.get("teacher") or ab.get("teacherCode") or "Učitel"
            t_type = ab.get("type", "")
            if t_type == "wholeDay":
                abs_names.append(f"{t_name} (celý den)")
            elif t_type == "exkurze":
                abs_names.append(f"{t_name} (exkurze)")
            else:
                abs_names.append(f"{t_name}")
        abs_val = ", ".join(abs_names)
        if len(absences) > 5:
            abs_val += f" a dalších {len(absences) - 5}"
        fields.append({
            "name": "📋 Chybějící vyučující (výběr)",
            "value": abs_val,
            "inline": False
        })

    embed = {
        "title": title,
        "description": "\n\n".join(description_parts) if description_parts else None,
        "color": color,
        "fields": fields,
        "footer": {
            "text": f"SPŠE Ječná • {status_text} • Kontrolováno {datetime.now().strftime('%H:%M')}"
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }

    if not embed["description"]:
        del embed["description"]

    return {
        "username": f"Ječná Supl – {target_class}",
        "avatar_url": "https://raw.githubusercontent.com/mark/jecna-icons/main/jecna.png",
        "embeds": [embed]
    }


def send_discord_webhook(webhook_url, payload):
    if not webhook_url or not webhook_url.startswith("http"):
        return False, "Není nastavena platná Discord Webhook URL"

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "JecnaSuplNotifier/1.0"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 204):
                return True, "Odesláno úspěšně"
            return False, f"Discord vrátil stavový kód: {resp.status}"
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return False, f"Chyba Discord HTTP {e.code}: {err_msg}"
    except Exception as e:
        return False, f"Chyba při odesílání na Discord: {str(e)}"


def check_and_notify_changes(force_notify=False):
    cfg = load_config()
    webhook_url = cfg.get("discord_webhook_url", "").strip()
    target_class = cfg.get("target_class", "C3a")
    notify_on_in_work = cfg.get("notify_on_in_work", True)
    last_hashes = cfg.get("last_sent_hashes", {})

    raw_data = fetch_raw_api_data()
    parsed = parse_schedule_for_class(raw_data, target_class=target_class)

    sent_count = 0
    notifications_log = []

    for day in parsed["days"]:
        date_key = day["date"]
        day_hash = day["day_hash"]
        in_work = day["in_work"]
        has_changes = day["has_changes"]

        should_notify_day = has_changes and (notify_on_in_work or not in_work)
        is_new_or_changed = (date_key not in last_hashes) or (last_hashes[date_key] != day_hash)

        if (is_new_or_changed and should_notify_day) or force_notify:
            if webhook_url:
                payload = create_discord_payload(day, target_class=target_class, is_test=force_notify)
                ok, msg = send_discord_webhook(webhook_url, payload)
                if ok:
                    last_hashes[date_key] = day_hash
                    sent_count += 1
                    notifications_log.append(f"{date_key}: Odesláno ({msg})")
                else:
                    notifications_log.append(f"{date_key}: Chyba odeslání ({msg})")
            else:
                notifications_log.append(f"{date_key}: Zjištěna změna, ale chybí Discord Webhook URL")
                last_hashes[date_key] = day_hash

    cfg["last_sent_hashes"] = last_hashes
    save_config(cfg)

    return {
        "sent_count": sent_count,
        "logs": notifications_log,
        "parsed_data": parsed
    }


if __name__ == "__main__":
    import sys
    print("Spouštím kontrolu suplování pro C3a...")
    res = check_and_notify_changes(force_notify="--force" in sys.argv)
    print(f"Výsledek: odesláno {res['sent_count']} notifikací.")
    for l in res["logs"]:
        print(f" - {l}")
