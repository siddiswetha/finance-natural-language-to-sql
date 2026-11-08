#!/usr/bin/env python3
"""Build the synthetic finance SQLite database from the CSVs in this folder.

All data is SYNTHETIC and invented for learning and evaluation. It does not
describe any real company, vendor, person, or transaction.

Usage:
    python3 data/build_db.py [--db PATH] [--data-dir PATH]

Default database path: data/finance.db (next to this script's folder).
The script is idempotent: it drops and recreates the four tables each run.
Only the Python standard library is used.
"""

import argparse
import csv
import os
import sqlite3

SCHEMA = """
CREATE TABLE departments (
    id INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL,
    cost_center TEXT NOT NULL,
    budget_owner TEXT NOT NULL,
    annual_budget REAL NOT NULL
);

CREATE TABLE vendors (
    id INTEGER PRIMARY KEY,
    vendor_name TEXT NOT NULL,
    vendor_type TEXT NOT NULL,
    country TEXT NOT NULL,
    active INTEGER NOT NULL
);

CREATE TABLE transactions (
    id INTEGER PRIMARY KEY,
    transaction_date TEXT NOT NULL,
    vendor_id INTEGER NOT NULL REFERENCES vendors(id),
    department_id INTEGER NOT NULL REFERENCES departments(id),
    category TEXT NOT NULL,
    description TEXT NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    status TEXT NOT NULL,
    payment_method TEXT NOT NULL
);

CREATE TABLE monthly_close (
    id INTEGER PRIMARY KEY,
    close_month TEXT NOT NULL,
    department_id INTEGER NOT NULL REFERENCES departments(id),
    total_spend REAL NOT NULL,
    total_transactions INTEGER NOT NULL,
    close_status TEXT NOT NULL
);
"""

# (csv file, table, columns in csv order)
TABLES = [
    ("departments.csv", "departments",
     ["id", "department_name", "cost_center", "budget_owner", "annual_budget"]),
    ("vendors.csv", "vendors",
     ["id", "vendor_name", "vendor_type", "country", "active"]),
    ("transactions.csv", "transactions",
     ["id", "transaction_date", "vendor_id", "department_id", "category",
      "description", "amount", "currency", "status", "payment_method"]),
    ("monthly_close.csv", "monthly_close",
     ["id", "close_month", "department_id", "total_spend",
      "total_transactions", "close_status"]),
]


def build(db_path, data_dir):
    if os.path.exists(db_path):
        os.remove(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for csv_name, table, columns in TABLES:
            csv_path = os.path.join(data_dir, csv_name)
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = [tuple(row[c] for c in columns) for row in reader]
            placeholders = ", ".join("?" for _ in columns)
            conn.executemany(
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({placeholders})",
                rows,
            )
            print(f"Loaded {len(rows)} rows into {table} from {csv_name}")
        conn.commit()
        for table in ("departments", "vendors", "transactions", "monthly_close"):
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count} rows")
    finally:
        conn.close()
    print(f"Built synthetic database at {db_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=None,
                        help="Output SQLite path (default: data/finance.db)")
    parser.add_argument("--data-dir", default=None,
                        help="Folder holding the CSVs (default: this folder)")
    args = parser.parse_args()
    data_dir = args.data_dir or os.path.dirname(os.path.abspath(__file__))
    db_path = args.db or os.path.join(data_dir, "finance.db")
    build(db_path, data_dir)


if __name__ == "__main__":
    main()
