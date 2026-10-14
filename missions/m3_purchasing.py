"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing, sustainability

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    advanced_recs = []
    advanced_opt_monthly = 0.0

    # Total energy consumed by interruptible jobs for carbon-aware scheduling (Wh)
    total_interruptible_wh = 0.0

    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        job_days = num(j.get("days", 30))
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        spot_price = num(c["spot_hr"])
        r1yr_price = num(c.get("reserved_1yr_hr", od * 0.8))
        r3yr_price = num(c.get("reserved_3yr_hr", od * 0.55))
        watts = num(c.get("watts", 400))
        on_demand_cost = gpu_hours * od

        # BASELINE POLICY
        tier = pricing.recommend_tier(hpd, interruptible)
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, spot_price, od)
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            opt_cost = gpu_hours * r3yr_price
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

        # EXTENSION 1: ADVANCED MULTI-FACTOR TIER POLICY
        adv_res = pricing.recommend_tier_advanced(
            hours_per_day=hpd,
            interruptible=interruptible,
            gpu_type=gtype,
            job_days=job_days,
            on_demand_hr=od,
            spot_hr=spot_price,
            reserved_1yr_hr=r1yr_price,
            reserved_3yr_hr=r3yr_price,
        )
        adv_tier = adv_res["tier"]
        if adv_tier == "spot":
            int_rate = adv_res["interruption_rate"]
            sim_adv = pricing.spot_checkpoint_cost(gpu_hours, spot_price, od, interrupt_rate=int_rate)
            adv_cost = sim_adv["spot_cost"]
        elif adv_tier in ("reserved", "reserved_3yr"):
            adv_cost = gpu_hours * r3yr_price
        elif adv_tier == "reserved_1yr":
            adv_cost = gpu_hours * r1yr_price
        else:
            adv_cost = on_demand_cost

        advanced_opt_monthly += adv_cost
        advanced_recs.append({
            "job_id": j["job_id"],
            "gpu_type": gtype,
            "adv_tier": adv_tier,
            "interruption_rate": adv_res["interruption_rate"],
            "cost": round(adv_cost),
            "rationale": adv_res["rationale"],
        })

        # EXTENSION 5: Track energy for interruptible jobs
        if interruptible:
            # Monthly energy in Wh
            total_interruptible_wh += gpu_hours * watts

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    adv_savings = on_demand_monthly - advanced_opt_monthly
    adv_savings_pct = adv_savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    # Extension 5: Multi-region carbon and electricity cost analysis
    default_region = "us-east-1"
    cleanest_region = "europe-north1"
    default_carbon_kg = (sustainability.carbon_g(total_interruptible_wh, default_region)) / 1000.0
    cleanest_carbon_kg = (sustainability.carbon_g(total_interruptible_wh, cleanest_region)) / 1000.0
    carbon_reduction_kg = default_carbon_kg - cleanest_carbon_kg
    carbon_reduction_pct = (carbon_reduction_kg / default_carbon_kg * 100) if default_carbon_kg else 0.0

    regional_comparison = []
    for reg, g_co2 in sustainability.REGION_CARBON.items():
        kwh = total_interruptible_wh / 1000.0
        c_kg = (kwh * g_co2) / 1000.0
        cost_elec = kwh * sustainability.REGION_PRICE_KWH[reg]
        regional_comparison.append({
            "region": reg,
            "carbon_intensity_g_kwh": g_co2,
            "price_per_kwh": sustainability.REGION_PRICE_KWH[reg],
            "total_monthly_carbon_kg": round(c_kg, 1),
            "total_monthly_elec_usd": round(cost_elec, 2),
        })

    carbon_scheduling = {
        "total_interruptible_kwh": round(total_interruptible_wh / 1000.0, 1),
        "default_region": default_region,
        "default_carbon_kg": round(default_carbon_kg, 1),
        "cleanest_region": cleanest_region,
        "cleanest_carbon_kg": round(cleanest_carbon_kg, 1),
        "carbon_saved_kg": round(carbon_reduction_kg, 1),
        "carbon_savings_pct": round(carbon_reduction_pct, 1),
        "regional_comparison": regional_comparison,
    }

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")

        print("\n-- Extension 1: Advanced Tier Matrix (Interruption Risk & Horizon) --")
        print(f"{'job':18}{'gpu':7}{'adv_tier':14}{'adv_cost':>10}  Rationale")
        for ar in advanced_recs:
            print(f"{ar['job_id']:18}{ar['gpu_type']:7}{ar['adv_tier']:14}${ar['cost']:>9,}  {ar['rationale']}")
        print(f"Advanced Policy Monthly Cost: ${advanced_opt_monthly:,.0f} ({adv_savings_pct:.1f}% saved vs on-demand)")

        print("\n-- Extension 5: Carbon-Aware Scheduling (Interruptible Jobs) --")
        print(f"Total interruptible compute: {carbon_scheduling['total_interruptible_kwh']:,} kWh/month")
        print(f"{'Region':18}{'gCO2/kWh':>10}{'$/kWh':>10}{'Carbon (kg)':>14}{'Elec Cost':>12}")
        for rc in regional_comparison:
            print(f"{rc['region']:18}{rc['carbon_intensity_g_kwh']:>10}{rc['price_per_kwh']:>10.3f}${rc['total_monthly_carbon_kg']:>13,.1f}${rc['total_monthly_elec_usd']:>11,.2f}")
        print(f"Relocating to {cleanest_region}: Saves {carbon_reduction_kg:,.1f} kgCO2e/month ({carbon_reduction_pct:.1f}% carbon reduction!)")

    return {
        "recommendations": recs,
        "on_demand_monthly": round(on_demand_monthly),
        "optimized_monthly": round(optimized_monthly),
        "savings_pct": round(savings_pct, 1),
        "advanced_recommendations": advanced_recs,
        "advanced_optimized_monthly": round(advanced_opt_monthly),
        "carbon_scheduling": carbon_scheduling,
    }


if __name__ == "__main__":
    run()
