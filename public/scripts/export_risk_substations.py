#!/usr/bin/env python3

import argparse
import math
from pathlib import Path

import geopandas as gpd


RISK_CATEGORIES = (
    (0.75, "High Risk"),
    (0.5, "Medium Risk"),
    (0.0, "Low Risk"),
)


def classify_risk(score: float) -> str:
    for threshold, category in RISK_CATEGORIES:
        if score >= threshold:
            return category
    raise ValueError(f"Risk score must be greater than zero, got {score}")


def format_value(value) -> str:
    if value is None:
        return "N/A"
    try:
        if math.isnan(value):
            return "N/A"
    except TypeError:
        pass
    return str(value)


def export_risk_substations(input_path: Path, output_path: Path) -> None:
    print("[1/1] Exporting classified substations...")
    
    if not input_path.exists():
        raise FileNotFoundError(f"Processed GeoJSON not found at: {input_path}")

    gdf = gpd.read_file(input_path)
    if "final_risk_score" not in gdf.columns:
        raise ValueError("Processed GeoJSON is missing the 'final_risk_score' column.")

    scores = gdf["final_risk_score"].apply(
        lambda value: float(value) if value is not None else math.nan
    )
    classified = gdf[scores.notna() & (scores > 0)].copy()
    classified["_risk_score"] = scores.loc[classified.index]
    classified["_risk_category"] = classified["_risk_score"].apply(classify_risk)
    classified = classified.sort_values(
        by=["_risk_score", "site_name"],
        ascending=[False, True],
        na_position="last",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("CLASSIFIED SUBSTATIONS BY FINAL RISK SCORE\n")
        handle.write(f"Classified substations: {len(classified)}\n")
        handle.write("Scores are sorted from highest to lowest.\n")
        handle.write("=" * 80 + "\n\n")

        for number, (_, row) in enumerate(classified.iterrows(), start=1):
            handle.write(f"{number}. {format_value(row.get('site_name'))}\n")
            handle.write(f"Risk category: {row['_risk_category']}\n")
            handle.write(f"Final risk score: {row['_risk_score']:.4f}\n")

            for column in gdf.columns:
                if column == gdf.geometry.name:
                    continue
                handle.write(f"{column}: {format_value(row[column])}\n")

            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                handle.write("geometry: N/A\n")
            else:
                handle.write(f"geometry: {geometry.wkt}\n")
            handle.write("-" * 80 + "\n")

    print(f"      --> Exported {len(classified)} classified substations to: {output_path}")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    data_dir = script_dir.parent / "data"
    parser = argparse.ArgumentParser(
        description="Export classified processed substations to a sorted text file."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=data_dir / "substation_sites_processed.geojson",
        help="Path to the processed GeoJSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=data_dir / "classified_risk_substations.txt",
        help="Path for the text export.",
    )
    args = parser.parse_args()
    export_risk_substations(args.input, args.output)


if __name__ == "__main__":
    main()
