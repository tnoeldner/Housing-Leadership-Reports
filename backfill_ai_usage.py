"""
Bulk insert Gemini billing daily rollups into Supabase ai_usage_logs.

Usage:
    python backfill_ai_usage.py path/to/gemini_daily_rollup.csv
    python backfill_ai_usage.py --bq-table project.dataset.table [--start YYYY-MM-DD] [--end YYYY-MM-DD]

CSV expected columns: usage_date, cost_usd
BigQuery table is expected to expose columns usage_date (DATE) and cost_usd (FLOAT)
Env vars required: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
Optional for BigQuery: GOOGLE_APPLICATION_CREDENTIALS or default ADC
"""
import argparse
import csv
import os
import sys
from typing import List, Dict, Optional

from supabase import create_client

try:
    from google.cloud import bigquery
except Exception:
    bigquery = None

BATCH_SIZE = 500


def load_env() -> Dict[str, str]:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment.")
    return {"url": url, "key": key}


def format_rows(raw_rows: List[Dict]) -> List[Dict]:
    formatted: List[Dict] = []
    for r in raw_rows:
        usage_date = r.get("usage_date")
        cost_usd = r.get("cost_usd")
        if not usage_date or cost_usd is None:
            continue
        # Normalize date to string
        if hasattr(usage_date, "isoformat"):
            usage_date = usage_date.isoformat()
        try:
            cost_val = float(cost_usd)
        except (TypeError, ValueError):
            continue
        formatted.append({
            "model": "gemini_billing_export",
            "prompt_tokens": None,
            "response_tokens": None,
            "total_tokens": None,
            "cost_usd": cost_val,
            "context": "backfill_bigquery_standard",
            "created_at": f"{usage_date}T00:00:00Z",
        })
    return formatted


def load_rows_from_csv(csv_path: str) -> List[Dict]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return format_rows(list(reader))


def load_rows_from_bigquery(table: str, start: Optional[str], end: Optional[str]) -> List[Dict]:
    """
    Pull daily cost from a GCP billing export (detailed) table.
    Assumes columns: cost (FLOAT) and usage_start_time (TIMESTAMP). Falls back to export_time if usage_start_time is absent.
    """
    if bigquery is None:
        raise SystemExit("google-cloud-bigquery is not installed. pip install google-cloud-bigquery")

    client = bigquery.Client()
    params = []
    where_clauses = []
    if start:
        where_clauses.append("usage_day >= @start")
        params.append(bigquery.ScalarQueryParameter("start", "DATE", start))
    if end:
        where_clauses.append("usage_day <= @end")
        params.append(bigquery.ScalarQueryParameter("end", "DATE", end))
    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    query = f"""
        WITH base AS (
            SELECT
                CASE
                    WHEN TRUE THEN DATE(usage_start_time)
                END AS usage_day,
                cost AS cost_usd
            FROM `{table}`
        )
        SELECT usage_day AS usage_date, SUM(cost_usd) AS cost_usd
        FROM base
        {where_sql}
        GROUP BY usage_day
        ORDER BY usage_day
    """

    job_config = bigquery.QueryJobConfig(query_parameters=params) if params else None
    rows = client.query(query, job_config=job_config).result()
    raw_rows = [dict(r) for r in rows]
    return format_rows(raw_rows)


def insert_rows(client, rows: List[Dict]):
    total = len(rows)
    for i in range(0, total, BATCH_SIZE):
        chunk = rows[i:i + BATCH_SIZE]
        client.table("ai_usage_logs").insert(chunk).execute()
        print(f"Inserted {len(chunk)} rows ({i + len(chunk)}/{total})")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill ai_usage_logs from CSV or BigQuery.")
    parser.add_argument("csv", nargs="?", help="Path to CSV with usage_date,cost_usd")
    parser.add_argument("--bq-table", dest="bq_table", help="BigQuery table in project.dataset.table form")
    parser.add_argument("--start", dest="start", help="Start date YYYY-MM-DD")
    parser.add_argument("--end", dest="end", help="End date YYYY-MM-DD")
    return parser.parse_args()


def main():
    args = parse_args()
    env = load_env()
    client = create_client(env["url"], env["key"])

    rows: List[Dict]
    if args.bq_table:
        rows = load_rows_from_bigquery(args.bq_table, args.start, args.end)
    else:
        if not args.csv:
            raise SystemExit("Provide a CSV path or --bq-table project.dataset.table")
        if not os.path.isfile(args.csv):
            raise SystemExit(f"CSV file not found: {args.csv}")
        rows = load_rows_from_csv(args.csv)

    if not rows:
        raise SystemExit("No valid rows found. Ensure columns usage_date and cost_usd exist.")

    insert_rows(client, rows)
    print("Done.")


if __name__ == "__main__":
    main()
