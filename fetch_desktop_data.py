from aw_client import ActivityWatchClient
from datetime import datetime, timedelta, timezone
import ollama
import sqlite3, json, uuid


conn = sqlite3.connect("tracker.db")
cursor = conn.cursor()

# Table 1: Unified timeline for everything
cursor.execute(""""
CREATE TABLE IF NOT EXISTS timeline_events (
    id TEXT PRIMARY KEY,
    source_app TEXT,
    event_category TEXT,
    start_time TEXT,
    duration_seconds REAL,
    title TEXT,
    metadata TEXT
) 
""")
client = ActivityWatchClient("my-test-script")

# Look at the last 4 hours (in UTC)
now = datetime.now(timezone.utc)
start_time = now - timedelta(hours=4)

# Locate both buckets in aw
buckets = client.get_buckets()
window_bucket_id = next(b for b in buckets.keys() if "aw-watcher-window" in b)
afk_bucket_id = next(b for b in buckets.keys() if "aw-watcher-afk" in b)

# Query the server to remove AFK time and merge repeated switches
query = f"""
window_events = query_bucket("{window_bucket_id}");
afk_events = query_bucket("{afk_bucket_id}");

not_afk = filter_keyvals(afk_events, "status", ["not-afk"]);
active_events = filter_period_intersect(window_events, not_afk);
merged_events = merge_events_by_keys(active_events, ["app", "title"]);
RETURN = sort_by_duration(merged_events);
"""

results = client.query(query, [(start_time, now)])
events = results[0]

# Collect meaningful activity (30+ seconds) into a text block
activity_lines = []

for event in events:
    duration_seconds = event["duration"]
    
    if duration_seconds < 30:
        continue

    app_name = event["data"].get("app", "Unknown App")
    window_title = event["data"].get("title", "Unknown Title")
    duration_minutes = round(duration_seconds / 60, 1)
    
    activity_lines.append(f"- App: {app_name} | Title: {window_title} | Time: {duration_minutes} mins")

logs_text = "\n".join(activity_lines)

# Send to Ollama if we have activity to summarize
if not logs_text:
    print("No activity longer than 30 seconds found in the last 4 hours.")
else:
    print("Cleaned Logs Sent to AI:\n" + logs_text)
    print("\nGenerating AI Summary...\n" + "=" * 40)

    response = ollama.chat(
        model="llama3.2",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a personal productivity assistant. Analyze the user's activity logs "
                    "and write a concise daily journal summary. Group their time into categories "
                    "(e.g., Coding, Studying, Entertainment, Admin), estimate time per category, "
                    "and write a short paragraph summarizing what they accomplished."
                )
            },
            {
                "role": "user",
                "content": f"Here are my active window logs for the last 4 hours:\n\n{logs_text}"
            }
        ]
    )

    print(response["message"]["content"])