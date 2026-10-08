"""Check frontend/filter parity and report momentum coverage for every exported symbol."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.revenue_growth_momentum import calculate_revenue_growth_momentum
from test_revenue_growth_momentum import RevenueGrowthMomentumTests, scenarios


def assert_equal(actual, expected, path="result"):
    if isinstance(expected, dict):
        assert actual.keys() == expected.keys(), f"{path}: result keys differ"
        for key in expected:
            assert_equal(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        assert len(actual) == len(expected), f"{path}: lengths differ"
        for index, (left, right) in enumerate(zip(actual, expected)):
            assert_equal(left, right, f"{path}[{index}]")
    elif isinstance(expected, (int, float)):
        assert isinstance(actual, (int, float)) and math.isclose(actual, expected, abs_tol=1e-10, rel_tol=1e-12), f"{path}: {actual} != {expected}"
    else:
        assert actual == expected, f"{path}: {actual} != {expected}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stocks", type=Path, default=ROOT / "frontend/public/data/open-data/stocks.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path, help="Append coverage to the GitHub Actions step summary.")
    args = parser.parse_args()
    test_result = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromTestCase(RevenueGrowthMomentumTests))
    if not test_result.wasSuccessful():
        raise SystemExit(1)

    stocks = json.loads(args.stocks.read_text())
    cases = scenarios()
    inputs = [row for _, row, _ in cases] + stocks
    expected = [calculate_revenue_growth_momentum(row) for row in inputs]
    with tempfile.TemporaryDirectory(prefix="revenue-momentum-") as directory:
        temp = Path(directory)
        subprocess.run([
            str(ROOT / "frontend/node_modules/.bin/tsc"), str(ROOT / "frontend/src/revenueGrowthMomentum.ts"),
            "--outDir", directory, "--module", "commonjs", "--target", "ES2020", "--strict", "--skipLibCheck",
        ], check=True, cwd=ROOT)
        inputs_path = temp / "inputs.json"
        inputs_path.write_text(json.dumps(inputs))
        runner = temp / "validate.cjs"
        runner.write_text('''const { readFileSync } = require("node:fs");
const { calculateRevenueGrowthMomentum } = require("./revenueGrowthMomentum.js");
const rows = JSON.parse(readFileSync(process.argv[2], "utf8"));
for (const value of [NaN, Infinity, -Infinity]) {
  const snapshot = structuredClone(rows[0]);
  snapshot.historical_series.quarterly_revenue[5].metrics.revenue_growth_yoy.value = value;
  if (calculateRevenueGrowthMomentum(snapshot).label !== "Unclear") throw new Error("Nonfinite growth was calculated");
}
process.stdout.write(JSON.stringify(rows.map(calculateRevenueGrowthMomentum)));
''')
        actual = json.loads(subprocess.check_output(["node", str(runner), str(inputs_path)], text=True))
    for index, (left, right) in enumerate(zip(actual, expected)):
        name = cases[index][0] if index < len(cases) else stocks[index - len(cases)]["ticker"]
        assert_equal(left, right, name)
    assert len(actual) == len(expected), "Frontend returned incomplete results"

    results = [{"ticker": row["ticker"], **result} for row, result in zip(stocks, expected[len(cases):])]
    unavailable = [{"ticker": row["ticker"], "reason": row["reason"]} for row in results if row["label"] == "Unclear"]
    counts = dict(sorted(Counter(row["label"] for row in results).items()))
    report = {"symbol_count": len(stocks), "calculated_count": len(stocks) - len(unavailable),
              "scenario_count": len(cases), "frontend_filter_parity": "passed", "labels": counts,
              "unavailable": unavailable, "results": results}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    lines = [f"Revenue growth momentum: {report['calculated_count']}/{len(stocks)} symbols calculated; frontend/filter parity passed across {len(cases)} scenarios and all symbols.",
             f"Labels: {json.dumps(counts)}"]
    lines.extend(f"- {row['ticker']}: {row['reason']}" for row in unavailable)
    print("\n".join(lines))
    if args.summary:
        with args.summary.open("a") as handle:
            handle.write("\n### Revenue growth momentum\n\n" + "\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
