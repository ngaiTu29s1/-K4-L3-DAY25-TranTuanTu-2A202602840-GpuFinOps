"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing

from finops import pricing, sustainability

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}
CACHE_WRITE_MULTIPLIER = 1.25  # standard industry write premium (e.g. Anthropic prompt caching)


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = 0.0
    total_tokens = 0

    # Tracking for Extension 3 & 4
    total_input_tokens = total_cached_tokens = 0
    reasoning_reqs = 0
    reasoning_tokens = 0
    reasoning_opt_cost = 0.0
    standard_opt_cost = 0.0
    reasoning_wh = 0.0
    standard_wh = 0.0

    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        is_reasoning = bool(int(num(r["is_reasoning"])))
        req_tokens = inp + out
        total_tokens += req_tokens
        total_input_tokens += inp
        total_cached_tokens += cached

        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)

        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        cost = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        opt_cost += cost

        # Energy tracking
        req_wh = sustainability.wh_per_query(req_tokens, is_reasoning=is_reasoning)
        if is_reasoning:
            reasoning_reqs += 1
            reasoning_tokens += req_tokens
            reasoning_opt_cost += cost
            reasoning_wh += req_wh
        else:
            standard_opt_cost += cost
            standard_wh += req_wh

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    # --- Extension 3: Cache Economics Evaluation ---
    # Realistic prompt caching write cost is 1.25x input price
    large_write_cost = MODEL_PRICES["large"][0] * CACHE_WRITE_MULTIPLIER
    small_write_cost = MODEL_PRICES["small"][0] * CACHE_WRITE_MULTIPLIER
    be_reads_large = pricing.break_even_cache_reads(large_write_cost, MODEL_PRICES["large"][0], 0.10)
    be_reads_small = pricing.break_even_cache_reads(small_write_cost, MODEL_PRICES["small"][0], 0.10)

    # In chat/RAG workflows with multi-turn conversations, average reads per prefix is ~4.0x
    assumed_reads_per_prefix = 4.0
    cache_worth_large = pricing.cache_is_worth_it(assumed_reads_per_prefix, large_write_cost, 0.10, MODEL_PRICES["large"][0])
    cache_worth_small = pricing.cache_is_worth_it(assumed_reads_per_prefix, small_write_cost, 0.10, MODEL_PRICES["small"][0])

    cache_metrics = {
        "cached_tokens": total_cached_tokens,
        "input_tokens": total_input_tokens,
        "overall_cache_hit_ratio": round(total_cached_tokens / total_input_tokens if total_input_tokens else 0, 3),
        "break_even_reads_large": round(be_reads_large, 2),
        "break_even_reads_small": round(be_reads_small, 2),
        "cache_is_worth_it": cache_worth_large and cache_worth_small,
    }

    # --- Extension 4: Reasoning Budget Analysis ---
    n_total = len(rows)
    reasoning_req_pct = (reasoning_reqs / n_total * 100) if n_total else 0.0
    reasoning_token_pct = (reasoning_tokens / total_tokens * 100) if total_tokens else 0.0
    reasoning_cost_pct = (reasoning_opt_cost / opt_cost * 100) if opt_cost else 0.0
    total_wh = reasoning_wh + standard_wh
    reasoning_wh_pct = (reasoning_wh / total_wh * 100) if total_wh else 0.0

    # Simulated selective routing: If reasoning is gated to 10% traffic instead of current %
    target_cap_frac = 0.10
    if reasoning_reqs > 0 and reasoning_req_pct > 10.0:
        reduction_factor = (target_cap_frac * n_total) / reasoning_reqs
        gated_savings_cost = reasoning_opt_cost * (1.0 - reduction_factor)
        gated_savings_wh = reasoning_wh * (1.0 - reduction_factor)
    else:
        gated_savings_cost = 0.0
        gated_savings_wh = 0.0

    reasoning_metrics = {
        "reasoning_reqs": reasoning_reqs,
        "reasoning_req_pct": round(reasoning_req_pct, 1),
        "reasoning_tokens": reasoning_tokens,
        "reasoning_token_pct": round(reasoning_token_pct, 1),
        "reasoning_cost_daily": round(reasoning_opt_cost, 2),
        "reasoning_cost_pct": round(reasoning_cost_pct, 1),
        "reasoning_wh_daily": round(reasoning_wh, 2),
        "reasoning_wh_pct": round(reasoning_wh_pct, 1),
        "gated_savings_usd_daily": round(gated_savings_cost, 2),
        "gated_savings_wh_daily": round(gated_savings_wh, 2),
    }

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")

        print("\n-- Extension 3: Cache Economics (cache_is_worth_it) --")
        print(f"Cache hit tokens: {total_cached_tokens:,} / {total_input_tokens:,} ({cache_metrics['overall_cache_hit_ratio']:.1%})")
        print(f"Break-even reads (Large): {be_reads_large:.2f}x | (Small): {be_reads_small:.2f}x")
        print(f"Cache worth it for workloads with >= {be_reads_large:.2f} reads: {cache_metrics['cache_is_worth_it']}")

        print("\n-- Extension 4: Reasoning Budget & Energy Disproportion --")
        print(f"Reasoning requests: {reasoning_reqs} ({reasoning_req_pct:.1f}% of requests)")
        print(f"Reasoning tokens:   {reasoning_tokens:,} ({reasoning_token_pct:.1f}% of volume)")
        print(f"Reasoning cost:     ${reasoning_opt_cost:.2f}/day ({reasoning_cost_pct:.1f}% of optimized spend)")
        print(f"Reasoning energy:   {reasoning_wh:.1f} Wh/day ({reasoning_wh_pct:.1f}% of total inference power)")
        print(f"Selective routing savings (capping to 10% traffic): ${gated_savings_cost*30:,.0f}/mo and {gated_savings_wh*30/1000:,.1f} kWh/mo")

    return {
        "baseline_daily": round(base_cost, 2),
        "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3),
        "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1),
        "total_tokens": total_tokens,
        "cache_metrics": cache_metrics,
        "reasoning_metrics": reasoning_metrics,
    }


if __name__ == "__main__":
    run()
