import json
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr


SCENARIOS = {
    "Baseline": (0.33, 0.33, 0.00, 0.34),
    "Hazard_Dominant": (0.70, 0.10, 0.10, 0.10),
    "Terrain_Dominant": (0.10, 0.70, 0.10, 0.10),
    "Vulnerability_Dominant": (0.10, 0.10, 0.70, 0.10),
    "Consequence_Dominant": (0.10, 0.10, 0.10, 0.70),
}
TIERS = ("low", "med", "high")
TIER_WEIGHTS = {"low": 0.55, "med": 1.5, "high": 3.3}


def calculate_final_score(
    dataframe: pd.DataFrame,
    w_H: float,
    w_T: float,
    w_V: float,
    w_C: float,
) -> pd.Series:
    tier_scores = {}
    for tier in TIERS:
        exposed = dataframe[f"rof_{tier}"].notna()
        hazard = pd.to_numeric(dataframe[f"degree_{tier}_norm"], errors="coerce").fillna(0.0)
        vulnerability = pd.to_numeric(
            dataframe[f"site_type_norm_{tier}"], errors="coerce"
        ).fillna(0.0)
        terrain = pd.to_numeric(dataframe["combined_norm"], errors="coerce").fillna(0.0)
        consequence = pd.to_numeric(
            dataframe["customers_class_norm"], errors="coerce"
        ).fillna(0.0)
        tier_score = (
            hazard * w_H
            + terrain * w_T
            + vulnerability * w_V
            + consequence * w_C
        )
        tier_scores[tier] = tier_score.where(exposed, 0.0).round(4)

    combined = sum(
        tier_scores[tier] * tier_weight
        for tier, tier_weight in TIER_WEIGHTS.items()
    ) / sum(TIER_WEIGHTS.values())
    has_exposure = dataframe[[f"rof_{tier}" for tier in TIERS]].notna().any(axis=1)
    return combined.where(has_exposure)


def load_default_dataframe(data_path: Path) -> pd.DataFrame:
    with data_path.open(encoding="utf-8") as input_file:
        features = json.load(input_file)["features"]

    source = pd.DataFrame(feature["properties"] for feature in features)
    source = source[source["final_risk_score"].notna()].copy()
    return source


def run_sensitivity_analysis(df: pd.DataFrame, output_path: str = "sensitivity_results.txt") -> None:
    required_columns = {
        "site_name",
        "combined_norm",
        "customers_class_norm",
        *(f"degree_{tier}_norm" for tier in TIERS),
        *(f"site_type_norm_{tier}" for tier in TIERS),
        *(f"rof_{tier}" for tier in TIERS),
    }
    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing_columns))}")
    results = df[["site_name"]].rename(columns={"site_name": "Substation_Name"}).copy()
    for scenario_name, weights in SCENARIOS.items():
        score = calculate_final_score(df, *weights)
        results[f"{scenario_name}_Score"] = score
        results[f"{scenario_name}_Rank"] = score.rank(method="dense", ascending=False).astype(int)

    top_10 = results.sort_values(
        by=["Baseline_Rank", "Baseline_Score", "Substation_Name"],
        ascending=[True, False, True],
    ).head(10)
    dominant_scenarios = list(SCENARIOS)[1:]
    correlations = {
        scenario_name: spearmanr(
            results["Baseline_Score"], results[f"{scenario_name}_Score"]
        ).statistic
        for scenario_name in dominant_scenarios
    }

    table_columns = ["Substation_Name"] + [
        f"{scenario_name}_Rank" for scenario_name in SCENARIOS
    ]
    table = top_10[table_columns].rename(
        columns={"Substation_Name": "Substation Name"}
    )
    table_text = table.to_string(index=False)

    with open(output_path, "w", encoding="utf-8") as output_file:
        output_file.write("BASELINE TOP 10 SUBSTATIONS\n")
        output_file.write(table_text)
        output_file.write("\n\nSPEARMAN RANK CORRELATIONS\n")
        for scenario_name, correlation in correlations.items():
            output_file.write(f"Baseline vs {scenario_name}: {correlation:.3f}\n")
    
    print(f"[1/1] Sensitivity analysis complete")
    print(f"      --> Results exported to: {output_path}")


if __name__ == "__main__":
    script_dir = Path(__file__).resolve().parent
    data_path = script_dir.parent / "data" / "substation_sites_processed.geojson"
    output_path = script_dir.parent / "data" / "sensitivity_results.txt"
    run_sensitivity_analysis(load_default_dataframe(data_path), output_path)
