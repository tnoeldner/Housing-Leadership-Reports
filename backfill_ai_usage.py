"""
Bulk insert Gemini billing daily rollups into Supabase ai_usage_logs.

Usage:
    python backfill_ai_usage.py path/to/gemini_daily_rollup.csv

CSV expected columns: usage_date, cost_usd
Env vars required: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import csv
import os
import sys
from typing import List, Dict

from supabase import create_client

BATCH_SIZE = 500


def load_env() -> Dict[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")
    return {"url": url, "key": key}


def load_rows(csv_path: str) -> List[Dict]:
    rows: List[Dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            usage_date = r.get("usage_date")
            cost_usd = r.get("cost_usd")
            if not usage_date or cost_usd is None:
                continue
            try:
                cost_val = float(cost_usd)
            except ValueError:
                continue
            rows.append({
                "model": "gemini_billing_export",
                "prompt_tokens": None,
                "response_tokens": None,
                "total_tokens": None,
                "cost_usd": cost_val,
                "context": "backfill_bigquery_standard",
                "created_at": f"{usage_date}T00:00:00Z",
            })
    return rows


def insert_rows(client, rows: List[Dict]):
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        chunk = rows[i:i + BATCH_SIZE]
        client.table("ai_usage_logs").insert(chunk).execute()
        print(f"Inserted {len(chunk)} rows ({i + len(chunk)}/{total})")


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python backfill_ai_usage.py path/to/gemini_daily_rollup.csv")
    csv_path = sys.argv[1]
    if not os.path.isfile(csv_path):
        raise SystemExit(f"CSV file not found: {csv_path}")

    env = load_env()
    client = create_client(env["url"], env["key"])
    rows = load_rows(csv_path)
    if not rows:
        raise SystemExit("No valid rows found in CSV. Ensure columns usage_date and cost_usd exist.")

    insert_rows(client, rows)
    print("Done.")


if __name__ == "__main__":
    main()
