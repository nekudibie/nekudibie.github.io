#!/usr/bin/env python3
"""Weighted decision matrix for the payment architecture.
Scores 1 (worst) – 5 (best). For 'technical difficulty', 5 = easiest.
Edit the scores as evidence arrives and re-run:  python3 decision_matrix.py
Gate: an approach scoring 1 on 'activation' (no legitimate provisioning
path) cannot be selected regardless of total.
"""
W = {"Terminal compatibility": .25, "Activation & continued use": .20, "Cost": .20,
     "Ring size & comfort": .15, "Technical difficulty (5=easy)": .10, "Reliability & serviceability": .10}
S = {
 "A  Transplant chip from own card":                [2, 2, 5, 4, 2, 1],
 "B  OEM module (IDEMIA / Infineon / Tappy)":       [5, 1, 1, 4, 3, 4],
 "C  Dismantle a Curve-linked payment fob":         [4, 4, 4, 2, 3, 3],
 "D  Intact Curve-linked payment ring as core":     [4, 4, 3, 3, 5, 4],
 "E  Intact Curve-linked flat tag under emblem":    [3, 4, 4, 3, 3, 4],
}
rows = []
for k, s in S.items():
    tot = sum(w * x for w, x in zip(W.values(), s))
    gate = "BLOCKED (no provisioning path)" if s[1] == 1 else ""
    rows.append((tot, k, s, gate))
print("| Approach | " + " | ".join(f"{c} ({int(w*100)}%)" for c, w in W.items()) + " | Weighted /5 | Gate |")
print("|---|" + "---|" * (len(W) + 2))
for tot, k, s, gate in sorted(rows, reverse=True):
    print(f"| {k} | " + " | ".join(map(str, s)) + f" | **{tot:.2f}** | {gate} |")
