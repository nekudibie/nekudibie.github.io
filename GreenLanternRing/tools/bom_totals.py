#!/usr/bin/env python3
"""Sum shopping/uk_bom.csv into required / optional totals per section."""
import csv, collections
from pathlib import Path
rows = list(csv.DictReader(open(Path(__file__).resolve().parents[1] / "shopping" / "uk_bom.csv")))
tot = collections.defaultdict(lambda: [0.0, 0.0])
for r in rows:
    tot[r["section"]][0 if r["required"] == "Required" else 1] += float(r["total_gbp_est"])
print("| Section | Required (£, est.) | Optional (£, est.) |\n|---|---|---|")
for k in sorted(tot):
    print(f"| {k} | {tot[k][0]:.2f} | {tot[k][1]:.2f} |")
req = {k: v[0] for k, v in tot.items()}
print(f"\nBasic payment prototype (sections 2 only): £{req['2 Payment prototype']:.2f}")
print(f"NFC proof-of-concept (required only): £{req['1 NFC proof-of-concept']:.2f}")
fin = req['2 Payment prototype'] + req['3 Complete ring']
print(f"Finished ring, required items, filament & tools already owned: £{fin:.2f}")
