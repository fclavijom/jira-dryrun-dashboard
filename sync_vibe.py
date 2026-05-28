#!/usr/bin/env python3
"""
Sync Jira DryRun-DQOT tickets to the Vibe app testkeeper-dryrun-dashboard.
Fetches tickets from T3 Jira REST API, computes SLA, rebuilds and deploys.
"""
import subprocess
import json
import math
import sys
from datetime import datetime, timezone

JIRA_BASE = "https://t3.uberinternal.com"
JQL = 'project = TESTKEEPER AND labels = "DryRun-DQOT" ORDER BY created DESC'
SLUG = "testkeeper-dryrun-dashboard"
SLA_DAYS = 14
FR_DAYS = 7

MANAGER_MAP = {
    "achari@ext.uber.com": "Other",
    "alejandro.torres@uber.com": "Lynda Estrada",
    "ana.santos@uber.com": "Gessica Rodrigues",
    "anabelf@uber.com": "Fabiola Clavijo",
    "ar54@ext.uber.com": "Other",
    "ariel.sanhueza@uber.com": "Fabiola Clavijo",
    "carla.aguiar@uber.com": "Lynda Estrada",
    "dchakr11@ext.uber.com": "Other",
    "dchimi@ext.uber.com": "Other",
    "diego.riveros@uber.com": "Lynda Estrada",
    "edu.robledo@uber.com": "Lynda Estrada",
    "eramya@ext.uber.com": "Shiva Shanker Pokala",
    "fabi.clavijo@uber.com": "Other",
    "gmitta2@ext.uber.com": "Other",
    "ivan.zubiate@uber.com": "Lynda Estrada",
    "jeiker.mata@uber.com": "Gessica Rodrigues",
    "kpedda1@ext.uber.com": "Other",
    "leopc@uber.com": "Other",
    "lgarre1@ext.uber.com": "Shiva Shanker Pokala",
    "lizeth.alvarado@uber.com": "Lynda Estrada",
    "luka.fialho@uber.com": "Yik Ran Au Yong",
    "nbhavana@uber.com": "Other",
    "patricia.islas@uber.com": "Gessica Rodrigues",
    "pdawar3@ext.uber.com": "Other",
    "pega@ext.uber.com": "Other",
    "rodrigo.madariaga@uber.com": "Lynda Estrada",
    "sbanal@ext.uber.com": "Other",
    "schhot@ext.uber.com": "Other",
    "spokal1@ext.uber.com": "Shiva Shanker Pokala",
    "sshaik70@ext.uber.com": "Other",
    "tchait1@ext.uber.com": "Shiva Shanker Pokala",
    "vasugi.durai@uber.com": "Yik Ran Au Yong",
    "vdonga@ext.uber.com": "Other",
    "vmalla@ext.uber.com": "Shiva Shanker Pokala",
    "wquintanilha@uber.com": "Gessica Rodrigues",
}


