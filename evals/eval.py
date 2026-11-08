#!/usr/bin/env python3
"""Run the eval set in eval-set.csv against main.py's deterministic
translator, in auto-confirm mode (no human prompt during the eval run).

For each test case:
- Valid questions: PASS only if the generated SQL matches the expected SQL
  exactly (after normalising whitespace) AND the SQL passes validation
  AND it runs AND the extra row check in the rubric holds.
- Rejected questions: PASS only if the translator rejects the question
  with the expected reason (UNSAFE or UNKNOWN_SCHEMA) and nothing runs.

Results are written to eval-results.csv AND the `result` column of
eval-set.csv is updated in place with the true outcome of this run.
Nothing is invented: a test that fails is recorded as FAIL.

Usage:
    python3 evals/eval.py
    python3 main.py --eval
"""

import csv
import os
import re
import sqlite3
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from main import translate_question, validate_sql, ensure_db, DEFAULT_DB

EVALS_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_SET = os.path.join(EVALS_DIR, "eval-set.csv")
EVAL_RESULTS = os.path.join(EVALS_DIR, "eval-results.csv")


def normalise(sql):
    return " ".join(sql.strip().split())


def extra_row_check(test_id, columns, rows):
    """Rubric-specific row checks. Returns (ok, note)."""
    if test_id == "T02":
        return (len(rows) == 5, f"expected 5 rows, got {len(rows)}")
    if test_id == "T03":
        amount_idx = columns.index("amount")
        bad = [r for r in rows if not r[amount_idx] > 1000]
        return (len(bad) == 0 and len(rows) > 0,
                f"{len(rows)} rows, {len(bad)} with amount <= 1000")
    if test_id == "T04":
        count_idx = columns.index("transaction_count")
        total = sum(r[count_idx] for r in rows)
        return (total == 40, f"counts sum to {total}, expected 40")
    if test_id == "T05":
        return (len(rows) == 1, f"expected 1 row, got {len(rows)}")
    if test_id == "T08":
        # The query filters by department in SQL; re-check via the DB is
        # covered by the exact-SQL match. Here just require rows exist.
        return (len(rows) > 0, f"{len(rows)} rows returned")
    if test_id == "T10":
        return (len(rows) == 2, f"expected 2 flagged rows, got {len(rows)}")
    if test_id == "T11":
        return (len(rows) == 1, f"expected 1 row, got {len(rows)}")
    return (len(rows) >= 1, f"{len(rows)} rows returned")


def run_eval():
    ensure_db(DEFAULT_DB)
    with open(EVAL_SET, newline="", encoding="utf-8") as f:
        cases = list(csv.DictReader(f))

    conn = sqlite3.connect(DEFAULT_DB)
    results = []
    passed = 0
    try:
        for case in cases:
            test_id = case["test_id"]
            question = case["natural_language_question"]
            expected = case["expected_sql_or_outcome"].strip()
            sql, reason = translate_question(question)

            if expected.startswith("REJECTED:"):
                expected_reason = expected.split(":", 1)[1].strip()
                if sql is None and reason.startswith(expected_reason):
                    status, note = "PASS", f"rejected as {expected_reason}; nothing ran"
                elif sql is None:
                    status, note = "FAIL", f"rejected but reason was: {reason}"
                else:
                    status, note = "FAIL", f"NOT rejected — generated SQL: {sql}"
                actual = sql or ""
            else:
                if sql is None:
                    status, note, actual = "FAIL", f"rejected: {reason}", ""
                elif normalise(sql) != normalise(expected):
                    status, note = "FAIL", "SQL does not match expected SQL"
                    actual = sql
                else:
                    ok, message = validate_sql(sql, conn)
                    if not ok:
                        status, note, actual = "FAIL", message, sql
                    else:
                        try:
                            cursor = conn.execute(sql)
                            columns = [d[0] for d in cursor.description]
                            rows = cursor.fetchall()
                        except Exception as exc:  # noqa: BLE001 - report it
                            status, note, actual = (
                                "FAIL", f"SQL failed to run: {exc}", sql)
                        else:
                            row_ok, row_note = extra_row_check(
                                test_id, columns, rows)
                            if row_ok:
                                status, note = "PASS", (
                                    f"exact SQL match, validation passed, "
                                    f"ran OK ({row_note})")
                            else:
                                status, note = "FAIL", (
                                    f"exact SQL match but row check failed: "
                                    f"{row_note}")
                            actual = sql
            if status == "PASS":
                passed += 1
            print(f"{test_id}: {status} — {question} — {note}")
            results.append({
                "test_id": test_id,
                "natural_language_question": question,
                "expected_sql_or_outcome": expected,
                "actual_sql_or_reason": actual if sql is not None else reason,
                "result": status,
                "notes": note,
            })
    finally:
        conn.close()

    total = len(results)
    print(f"\nEval result: {passed}/{total} passed")
    if passed != total:
        failed = [r["test_id"] for r in results if r["result"] != "PASS"]
        print(f"Failed tests: {', '.join(failed)}")

    with open(EVAL_RESULTS, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["test_id", "natural_language_question",
                           "expected_sql_or_outcome", "actual_sql_or_reason",
                           "result", "notes"])
        writer.writeheader()
        writer.writerows(results)

    # Update the result column of eval-set.csv with the true outcomes.
    result_by_id = {r["test_id"]: r["result"] for r in results}
    with open(EVAL_SET, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        fieldnames = list(rows[0].keys()) if rows else []
    for row in rows:
        row["result"] = result_by_id.get(row["test_id"], "not run")
    with open(EVAL_SET, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {EVAL_RESULTS}")
    print(f"Updated result column in {EVAL_SET}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(run_eval())
