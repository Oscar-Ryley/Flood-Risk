#!/usr/bin/env python3
# Shebang for Unix execution

# Imports
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen

# Default data sources and paths
URL = "https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/datasets/live-power-cuts-data/exports/geojson?lang=en&timezone=Europe%2FLondon"
FLOOD_URL = "https://environment.data.gov.uk/flood-monitoring/id/floods.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_PATH = REPO_ROOT / "public" / "data" / "powercut_archive.geojson"
BOUNDARY_PATH = REPO_ROOT / "public" / "data" / "county_durham.geojson"


def load_snapshots(path: Path):
    # Read the existing archive, each line in the JSON is a snapshot
    if not path.exists() or path.stat().st_size == 0:
        return []

    snapshots = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue

            snapshot = json.loads(line)
            if isinstance(snapshot, dict) and snapshot.get("type") == "FeatureCollection" and isinstance(snapshot.get("features"), list):
                snapshots.append(snapshot)

    return snapshots


def fetch_snapshot(url: str) -> dict:
    # Download the latest power cut GeoJSON feed from Nothern Power Grid
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)

    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError("The downloaded payload was not a GeoJSON FeatureCollection")

    return payload


def fetch_floods(url: str) -> dict:
    # Download the current flood warnings feed from the Environment Agency
    request = Request(url, headers={"Accept": "application/json"})
    with urlopen(request, timeout=45) as response:
        payload = json.load(response)

    if not isinstance(payload, dict):
        raise ValueError("The downloaded flood payload was not a JSON object")

    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return {}

    floods = {"items": items}
    meta = payload.get("meta")
    if isinstance(meta, dict):
        floods["meta"] = meta

    return floods


def load_boundary_geometries(path: Path):
    # Load the county boundary as a list of geometry objects
    if not path.exists():
        return []

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        if data.get("type") == "FeatureCollection":
            features = data.get("features") or []
            geometries = []
            for feature in features:
                if isinstance(feature, dict) and feature.get("type") == "Feature":
                    geometry = feature.get("geometry")
                    if isinstance(geometry, dict):
                        geometries.append(geometry)
            return geometries

        if data.get("type") == "Feature":
            geometry = data.get("geometry")
            if isinstance(geometry, dict):
                return [geometry]

        if data.get("type") in {"Polygon", "MultiPolygon"} and isinstance(data.get("coordinates"), list):
            return [data]

    return []


def feature_is_within_boundary(feature, boundary_geometries):
    # Keep only point features that are inside the boundary polygon for county durham
    if not boundary_geometries:
        return True

    geometry = feature.get("geometry") or {}
    if not isinstance(geometry, dict):
        return False

    if geometry.get("type") != "Point":
        return False

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return False

    point = [coordinates[0], coordinates[1]]
    for boundary_geometry in boundary_geometries:
        if boundary_geometry.get("type") == "Polygon" and point_in_polygon(point, boundary_geometry.get("coordinates")):
            return True

    return False


def point_in_polygon(point, polygon):
    # Use a ray-casting method to test whether a point lies inside a polygon
    if not polygon or not isinstance(polygon, list):
        return False

    rings = polygon
    if len(rings) == 0:
        return False

    if not isinstance(rings[0], list):
        return False

    return any(point_in_ring(point, ring) for ring in rings)


def point_in_ring(point, ring):
    # Check whether the point is inside a ring of the county polygon
    x, y = point
    inside = False
    j = len(ring) - 1

    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        intersects = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi)
        if intersects:
            inside = not inside
        j = i

    return inside


def get_incident_key(feature: dict) -> Optional[str]:
    # Create an identifier from the incident properties when possible
    properties = feature.get("properties") or {}
    if not isinstance(properties, dict):
        return None

    for key in ["incident_id", "incident", "incident_code", "reference", "id", "outage_id", "outage_code", "incidentref", "incidentRef"]:
        value = properties.get(key)
        if value is not None and str(value).strip():
            return str(value)

    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if isinstance(coordinates, list) and len(coordinates) >= 2:
        lon, lat = coordinates[0], coordinates[1]
        return f"point:{lon:.5f}:{lat:.5f}"

    return None


def build_feature(feature: dict, incident_key: str) -> dict:
    # Build a GeoJSON feature with only useful properties kept
    geometry = feature.get("geometry")
    properties = feature.get("properties") or {}

    if not isinstance(properties, dict):
        properties = {}

    kept_properties = {}
    for key in ["reference", "type", "natureofoutage", "postcode", "postcodes", "incident_code", "incident_id", "incident", "status"]:
        if key in properties and properties[key] is not None:
            kept_properties[key] = properties[key]

    kept_properties["incident_key"] = incident_key

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": kept_properties,
    }


def build_snapshot(snapshot: dict, captured_at: str, floods: dict, boundary_geometries=None) -> dict:
    # Create one snapshot containing all boundary-filtered features for this run
    archived_features = []

    for feature in snapshot.get("features", []):
        if not isinstance(feature, dict):
            continue

        geometry = feature.get("geometry")
        if not geometry:
            continue

        if boundary_geometries is not None and not feature_is_within_boundary(feature, boundary_geometries):
            continue

        incident_key = get_incident_key(feature) or f"unknown:{len(archived_features)}"
        archived_features.append(build_feature(feature, incident_key))

    return {
        "type": "FeatureCollection",
        "captured_at": captured_at,
        "floods": floods if floods else {},
        "features": archived_features,
    }


def write_snapshots(path: Path, snapshots):
    # Write each snapshot as a JSON object on a new line
    with path.open("w", encoding="utf-8") as handle:
        for snapshot in snapshots:
            handle.write(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False))
            handle.write("\n")


def main() -> None:
    # Checks that archive folder exists before writing new snapshot
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load previous snapshots, fetch the latest feed
    snapshots = load_snapshots(ARCHIVE_PATH)
    snapshot = fetch_snapshot(URL)
    floods = fetch_floods(FLOOD_URL)
    boundary_geometries = load_boundary_geometries(BOUNDARY_PATH)
    captured_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    # Build new snapshot
    new_snapshot = build_snapshot(snapshot, captured_at, floods, boundary_geometries)
    snapshots.append(new_snapshot)
    write_snapshots(ARCHIVE_PATH, snapshots)

    # Write update to console
    total_features = len(new_snapshot["features"])
    total_flood_warnings = len(floods.get("items", [])) if isinstance(floods, dict) else 0
    print(f"Archived snapshot at {captured_at}, saved to {ARCHIVE_PATH}")
    print(f"Latest snapshot has {total_features} total features, {total_flood_warnings} flood warnings. Total Snapshots: {len(snapshots)}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed to archive power cuts: {exc}", file=sys.stderr)
        sys.exit(1)