def get_token():
    result = subprocess.run(
        ["usso", "-print", "-ussh", "t3.uberinternal.com"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def jira_get(token, path):
    result = subprocess.run(
        ["curl", "-s", "-H", f"Authorization: Bearer {token}",
         f"{JIRA_BASE}{path}"],
        capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def fetch_all_tickets(token):
    tickets = []
    start = 0
    page_size = 100
    while True:
        fields = "summary,assignee,status,priority,issuetype,created,updated"
        jql_enc = JQL.replace(' ', '%20').replace('"', '%22')
        path = (f"/rest/api/2/search?jql={jql_enc}"
                f"&maxResults={page_size}&startAt={start}&fields={fields}")
        data = jira_get(token, path)
        issues = data.get("issues", [])
        tickets.extend(issues)
        print(f"  Fetched {len(tickets)}/{data.get('total', '?')} tickets")
        if len(tickets) >= data.get("total", 0) or not issues:
            break
        start += page_size
    return tickets


def get_in_progress_since(token, issue_key):
    """Fetch changelog for a ticket and find when it first moved to In Progress."""
    data = jira_get(token, f"/rest/api/2/issue/{issue_key}?expand=changelog&fields=status")
    histories = data.get("changelog", {}).get("histories", [])
    for history in sorted(histories, key=lambda h: h.get("created", "")):
        for item in history.get("items", []):
            if item.get("field") == "status" and item.get("toString") == "In Progress":
                ts = history["created"]
                # Remove timezone suffix for consistency with existing format
                return ts[:19].replace("T", "T")
    return None


def parse_dt(ts):
    if not ts:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            dt = datetime.strptime(ts, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def compute_sla(created, in_progress_since, status_category):
    now = datetime.now(timezone.utc)
    ip = parse_dt(in_progress_since)
    cr = parse_dt(created)

    if not ip or status_category == "To Do":
        return {
            "slaStatus": "not_started", "slaDays": SLA_DAYS, "slaElapsed": None,
            "frStatus": "not_started", "frDays": FR_DAYS, "frElapsed": None,
        }

    sla_elapsed = (now - ip).days
    fr_elapsed = max(0, (ip - cr).days) if cr else None

    if sla_elapsed > SLA_DAYS:
        sla_status = "breached"
    elif sla_elapsed > math.floor(SLA_DAYS * 0.7):
        sla_status = "at_risk"
    else:
        sla_status = "on_track"

    if fr_elapsed is None:
        fr_status = "not_started"
    elif fr_elapsed > FR_DAYS:
        fr_status = "completed_late"
    else:
        fr_status = "completed_on_time"

    return {
        "slaStatus": sla_status, "slaDays": SLA_DAYS, "slaElapsed": sla_elapsed,
        "frStatus": fr_status, "frDays": FR_DAYS, "frElapsed": fr_elapsed,
    }


def build_ticket(raw, token, in_progress_cache):
    f = raw["fields"]
    key = raw["key"]
    assignee = f.get("assignee") or {}
    status = f.get("status") or {}
    status_cat = (status.get("statusCategory") or {}).get("name", "")
    email = assignee.get("emailAddress", "")

    in_progress_since = None
    if status_cat not in ("To Do", "Done"):
        if key not in in_progress_cache:
            in_progress_cache[key] = get_in_progress_since(token, key)
        in_progress_since = in_progress_cache[key]
    elif status_cat == "Done":
        # For Done tickets, try to get inProgressSince from cache or skip
        if key in in_progress_cache:
            in_progress_since = in_progress_cache[key]

    sla = compute_sla(f.get("created"), in_progress_since, status_cat)

    return {
        "key": key,
        "summary": f.get("summary", ""),
        "url": f"{JIRA_BASE}/browse/{key}",
        "assignee": assignee.get("displayName") or None,
        "assigneeEmail": email or None,
        "status": status.get("name", ""),
        "statusCategory": status_cat,
        "priority": (f.get("priority") or {}).get("name", ""),
        "issuetype": (f.get("issuetype") or {}).get("name", ""),
        "manager": MANAGER_MAP.get(email, "Other"),
        "created": f.get("created", ""),
        "updated": f.get("updated", ""),
        "inProgressSince": in_progress_since,
        **sla,
    }


def count_open_bugs(token):
    """Fetch open bug count separately — bugs span multiple projects."""
    import urllib.parse
    bug_jql = urllib.parse.quote('labels = "DryRun-DQOT" AND status = Open AND issuetype = Bug')
    data = jira_get(token, f"/rest/api/2/search?jql={bug_jql}&maxResults=1&fields=summary")
    return data.get("total", 0)


def generate_data_ts(tickets, last_synced, bugs_open):
    interface = """export interface Ticket {
  key: string;
  summary: string;
  url: string;
  assignee: string | null;
  assigneeEmail: string | null;
  status: string;
  statusCategory: string;
  priority: string;
  issuetype: string;
  manager: string;
  created: string;
  updated: string;
  inProgressSince: string | null;
  slaStatus: string;
  slaDays: number | null;
  slaElapsed: number | null;
  frStatus: string;
  frDays: number | null;
  frElapsed: number | null;
}"""
    bugs_open = bugs_open  # passed as parameter
    tickets_json = json.dumps(tickets, ensure_ascii=False)
    return (
        f'export const BUGS_OPEN_COUNT = {bugs_open};\n\n'
        f'export const LAST_SYNCED = "{last_synced}";\n'
        f'export const SOURCE = "T3 Jira REST API — JQL exacto";\n\n'
        f'{interface}\n\n'
        f'export const TICKETS: Ticket[] = {tickets_json};\n'
    )


def main():
    print("=== Vibe Sync: testkeeper-dryrun-dashboard ===")

    print("1. Getting auth token...")
    token = get_token()
    print(f"   Token OK ({len(token)} chars)")

    print("2. Fetching tickets from Jira...")
    raw_tickets = fetch_all_tickets(token)
    print(f"   Got {len(raw_tickets)} tickets")

    print("3. Building ticket records + SLA...")
    in_progress_cache = {}
    tickets = []
    for i, raw in enumerate(raw_tickets):
        t = build_ticket(raw, token, in_progress_cache)
        tickets.append(t)
        if (i + 1) % 50 == 0:
            print(f"   Processed {i+1}/{len(raw_tickets)}")
    print(f"   Done. {sum(1 for t in tickets if t['inProgressSince'])} tickets with inProgressSince")

    print("4. Generating data.ts...")
    last_synced = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    bugs_open = count_open_bugs(token)
    data_ts = generate_data_ts(tickets, last_synced, bugs_open)
    print(f"   data.ts: {len(data_ts):,} chars, {len(tickets)} tickets, {bugs_open} open bugs")

    print("5. Deploying to Vibe...")
    # Write both App.tsx (unchanged) and updated data.ts via vibe-mcp
    import subprocess as sp

    def vibe_call(tool, args):
        r = sp.run(
            ["aifx", "mcp", "call", "vibe-mcp", tool, "--args", json.dumps(args)],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            print(f"   ERROR calling {tool}: {r.stderr[:200]}")
            return None
        try:
            return json.loads(r.stdout) if r.stdout.strip() else {}
        except json.JSONDecodeError:
            return {"raw": r.stdout.strip()}

    with open("/tmp/vibe_app.json") as f:
        app_data = json.load(f)
    sf = app_data.get("src_files", {})

    # Write data.ts
    print("   Writing data.ts...")
    vibe_call("write_vibe_file", {"slug": SLUG, "path": "data.ts", "content": data_ts})

    # Write App.tsx (unchanged - preserve current)
    print("   Writing App.tsx...")
    vibe_call("write_vibe_file", {"slug": SLUG, "path": "App.tsx", "content": sf.get("App.tsx", "")})

    # Write src files
    if "src/App.tsx" in sf:
        vibe_call("write_vibe_file", {"slug": SLUG, "path": "src/App.tsx", "content": sf["src/App.tsx"]})
    if "src/index.tsx" in sf:
        vibe_call("write_vibe_file", {"slug": SLUG, "path": "src/index.tsx", "content": sf["src/index.tsx"]})

    # Build
    print("   Building app...")
    build_result = vibe_call("build_vibe_app", {"slug": SLUG})
    if build_result and build_result.get("error"):
        print(f"   BUILD ERROR: {build_result['error']}")
        sys.exit(1)
    print("   Build OK")

    # Promote to production
    print("   Promoting to production...")
    promote_result = vibe_call("promote_staging", {"slug": SLUG})
    if promote_result:
        print(f"   Promoted → version {promote_result.get('version', '?')}")

    print(f"\n=== DONE ===")
    print(f"Last synced: {last_synced}")
    print(f"Tickets: {len(tickets)} | Bugs open: {bugs_open}")
    print(f"URL: https://vibe-mcp.uberinternal.com/v/{SLUG}/")


if __name__ == "__main__":
    main()
