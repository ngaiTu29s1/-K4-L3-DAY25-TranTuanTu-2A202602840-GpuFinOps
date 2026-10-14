import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finops import pricing, metrics, sustainability
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing


def test_cache_is_worth_it_logic():
    # Break-even check: write_cost = 3.75, base_price = 3.00, read_discount = 0.10 (90% off)
    # savings per read = 3.00 * 0.90 = 2.70. Break-even reads = 3.75 / 2.70 = 1.3888
    be = pricing.break_even_cache_reads(3.75, 3.00, 0.10)
    assert abs(be - 1.38888) < 1e-4

    # If reads < break-even, cache is NOT worth it
    assert pricing.cache_is_worth_it(1.0, 3.75, 0.10, 3.00) is False
    # If reads > break-even, cache IS worth it
    assert pricing.cache_is_worth_it(2.0, 3.75, 0.10, 3.00) is True
    # Zero or negative reads should return False
    assert pricing.cache_is_worth_it(0.0, 3.75, 0.10, 3.00) is False


def test_recommend_tier_advanced():
    # Interruptible workload with reasonable interruption rate should prefer spot
    res_spot = pricing.recommend_tier_advanced(
        hours_per_day=8,
        interruptible=True,
        gpu_type="H100",
        job_days=14,
        on_demand_hr=2.50,
        spot_hr=1.50,
    )
    assert res_spot["tier"] == "spot"
    assert res_spot["spot_viable"] is True

    # High duty non-interruptible long horizon should recommend reserved_3yr
    res_res = pricing.recommend_tier_advanced(
        hours_per_day=24,
        interruptible=False,
        gpu_type="A100",
        job_days=180,
        on_demand_hr=1.79,
        spot_hr=1.10,
        reserved_3yr_hr=1.00,
    )
    assert res_res["tier"] == "reserved_3yr"

    # Low duty cycle non-interruptible should stay on_demand
    res_od = pricing.recommend_tier_advanced(
        hours_per_day=4,
        interruptible=False,
        gpu_type="A10G",
        job_days=30,
        on_demand_hr=1.00,
        spot_hr=0.40,
    )
    assert res_od["tier"] == "on_demand"


def test_mbu_rightsizing_candidates():
    cat = {
        "H100": {"on_demand_hr": 2.50, "peak_bw_tbs": 3.35, "hbm_gb": 80},
        "A100": {"on_demand_hr": 1.79, "peak_bw_tbs": 2.00, "hbm_gb": 80},
        "A10G": {"on_demand_hr": 1.00, "peak_bw_tbs": 0.60, "hbm_gb": 24},
        "L4": {"on_demand_hr": 0.80, "peak_bw_tbs": 0.30, "hbm_gb": 24},
    }
    # Workload achieves 0.5 TB/s on H100. A100 (2.0 TB/s) and A10G (0.6 TB/s) qualify.
    cands = metrics.rightsize_mbu_candidates("H100", 0.5, cat)
    assert len(cands) > 0
    # Cheapest valid candidate should be A10G (1.00 $/hr)
    assert cands[0]["target_gpu"] == "A10G"
    assert cands[0]["savings_pct"] > 50


def test_reasoning_and_sustainability_metrics():
    # Normal query
    wh_norm = sustainability.wh_per_query(1000, is_reasoning=False)
    # Reasoning query has 80x multiplier
    wh_reas = sustainability.wh_per_query(1000, is_reasoning=True)
    assert abs(wh_reas / wh_norm - 80.0) < 1e-4

    # Europe-north1 is cleaner than us-east-1
    assert sustainability.REGION_CARBON["europe-north1"] < sustainability.REGION_CARBON["us-east-1"]
