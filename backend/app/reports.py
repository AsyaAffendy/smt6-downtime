import csv
import io
import re
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from . import config, db
from .util import duration_seconds, now


def day_start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=config.PLANT_TZ)


async def search(machine=None, date_from=None, date_to=None, q=None, state=None, category=None):
    """Date filters apply to the DOWN time, in the plant's time zone (both days inclusive)."""
    query = {}
    if machine:
        query["machine_id"] = machine
    if state:
        query["state"] = state
    window = {}
    if date_from:
        window["$gte"] = day_start(date_from)
    if date_to:
        window["$lt"] = day_start(date_to + timedelta(days=1))
    if window:
        query["started_at"] = window
    events = await db.db.downtime_events.find(query).sort("started_at", -1).to_list(None)
    if category:
        events = [e for e in events if any(p["category"] == category for p in e["problems"])]
    if q and q.strip():
        pattern = re.compile(re.escape(q.strip()), re.I)

        def match(e):
            texts = [e["event_no"]]
            for p in e["problems"]:
                texts += [p["description"], p["root_cause"], p["category"]]
                texts += [a["description"] for a in p["actions"]]
                texts += [f"{x['part_name']} {x['part_number']} {x['donor_machine']}" for x in p["parts"]]
            return any(pattern.search(t) for t in texts)

        events = [e for e in events if match(e)]
    return events


def summarise(events):
    at = now()
    machines = {m: {"machine_id": m, "breakdowns": 0, "total_seconds": 0} for m in config.MACHINE_IDS}
    categories = Counter()
    techs = defaultdict(lambda: {"visits": 0, "events": set(), "seconds": 0})
    responses = []
    for e in events:
        row = machines[e["machine_id"]]
        row["breakdowns"] += 1
        row["total_seconds"] += duration_seconds(e, at)
        categories.update(p["category"] for p in e["problems"])
        if e["attendance"]:
            responses.append((min(a["arrived_at"] for a in e["attendance"]) - e["started_at"]).total_seconds())
        for a in e["attendance"]:
            t = techs[a["technician_name"]]
            t["visits"] += 1
            t["events"].add(e["_id"])
            t["seconds"] += max(0, int(((a["left_at"] or at) - a["arrived_at"]).total_seconds()))
    for row in machines.values():
        row["average_seconds"] = row["total_seconds"] // row["breakdowns"] if row["breakdowns"] else 0
    total = sum(r["total_seconds"] for r in machines.values())
    return {
        "breakdowns": len(events), "open": sum(e["state"] == "OPEN" for e in events),
        "total_seconds": total, "average_seconds": total // len(events) if events else 0,
        "average_response_seconds": int(sum(responses) / len(responses)) if responses else None,
        "by_machine": list(machines.values()),
        "problems_by_category": [{"category": c, "count": n} for c, n in categories.most_common()],
        "technicians": sorted(({"name": k, "visits": v["visits"], "events": len(v["events"]), "seconds": v["seconds"]}
                               for k, v in techs.items()), key=lambda r: -r["seconds"]),
    }


def local(t):
    return t.astimezone(config.PLANT_TZ).strftime("%Y-%m-%d %H:%M:%S") if t else ""


def safe(value):
    """Stop spreadsheet programs from running user text as a formula."""
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, str):
        return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return value


def tables(events):
    at = now()
    head = {
        "Events": ["Event No", "Machine", "State", "Down At", "Recovered At", "Duration (min)", "Problem Count",
                   "Problems", "Categories", "Root Causes", "Technicians", "Opened By", "Recovery Confirmed By",
                   "Recovery Note"],
        "Problems": ["Event No", "Machine", "Description", "Category", "Root Cause", "Status", "Created At",
                     "Created By", "Updated At", "Updated By"],
        "Actions": ["Event No", "Machine", "Problem", "Type", "Action", "At", "By"],
        "Parts": ["Event No", "Machine", "Problem", "Part Name", "Part Number", "Qty", "Source", "Donor Machine",
                  "Donor Details", "At", "By"],
        "Attendance": ["Event No", "Machine", "Technician", "Arrived", "Left", "Minutes", "Auto Check-out", "Note"],
    }
    rows = {k: [] for k in head}
    for e in events:
        key = [e["event_no"], e["machine_id"]]
        ps = e["problems"]
        rows["Events"].append(key + [
            e["state"], local(e["started_at"]), local(e["recovered_at"]), round(duration_seconds(e, at) / 60, 1),
            len(ps), " | ".join(p["description"] for p in ps), " | ".join(p["category"] for p in ps),
            " | ".join(p["root_cause"] or "(not recorded)" for p in ps),
            ", ".join(dict.fromkeys(a["technician_name"] for a in e["attendance"])), e["created_by"]["name"],
            e["recovery"]["confirmed_by"]["name"] if e["recovery"] else "",
            e["recovery"]["note"] if e["recovery"] else ""])
        for p in ps:
            rows["Problems"].append(key + [p["description"], p["category"], p["root_cause"], p["status"],
                                           local(p["created_at"]), p["created_by"]["name"],
                                           local(p["updated_at"]), p["updated_by"]["name"]])
            for a in p["actions"]:
                rows["Actions"].append(key + [p["description"], a["type"], a["description"], local(a["at"]), a["by"]["name"]])
            for x in p["parts"]:
                rows["Parts"].append(key + [p["description"], x["part_name"], x["part_number"], x["quantity"], x["source"],
                                            x["donor_machine"], x["donor_details"], local(x["at"]), x["by"]["name"]])
        for a in e["attendance"]:
            rows["Attendance"].append(key + [a["technician_name"], local(a["arrived_at"]), local(a["left_at"]),
                                             round(((a["left_at"] or at) - a["arrived_at"]).total_seconds() / 60, 1),
                                             "Yes" if a["auto_checkout"] else "No", a["note"]])
    return head, {k: [[safe(c) for c in r] for r in v] for k, v in rows.items()}


def to_csv(events) -> bytes:
    head, rows = tables(events)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(head["Events"])
    writer.writerows(rows["Events"])
    return buffer.getvalue().encode("utf-8-sig")


def to_xlsx(events) -> bytes:
    head, rows = tables(events)
    wb = Workbook()
    wb.remove(wb.active)
    for name, columns in head.items():
        ws = wb.create_sheet(name)
        ws.append(columns)
        for row in rows[name]:
            ws.append(row)
        for i, column in enumerate(columns, 1):
            cell = ws.cell(1, i)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1E293B")
            longest = max([len(column)] + [len(str(r[i - 1])) for r in rows[name]])
            ws.column_dimensions[get_column_letter(i)].width = min(max(longest + 2, 12), 60)
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = ws.dimensions
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
