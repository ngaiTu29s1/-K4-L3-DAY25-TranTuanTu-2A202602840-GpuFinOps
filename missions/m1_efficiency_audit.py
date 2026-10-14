"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "bw": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        a["bw"].append(num(r["achieved_bw_tbs"]))
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "achieved_bw_tbs": round(sum(a["bw"]) / len(a["bw"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # Extension 2: Right-sizing analysis according to MBU and VRAM/Bandwidth unit economics
    rightsizing_recs = []
    rightsizing_monthly_savings = 0.0
    for s in summary:
        # If GPU has low MFU or is flagged as util-lie or low MBU
        if s["mfu"] < 0.30 or s["mbu"] < 0.35:
            candidates = metrics.rightsize_mbu_candidates(s["gpu_type"], s["achieved_bw_tbs"], cat)
            if candidates:
                best = candidates[0]  # cheapest viable
                monthly_saving = (best["current_price_hr"] - best["target_price_hr"]) * 24 * 30
                rightsizing_monthly_savings += monthly_saving
                rightsizing_recs.append({
                    "gpu_id": s["gpu_id"],
                    "current_gpu": s["gpu_type"],
                    "achieved_bw_tbs": s["achieved_bw_tbs"],
                    "target_gpu": best["target_gpu"],
                    "target_bw_tbs": best["peak_bw_tbs"],
                    "current_price_hr": best["current_price_hr"],
                    "target_price_hr": best["target_price_hr"],
                    "savings_pct": best["savings_pct"],
                    "monthly_savings": round(monthly_saving, 2),
                })

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")

        if rightsizing_recs:
            print("\n-- Extension 2: MBU Right-Sizing Recommendations --")
            print(f"{'GPU ID':12}{'Current':9}{'AchievedBW':12}{'Target GPU':12}{'TargetBW':10}{'$/hr Old':10}{'$/hr New':10}{'Mo Savings':12}")
            for r in rightsizing_recs:
                print(f"{r['gpu_id']:12}{r['current_gpu']:9}{r['achieved_bw_tbs']:<12.3f}{r['target_gpu']:12}{r['target_bw_tbs']:<10.2f}${r['current_price_hr']:<9.2f}${r['target_price_hr']:<9.2f}${r['monthly_savings']:<11,.0f}")
            print(f"Total potential MBU right-sizing savings: ${rightsizing_monthly_savings:,.0f}/month")

    return {
        "summary": summary,
        "lies": lies,
        "idle_waste_daily": round(idle_waste, 2),
        "rightsizing_recs": rightsizing_recs,
        "rightsizing_monthly_savings": round(rightsizing_monthly_savings, 2),
    }


if __name__ == "__main__":
    run()
