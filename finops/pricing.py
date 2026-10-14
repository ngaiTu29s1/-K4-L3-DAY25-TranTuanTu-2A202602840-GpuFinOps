"""Pricing & purchasing economics — measure in $/1M-token, not $/GPU-hr.

Figures are June-2026 as-of snapshots from the deck's RESEARCH dossier; treat
live prices as fast-moving (re-baseline before each cohort).
"""
from __future__ import annotations


def request_cost(
    input_tok: int,
    output_tok: int,
    price_in_per_m: float,
    price_out_per_m: float,
    cached_in: int = 0,
    cache_discount: float = 0.10,   # Anthropic cached-read ~0.1x (=-90%)
    batch: bool = False,
    batch_discount: float = 0.50,   # Batch API ~ -50%
) -> float:
    """USD cost of a single request. Cached input billed at cache_discount x price."""
    cached_in = min(max(0, cached_in), input_tok)
    uncached_in = input_tok - cached_in
    cost = (
        (uncached_in / 1e6) * price_in_per_m
        + (cached_in / 1e6) * price_in_per_m * cache_discount
        + (output_tok / 1e6) * price_out_per_m
    )
    if batch:
        cost *= batch_discount
    return cost


def dollars_per_million(total_cost_usd: float, total_tokens: int) -> float:
    """Aggregate unit economics: $ per 1,000,000 tokens served."""
    if total_tokens <= 0:
        return 0.0
    return total_cost_usd / (total_tokens / 1e6)


def discount_stack(
    batch: bool = False,
    cache_hit_frac: float = 0.0,
    batch_discount: float = 0.50,
    cache_discount: float = 0.10,
) -> float:
    """Effective fraction of the naive bill after stacking discounts (input-heavy view).

    Discounts MULTIPLY: cache applies to the cached share of input, batch to the
    whole bill. batch + 100% cache-hit -> 0.5 * 0.1 = 0.05 (~95% off).
    """
    cache_mult = cache_hit_frac * cache_discount + (1.0 - cache_hit_frac)
    batch_mult = batch_discount if batch else 1.0
    return cache_mult * batch_mult


def break_even_utilization(discount_frac: float) -> float:
    """Utilization at which a commitment pays off ~= 1 - discount.

    A 45% reserved discount needs ~55% utilization (~13.2h/day) to beat on-demand.
    """
    return max(0.0, min(1.0, 1.0 - discount_frac))


def cache_is_worth_it(
    avg_cache_reads: float,
    write_cost_per_m: float,
    read_discount: float = 0.10,
    base_price_in_per_m: float = 3.00,
) -> bool:
    """Check if prompt caching is cost-effective given write overhead and read reuse.

    In production systems (e.g. Anthropic, Gemini, OpenAI), caching incurs a
    write/storage cost. Cached read gets a discount: base_price * (1 - read_discount).
    Net savings per 1M tokens = avg_cache_reads * base_price * (1 - read_discount) - write_cost.
    Cache is worth it if net savings > 0.
    """
    if avg_cache_reads <= 0:
        return False
    unit_savings_per_read = base_price_in_per_m * (1.0 - read_discount)
    if unit_savings_per_read <= 0:
        return False
    return (avg_cache_reads * unit_savings_per_read) > write_cost_per_m


def break_even_cache_reads(
    write_cost_per_m: float,
    base_price_in_per_m: float,
    read_discount: float = 0.10,
) -> float:
    """Calculate minimum read reuse factor needed to break even on cache creation costs."""
    unit_savings_per_read = base_price_in_per_m * (1.0 - read_discount)
    if unit_savings_per_read <= 0:
        return float("inf")
    return write_cost_per_m / unit_savings_per_read


GPU_INTERRUPT_RATES = {
    "H100": 0.03,    # High priority enterprise demand, lower spot reclaim
    "H200": 0.04,
    "A100": 0.05,
    "A10G": 0.08,    # Higher spot volatility
    "L4": 0.06,
    "B200": 0.05,
    "MI300X": 0.07,
}


def recommend_tier(
    hours_per_day: float,
    interruptible: bool,
    reserved_discount: float = 0.45,
    gpu_type: str | None = None,
    job_days: float | None = None,
) -> str:
    """Pick a purchasing tier from a workload's duty cycle + interruptibility.

    DOCUMENTED policy (with backward compatibility):
      - interruptible & not 24/7  -> 'spot'      (checkpoint and ride the discount)
      - duty cycle >= break-even  -> 'reserved'  (steady, high utilization)
      - otherwise                 -> 'on_demand' (spiky / low duty)
    """
    duty = max(0.0, hours_per_day) / 24.0
    be = break_even_utilization(reserved_discount)
    if interruptible and hours_per_day < 24:
        return "spot"
    if duty >= be:
        return "reserved"
    return "on_demand"


