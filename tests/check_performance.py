"""
tests/check_performance.py
──────────────────────────────────────────────────────────────────────────────
Parses the JMeter results CSV produced by:
    jmeter -n -t batches.jmx -l results.csv

Quality gates enforced:
  1. Error rate  — MUST be exactly 0.00 %
  2. Throughput  — MUST be ≥ MIN_THROUGHPUT_RPS (requests per second)

Exits with code 1 (fails the pipeline) on any violation.

Usage:
    python3 tests/check_performance.py results.csv
"""

import csv
import sys
import os

# ─── Tunable thresholds ───────────────────────────────────────────────────────
# Set this to the minimum acceptable requests-per-second your cluster must sustain.
# Derived from your previous stress-test baseline (3 pods × 2 workers → ~120 RPS).
MIN_THROUGHPUT_RPS: float = 80.0   # conservative lower-bound to catch regressions

# ─── Helpers ─────────────────────────────────────────────────────────────────

def parse_results(filepath: str) -> dict:
    """
    Reads the JMeter JTL/CSV file and returns aggregate statistics.

    JMeter CSV columns (default format):
      timeStamp, elapsed, label, responseCode, responseMessage,
      threadName, dataType, success, failureMessage, bytes,
      sentBytes, grpThreads, allThreads, URL, Latency, IdleTime, Connect
    """
    if not os.path.isfile(filepath):
        print(f"[FATAL] Results file not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    total       = 0
    errors      = 0
    total_ms    = 0
    start_ts    = None
    end_ts      = None

    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        # Validate that the expected columns are present
        required_cols = {"timeStamp", "elapsed", "success"}
        if not required_cols.issubset(set(reader.fieldnames or [])):
            print(
                f"[FATAL] Unexpected CSV format. "
                f"Required columns {required_cols} not found.\n"
                f"Actual columns: {reader.fieldnames}",
                file=sys.stderr,
            )
            sys.exit(1)

        for row in reader:
            total += 1
            total_ms += int(row["elapsed"])

            ts = int(row["timeStamp"])   # epoch ms
            if start_ts is None or ts < start_ts:
                start_ts = ts
            if end_ts is None or ts > end_ts:
                end_ts = ts

            if row["success"].strip().lower() != "true":
                errors += 1

    if total == 0:
        print("[FATAL] JMeter results file is empty — no samples found.", file=sys.stderr)
        sys.exit(1)

    duration_s    = (end_ts - start_ts) / 1000.0 if (end_ts and start_ts and end_ts > start_ts) else 1
    error_rate    = (errors / total) * 100.0
    throughput    = total / duration_s
    avg_latency   = total_ms / total

    return {
        "total_samples" : total,
        "errors"        : errors,
        "error_rate_pct": error_rate,
        "throughput_rps": throughput,
        "avg_latency_ms": avg_latency,
        "duration_s"    : duration_s,
    }


def evaluate(stats: dict) -> None:
    """Print a summary report and sys.exit(1) on any quality gate failure."""

    print("\n" + "=" * 60)
    print("  JMeter Performance Quality Gate Report")
    print("=" * 60)
    print(f"  Total samples  : {stats['total_samples']:,}")
    print(f"  Errors         : {stats['errors']:,}")
    print(f"  Error rate     : {stats['error_rate_pct']:.4f} %")
    print(f"  Throughput     : {stats['throughput_rps']:.2f} req/s")
    print(f"  Avg latency    : {stats['avg_latency_ms']:.1f} ms")
    print(f"  Test duration  : {stats['duration_s']:.1f} s")
    print("=" * 60)

    failures = []

    # ── Gate 1: Zero-error mandate ───────────────────────────────────────────
    if stats["error_rate_pct"] > 0.0:
        failures.append(
            f"  ❌ ERROR RATE {stats['error_rate_pct']:.4f}% > 0.00%  "
            f"({stats['errors']} failed samples)"
        )
    else:
        print("  ✅ Gate 1 PASSED — Error rate: 0.00%")

    # ── Gate 2: Minimum throughput ───────────────────────────────────────────
    if stats["throughput_rps"] < MIN_THROUGHPUT_RPS:
        failures.append(
            f"  ❌ THROUGHPUT {stats['throughput_rps']:.2f} RPS "
            f"< minimum {MIN_THROUGHPUT_RPS} RPS"
        )
    else:
        print(f"  ✅ Gate 2 PASSED — Throughput: {stats['throughput_rps']:.2f} RPS")

    print("=" * 60)

    if failures:
        print("\n[PIPELINE ABORTED] Performance quality gates FAILED:")
        for msg in failures:
            print(msg)
        print()
        sys.exit(1)

    print("\n🚀 All quality gates passed — proceeding to deployment.\n")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 tests/check_performance.py <results.csv>", file=sys.stderr)
        sys.exit(1)

    results_path = sys.argv[1]
    stats = parse_results(results_path)
    evaluate(stats)
