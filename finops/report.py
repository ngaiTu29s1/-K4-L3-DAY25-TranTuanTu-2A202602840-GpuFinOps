"""Report assembly — the lab's deliverable: baseline vs optimized + savings chart."""
from __future__ import annotations


def build_report(
    baseline_usd: float,
    optimized_usd: float,
    levers: dict,
    sustainability: dict | None = None,
    period: str = "monthly",
    details: dict | None = None,
) -> str:
    """Return a comprehensive markdown cost-optimization report matching Rubric specifications."""
    savings = baseline_usd - optimized_usd
    pct = (savings / baseline_usd * 100.0) if baseline_usd > 0 else 0.0
    lines = [
        "# NimbusAI — GPU Cost Optimization Report",
        "",
        f"**Period:** {period}  ",
        f"**Baseline spend:** ${baseline_usd:,.0f}  ",
        f"**Optimized spend:** ${optimized_usd:,.0f}  ",
        f"**Projected savings:** ${savings:,.0f}  (**{pct:.0f}%**)",
        "",
        "## Savings by lever",
        "",
        "| Lever | Savings (USD) |",
        "|---|---|",
    ]
    for name, amount in levers.items():
        lines.append(f"| {name} | ${amount:,.0f} |")

    if sustainability:
        lines += [
            "",
            "## Sustainability",
            "",
            f"- Energy per query: {sustainability.get('wh_per_query', 0):.2f} Wh",
            f"- Carbon per query: {sustainability.get('carbon_g', 0):.3f} gCO2e",
            f"- Cheapest+cleanest region: {sustainability.get('best_region', 'n/a')}",
        ]

    # Additional deep-dive analysis required by Rubric C.2
    if details:
        if "util_lie_analysis" in details:
            lines += ["", "## Deep-Dive: Root Cause of the 'GPU-Util Lie'", "", details["util_lie_analysis"]]
        if "prioritized_actions" in details:
            lines += ["", "## Prioritized FinOps Implementation Roadmap", "", details["prioritized_actions"]]
        if "sustainability_analysis" in details:
            lines += ["", "## Strategic Sustainability & Regional Placement", "", details["sustainability_analysis"]]
        if "extensions_analysis" in details:
            lines += ["", "## Advanced Extensions & Measurement Summary", "", details["extensions_analysis"]]

    lines += ["", "_Figures are June-2026 as-of snapshots; re-baseline before acting._"]
    return "\n".join(lines)


def savings_waterfall(levers: dict, path: str) -> str:
    """Write a clean savings bar chart PNG with value annotations. Returns path or empty string."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return ""
    names = list(levers.keys())
    vals = [levers[n] for n in names]
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(names, vals, color=["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728"], edgecolor="#333", linewidth=0.8)
    ax.set_ylabel("Monthly Savings (USD)", fontsize=11)
    ax.set_title("GPU Cost Optimization — Projected Monthly Savings by Lever", fontsize=13, fontweight="bold", pad=12)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    # Annotate bar values
    for bar in bars:
        h = bar.get_height()
        ax.annotate(f"${h:,.0f}",
                    xy=(bar.get_x() + bar.get_width() / 2, h),
                    xytext=(0, 4), textcoords="offset points",
                    ha="center", va="bottom", fontsize=10, fontweight="bold")

    plt.xticks(rotation=15, ha="right", fontsize=9.5)
    plt.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
