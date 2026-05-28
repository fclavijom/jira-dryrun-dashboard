#!/usr/bin/env python3
"""Processes pending Slack notification requests from Vibe Docstore queue."""
import json, subprocess

SLUG = "testkeeper-dryrun-dashboard"
COLLECTION = "notify-queue"


def vibe_call(tool, args):
    r = subprocess.run(
        ["aifx", "mcp", "call", "vibe-mcp", tool, "--args", json.dumps(args)],
        capture_output=True, text=True,
    )
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except Exception:
        return {}


def slack_lookup(email):
    r = subprocess.run(
        ["aifx", "mcp", "call", "slack-mcp", "slack_lookup_by_email",
         "--args", json.dumps({"email": email})],
        capture_output=True, text=True, timeout=15,
    )
    try:
        return json.loads(r.stdout).get("user", {}).get("id")
    except Exception:
        return None


def slack_send(channel_id, text):
    r = subprocess.run(
        ["aifx", "mcp", "call", "slack-mcp", "slack_send_message",
         "--args", json.dumps({"channel_id": channel_id, "text": text})],
        capture_output=True, text=True, timeout=20,
    )
    return r.returncode == 0


def process_notify_all(data):
    messages = data.get("messages", [])
    ok = 0
    for msg in messages:
        uid = slack_lookup(msg["email"])
        if uid and slack_send(uid, msg["text"]):
            ok += 1
    print(f"  notify-all: {ok}/{len(messages)} sent")


def process_notify_one(data):
    uid = slack_lookup(data["email"])
    if uid and slack_send(uid, data["text"]):
        print(f"  notify-one: sent to {data['name']}")
    else:
        print(f"  notify-one: failed for {data['name']}")


def process_notify_channel(data):
    if slack_send(data["channel_id"], data["text"]):
        print(f"  notify-channel: sent")
    else:
        print(f"  notify-channel: failed")


def main():
    result = vibe_call("db_list", {"slug": SLUG, "collection": COLLECTION, "limit": 50})
    docs = result.get("docs", []) if isinstance(result, dict) else []
    pending = [d for d in docs if d.get("doc_data", {}).get("status") == "pending"]

    if not pending:
        return

    print(f"Processing {len(pending)} pending notification(s)...")
    for doc in pending:
        doc_id = doc["doc_id"]
        data = doc.get("doc_data", {})
        ntype = data.get("type")

        vibe_call("db_set", {
            "slug": SLUG, "collection": COLLECTION, "doc_id": doc_id,
            "doc_data": {**data, "status": "processing"},
        })

        try:
            if ntype == "notify-all":
                process_notify_all(data)
            elif ntype == "notify-one":
                process_notify_one(data)
            elif ntype == "notify-channel":
                process_notify_channel(data)
            status = "done"
        except Exception as e:
            print(f"  error: {e}")
            status = "failed"

        vibe_call("db_set", {
            "slug": SLUG, "collection": COLLECTION, "doc_id": doc_id,
            "doc_data": {**data, "status": status},
        })


if __name__ == "__main__":
    main()
