# NimbusAI — GPU Cost Optimization Report

**Period:** monthly  
**Baseline spend:** $27,133  
**Optimized spend:** $14,626  
**Projected savings:** $12,507  (**46%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,212 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per query: 0.24 Wh
- Carbon per query: 0.091 gCO2e
- Cheapest+cleanest region: europe-north1

## Deep-Dive: Root Cause of the 'GPU-Util Lie'

The M1 audit flagged the following GPUs as 'GPU-Util Lies': `gpu-h100-4, gpu-a10g-1` (active utilization >= 90% while computational MFU < 30%).

- **Underlying Mechanism:** `nvidia-smi` GPU-Util measures the percentage of time that any GPU kernel was actively scheduled on the hardware clocks. It does **not** measure computational efficiency or achieved throughput (FLOPs). In memory-bound workloads (where arithmetic intensity is below the GPU's ridge point) or in un-batched inference pipelines with heavy kernel-launch overhead, the Tensor Cores spend the majority of cycles stalled waiting on HBM memory transfers or host synchronization. Consequently, the GPU registers 98% utilization while performing useful math at less than 20% of its rated capability.
- **Financial Impact:** NimbusAI is paying top-tier rental rates ($2.50/GPU-hr for H100) for hardware operating at 1/5th its throughput. Downsizing or refactoring these workloads recovers $655 to $1,879/month in unnecessary cloud spend.

## Prioritized FinOps Implementation Roadmap

FinOps remediation roadmap prioritized by ROI and implementation risk:

1. **P0 — Quick Wins (Immediate execution, zero application disruption):**
   - **Terminate Idle Instances Overnight:** Shut down unutilized instances like `gpu-h100-5` (idle 8 hours every night) to save $600/month immediately.
   - **Migrate Interruptible Jobs to Spot with Checkpointing:** Move training and evaluation batch jobs to Spot instances with regular checkpointing, cutting purchasing spend by $10,040/month.

2. **P1 — Application Architecture & API Levers (Weeks 2–3):**
   - **Enable Prompt Caching:** Benefit from 90% discount on static system prompts in multi-turn chat and RAG workflows.
   - **Model Cascade Routing:** Direct 80% of simpler traffic to small model tiers, slashing $/1M-token from $6.488 to $1.126 (82.6% savings).
   - **Batch API for Asynchronous Workloads:** Shift nightly evals and embeddings to Batch API for an unconditional 50% discount.

3. **P2 — Long-Term Commitments & Infrastructure Right-Sizing (Month 2):**
   - **3-Year Reserved Instances for Baseline Services:** Commit reserved capacity for steady-state 24/7 inference workloads where duty cycle >= 55%.
   - **Right-Size Memory-Bound Workloads:** Migrate bandwidth-constrained workloads from H100 to A100 or L4/A10G based on MBU profiling.

## Strategic Sustainability & Regional Placement

- **Inference Energy Footprint:** Average serving energy is **0.24 Wh per query**, yielding **0.091 gCO2e** on the standard `us-east-1` grid.
- **Strategic Regional Placement:**
  - **Cleanest Grid:** `europe-north1` (Norway hydro) has a carbon intensity of only 30 gCO2/kWh (12.6x cleaner than `us-east-1` and 22x cleaner than `europe-central2`). Routing interruptible training jobs to this region eliminates **92.1% of emissions** (saving ~1,480 kgCO2e/month).
  - **Lowest Electricity Cost:** `us-east-wa` (Washington hydro) offers $0.055/kWh, yielding 54% lower power costs than `us-east-1`.
  - *Trade-off Recommendation:* Offline batch training is network latency-insensitive; placing training in clean/cheap hydro regions maximizes sustainability with zero user impact.

## Advanced Extensions & Measurement Summary

- **Extension 1 (Advanced Purchasing Matrix):** Evaluated GPU-specific spot interruption probabilities (H100 3% vs A10G 8%) and job horizons, yielding $15,551/month optimized purchasing spend (39.4% saved).
- **Extension 2 (MBU Hardware Right-Sizing):** Matched achieved memory bandwidth to catalog tiers, unlocking up to $1,879/month by moving underutilized memory workloads to A100/A10G/L4.
- **Extension 3 (Economics of Prompt Caching):** Calculated write vs read break-even reuse factor (1.39x). Confirmed caching is highly profitable for chat/RAG sessions with >1.39 turns.
- **Extension 4 (Reasoning Workload Budgeting):** Found that reasoning requests represent only 8.4% of request volume but generate 16.5% of tokens and consume **94.0% of total inference energy (Wh)**.
- **Extension 5 (Carbon-Aware Scheduling):** Analyzed multi-region scheduling for 4,227 kWh of monthly interruptible compute, proving a 1,479.5 kgCO2e/month reduction via green region selection.

_Figures are June-2026 as-of snapshots; re-baseline before acting._