def recommend_tier_advanced(
    hours_per_day: float,
    interruptible: bool,
    gpu_type: str = "H100",
    job_days: float = 30,
    reserved_3yr_discount: float = 0.45,
    reserved_1yr_discount: float = 0.20,
    on_demand_hr: float = 2.50,
    spot_hr: float = 1.50,
    reserved_1yr_hr: float = 2.00,
    reserved_3yr_hr: float = 1.40,
) -> dict:
    """Advanced multi-factor tier selection considering interruption risk and commitment horizon."""
    duty = max(0.0, hours_per_day) / 24.0
    int_rate = GPU_INTERRUPT_RATES.get(gpu_type, 0.05)
    
    spot_viable = interruptible and hours_per_day < 24
    if spot_viable:
        sim = spot_checkpoint_cost(
            job_hours=hours_per_day * job_days,
            spot_hr=spot_hr,
            on_demand_hr=on_demand_hr,
            interrupt_rate=int_rate,
        )
        spot_effective_hr = sim["spot_cost"] / (hours_per_day * job_days) if hours_per_day * job_days > 0 else spot_hr
    else:
        sim = None
        spot_effective_hr = float("inf")

    be_3yr = break_even_utilization(reserved_3yr_discount)
    be_1yr = break_even_utilization(reserved_1yr_discount)

    if spot_viable and spot_effective_hr < on_demand_hr:
        best_tier = "spot"
        effective_rate = spot_effective_hr
        rationale = f"Workload is interruptible ({gpu_type} interrupt rate {int_rate:.1%}); checkpointing saves {sim['savings_pct'] if sim else 0}% vs on-demand."
    elif duty >= be_3yr and job_days >= 180:
        best_tier = "reserved_3yr"
        effective_rate = reserved_3yr_hr
        rationale = f"Duty cycle ({duty:.1%}) >= break-even ({be_3yr:.1%}) and long horizon ({job_days} days) justify 3yr commitment (45% discount)."
    elif duty >= be_1yr and job_days >= 60:
        best_tier = "reserved_1yr"
        effective_rate = reserved_1yr_hr
        rationale = f"Duty cycle ({duty:.1%}) qualifies for 1yr commitment (20% discount) with lower lock-in risk."
    elif duty >= be_3yr:
        best_tier = "reserved"
        effective_rate = reserved_3yr_hr
        rationale = f"High duty cycle ({duty:.1%}) >= break-even ({be_3yr:.1%}) maximizes reservation discount."
    else:
        best_tier = "on_demand"
        effective_rate = on_demand_hr
        rationale = f"Duty cycle ({duty:.1%}) is below break-even ({be_3yr:.1%}); on-demand avoids unutilized commitment waste."

    return {
        "tier": best_tier,
        "effective_hourly_rate": round(effective_rate, 3),
        "spot_viable": spot_viable,
        "duty_cycle": round(duty, 3),
        "interruption_rate": int_rate,
        "rationale": rationale,
    }


def spot_checkpoint_cost(
    job_hours: float,
    spot_hr: float,
    on_demand_hr: float,
    interrupt_rate: float = 0.05,      # per-hour chance (H100 spot ~<5%)
    ckpt_overhead_frac: float = 0.03,  # steady cost of writing checkpoints
    rework_hours_per_interrupt: float = 0.5,
) -> dict:
    """Effective cost of running a checkpointable job on spot vs on-demand.

    Interruptions waste the compute since the last checkpoint (rework); checkpointing
    adds a small steady overhead. Spot still wins for interruptible jobs.
    """
    expected_interrupts = job_hours * interrupt_rate
    rework_hours = expected_interrupts * rework_hours_per_interrupt
    effective_hours = job_hours * (1.0 + ckpt_overhead_frac) + rework_hours
    spot_cost = effective_hours * spot_hr
    on_demand_cost = job_hours * on_demand_hr
    savings_pct = (1.0 - spot_cost / on_demand_cost) * 100.0 if on_demand_cost > 0 else 0.0
    return {
        "spot_effective_hours": round(effective_hours, 2),
        "spot_cost": round(spot_cost, 2),
        "on_demand_cost": round(on_demand_cost, 2),
        "savings_pct": round(savings_pct, 1),
    }
