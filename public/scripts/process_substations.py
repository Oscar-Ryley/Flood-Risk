import math
from pathlib import Path
import warnings

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import rasterio
from rasterio.windows import from_bounds
from scipy.ndimage import uniform_filter
from scipy.signal import convolve2d
from shapely.geometry import box
from shapely.ops import transform

# check for pyogrio fast I/O engine
try:
    import pyogrio
    HAS_PYOGRIO = True
except ImportError:
    HAS_PYOGRIO = False

# robust progress bar fallback
try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, iterable=None, desc="", total=None, **kwargs):
            self.iterable = iterable
            self.total = total
            self.desc = desc
            if desc:
                print(f"--> {desc}...")

        def __iter__(self):
            return iter(self.iterable) if self.iterable is not None else iter([])

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

        def update(self, n=1):
            pass

        def set_postfix_str(self, s):
            pass

warnings.filterwarnings("ignore", category=UserWarning)

# lookup tables and default weights

UKCEH_MAPPING = {
    "Broadleaved woodland": {"mannings": 0.100, "df_class": "Woodland"},
    "Coniferous woodland": {"mannings": 0.100, "df_class": "Woodland"},
    "Arable and horticulture": {"mannings": 0.030, "df_class": "Pasture/Arable"},
    "Improved grassland": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Neutral grassland": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Calcareous grassland": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Acid grassland": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Fen, marsh and swamp": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Heather": {"mannings": 0.050, "df_class": "Pasture/Arable"},
    "Heather grassland": {"mannings": 0.050, "df_class": "Pasture/Arable"},
    "Bog": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Inland rock": {"mannings": 0.035, "df_class": "Pasture/Arable"},
    "Saltwater": {"mannings": 0.070, "df_class": "Pasture/Arable"},
    "Freshwater": {"mannings": 0.070, "df_class": "Pasture/Arable"},
    "Supralittoral sediment": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Littoral rock": {"mannings": 0.035, "df_class": "Pasture/Arable"},
    "Littoral sediment": {"mannings": 0.040, "df_class": "Pasture/Arable"},
    "Urban": {"mannings": 0.013, "df_class": "Urban"},
    "Suburban": {"mannings": 0.013, "df_class": "Urban"},
}

DEFAULT_WEIGHTS = {
    "physical": 0.25,
    "terrain": 0.25,
    "vulnerability": 0.25,
    "consequence": 0.25,
}

TIERS = ["high", "med", "low"]
FLOOD_DEPTHS = (0.2, 0.3, 0.6, 0.9, 1.2)


def load_raw_flood_depths(gdf: gpd.GeoDataFrame, data_dir: str | Path) -> gpd.GeoDataFrame:
    """Sample each raw flood-depth polygon layer at substation points and extract EA likelihoods."""
    data_dir = Path(data_dir)
    result = gdf.copy()

    if result.crs is None:
        raise ValueError("Substation geometries must have a CRS to sample raw flood data.")

    for dataset_name in ["rofrs", "rofsw"]:
        for depth in FLOOD_DEPTHS:
            depth_text = str(depth).replace(".", "_")
            result[f"{dataset_name}_{depth_text}m"] = None

    total_layers = 2 * len(FLOOD_DEPTHS)

    with tqdm(total=total_layers, desc="      --> Sampling flood layers") as pbar:
        for dataset_name, folder_name, file_prefix in (
            ("rofrs", "RoFRS", "rofrs_4band"),
            ("rofsw", "RoFSW", "rofsw"),
        ):
            for depth in FLOOD_DEPTHS:
                depth_text = str(depth).replace(".", "_")
                pbar.set_postfix_str(f"{dataset_name.upper()} {depth}m")

                folder = data_dir / folder_name / f"{file_prefix}_{depth_text}m_depth"
                shapefiles = list(folder.glob("*.shp"))
                if not shapefiles:
                    print(f"      --> Warning: Raw flood shapefile not found in: {folder}. Skipping.")
                    pbar.update(1)
                    continue

                shp_path = shapefiles[0]

                if HAS_PYOGRIO:
                    shp_info = pyogrio.read_info(shp_path)
                    shp_crs = shp_info["crs"]
                else:
                    import fiona
                    with fiona.open(shp_path) as src:
                        shp_crs = src.crs

                minx, miny, maxx, maxy = result.total_bounds
                geom_box = box(minx, miny, maxx, maxy)

                shp_crs_obj = None
                if shp_crs is not None:
                    try:
                        shp_crs_obj = pyproj.CRS.from_user_input(shp_crs)
                        if result.crs != shp_crs_obj:
                            project = pyproj.Transformer.from_crs(result.crs, shp_crs_obj, always_xy=True).transform
                            geom_box = transform(project, geom_box)
                    except Exception as e:
                        print(f"CRS conversion failed for {shp_path}: {e}")

                bbox = geom_box.buffer(200.0).bounds

                read_kwargs = {"bbox": bbox}
                if HAS_PYOGRIO:
                    read_kwargs["engine"] = "pyogrio"

                try:
                    flood = gpd.read_file(shp_path, **read_kwargs)
                except Exception as e:
                    print(f"Error reading {shp_path}: {e}")
                    flood = gpd.GeoDataFrame(geometry=[])

                if not flood.empty:
                    if flood.crs is None and shp_crs_obj is not None:
                        try:
                            flood.set_crs(shp_crs_obj, inplace=True)
                        except:
                            pass
                    if flood.crs is None:
                        raise ValueError(f"Raw flood layer has no CRS: {shp_path}")

                    if flood.crs != result.crs:
                        flood = flood.to_crs(result.crs)

                    flood = flood.loc[flood.geometry.notna() & ~flood.geometry.is_empty]

                    prob_col = None
                    for col in flood.columns:
                        if col.lower() in ["prob_4band", "prob", "probability", "risk_level", "risk", "suitability"]:
                            prob_col = col
                            break
                    
                    if not prob_col:
                        for col in flood.select_dtypes(include=['object', 'str', 'string']).columns:
                            if flood[col].astype(str).str.contains('high|medium|low', case=False, na=False).any():
                                prob_col = col
                                break

                    if not flood.empty:
                        matches = gpd.sjoin(
                            result[["geometry"]],
                            flood,
                            how="left",
                            predicate="intersects",
                        )
                        matches = matches[matches["index_right"].notna()]

                        if prob_col and not matches.empty:
                            def score_prob(val):
                                val = str(val).lower()
                                if 'high' in val: return 4
                                if 'medium' in val or 'med' in val: return 3
                                if 'very' in val and 'low' in val: return 1
                                if 'low' in val: return 2
                                return 0
                            
                            matches['prob_score'] = matches[prob_col].apply(score_prob)
                            
                            best_probs = matches.groupby(matches.index)['prob_score'].max()
                            best_probs = best_probs[best_probs > 0]
                            
                            reverse_map = {4: "High", 3: "Medium", 2: "Low", 1: "Very Low"}
                            for idx, score in best_probs.items():
                                result.at[idx, f"{dataset_name}_{depth_text}m"] = reverse_map[score]
                        else:
                            for idx in matches.index.unique():
                                result.at[idx, f"{dataset_name}_{depth_text}m"] = "High"

                pbar.update(1)

            tier_thresholds = {"high": 4, "med": 3, "low": 2}
            
            for tier, min_score in tier_thresholds.items():
                result[f"{dataset_name}_{tier}"] = np.nan 
                
                for idx in result.index:
                    max_valid_depth = np.nan
                    
                    for d in FLOOD_DEPTHS:
                        d_text = str(d).replace(".", "_")
                        val = result.at[idx, f"{dataset_name}_{d_text}m"]
                        
                        score = 0
                        if val == "High": score = 4
                        elif val == "Medium": score = 3
                        elif val == "Low": score = 2
                        elif val == "Very Low": score = 1
                        
                        if score >= min_score:
                            max_valid_depth = d
                            
                    if pd.notnull(max_valid_depth):
                        result.at[idx, f"{dataset_name}_{tier}"] = max_valid_depth

    return result


def compute_terrain_rasters(elevation: np.ndarray, cell_size_x: float, cell_size_y: float, nodata_val=None):
    nan_mask = np.isnan(elevation)
    if nodata_val is not None:
        nan_mask |= (elevation == nodata_val)
        elevation = np.where(elevation == nodata_val, np.nan, elevation)

    mean_val = float(np.nanmean(elevation)) if not np.all(nan_mask) else 0.0
    elev_filled = np.nan_to_num(elevation, nan=mean_val)

    kernel_x = np.array([[-1, 0, 1],
                         [-2, 0, 2],
                         [-1, 0, 1]], dtype=float) / (8.0 * cell_size_x)

    kernel_y = np.array([[ 1,  2,  1],
                         [ 0,  0,  0], 
                         [-1, -2, -1]], dtype=float) / (8.0 * cell_size_y)

    dz_dx = convolve2d(elev_filled, kernel_x, mode="same", boundary="symm")
    dz_dy = convolve2d(elev_filled, kernel_y, mode="same", boundary="symm")

    slope_riserun = np.sqrt(dz_dx**2 + dz_dy**2)
    slope_deg = np.degrees(np.arctan(slope_riserun))

    slope_deg[nan_mask] = np.nan
    slope_riserun[nan_mask] = np.nan

    smoothed = uniform_filter(elev_filled, size=5)
    depression_proxy = np.maximum(0, smoothed - elev_filled)
    cell_area = cell_size_x * cell_size_y
    sca = cell_area * (1.0 + uniform_filter(depression_proxy, size=9))

    tan_beta = np.maximum(slope_riserun, 1e-4)
    twi = np.log((sca / cell_size_x) / tan_beta)
    spi = (sca / cell_size_x) * tan_beta

    twi[nan_mask] = np.nan
    spi[nan_mask] = np.nan

    return slope_deg, twi, spi


def sample_dtm_windowed(gdf: gpd.GeoDataFrame, dtm_path: str | Path) -> gpd.GeoDataFrame:
    dtm_path = Path(dtm_path)
    if not dtm_path.exists():
        raise FileNotFoundError(f"DTM raster not found at: {dtm_path}")

    print(f"\n[2/6] Reading DTM Window: {dtm_path.name}")
    with rasterio.open(dtm_path) as src:
        reprojected = gdf.to_crs(src.crs) if gdf.crs != src.crs else gdf

        minx, miny, maxx, maxy = reprojected.total_bounds
        buffer = 500.0
        minx, miny = max(minx - buffer, src.bounds.left), max(miny - buffer, src.bounds.bottom)
        maxx, maxy = min(maxx + buffer, src.bounds.right), min(maxy + buffer, src.bounds.top)

        window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
        window = window.round_offsets().round_lengths()
        window_transform = rasterio.windows.transform(window, src.transform)

        print(f"      --> Cropped window size: {int(window.width)} x {int(window.height)} pixels")

        elevation = src.read(1, window=window).astype(float)
        dx = abs(window_transform.a)
        dy = abs(window_transform.e)

        print("      --> Computing ArcGIS-Standard Horn Slope, TWI, and SPI matrices...")
        slope_deg, twi_arr, spi_arr = compute_terrain_rasters(elevation, dx, dy, src.nodata)

        inv_transform = ~window_transform
        elev_vals, slope_vals, twi_vals, spi_vals = [], [], [], []

        for geom in tqdm(reprojected.geometry, desc="      --> Sampling terrain points", total=len(reprojected)):
            if geom is None or geom.is_empty:
                elev_vals.append(0.0)
                slope_vals.append(0.0)
                twi_vals.append(0.0)
                spi_vals.append(0.0)
                continue

            c_float, r_float = inv_transform * (geom.x, geom.y)
            r, c = int(round(r_float)), int(round(c_float))

            if 0 <= r < elevation.shape[0] and 0 <= c < elevation.shape[1]:
                e_val = elevation[r, c]
                s_val = slope_deg[r, c]
                t_val = twi_arr[r, c]
                sp_val = spi_arr[r, c]

                elev_vals.append(round(float(e_val), 2) if np.isfinite(e_val) else 0.0)
                slope_vals.append(round(float(s_val), 2) if np.isfinite(s_val) else 0.0)
                twi_vals.append(round(float(t_val), 3) if np.isfinite(t_val) else 0.0)
                spi_vals.append(round(float(sp_val), 3) if np.isfinite(sp_val) else 0.0)
            else:
                elev_vals.append(0.0)
                slope_vals.append(0.0)
                twi_vals.append(0.0)
                spi_vals.append(0.0)

    gdf["elevation_m"] = elev_vals
    gdf["slope"] = slope_vals
    gdf["twi"] = twi_vals
    gdf["spi"] = spi_vals
    return gdf


# hydraulic and hazard helpers

def get_debris_factor(depth, velocity, df_class):
    if pd.isnull(depth) or depth <= 0:
        return 0.0

    if depth > 0.75 or velocity > 2.0:
        if df_class == "Pasture/Arable":
            return 0.5
        elif df_class == "Woodland":
            return 1.0
        elif df_class == "Urban":
            return 1.0

    elif depth > 0.25 and depth <= 0.75:
        if df_class == "Pasture/Arable":
            return 0.0
        elif df_class == "Woodland":
            return 0.5
        elif df_class == "Urban":
            return 1.0
            
    elif depth <= 0.25:
        return 0.0

    return 0.0


def calculate_manning_velocity(depth, slope_dim, n):
    if pd.isnull(depth) or depth <= 0 or slope_dim <= 0 or n <= 0:
        return 0.0
    return round((1.0 / n) * (depth ** (2.0 / 3.0)) * (math.sqrt(slope_dim)), 3)


def classify_hazard(hr):
    if pd.isnull(hr) or hr <= 0:
        return None, None, None
    if hr < 0.75:
        return "Low", 1, 0.0
    elif hr <= 1.25:
        return "Moderate", 2, round((2 - 1) / 3.0, 3)
    elif hr <= 2.5:
        return "Significant", 3, round((3 - 1) / 3.0, 3)
    else:
        return "Extreme", 4, 1.0


def load_and_filter_substations(geometry_path, boundary_geojson_path=None):
    print("[0/6] Loading Substation geometries and attributes...")
    geometry = gpd.read_file(geometry_path)

    geometry.columns = [c.strip().lower() for c in geometry.columns]

    required_columns = {"site_name", "customer_numbers", "site_type"}
    missing_columns = required_columns.difference(geometry.columns)
    if missing_columns:
        raise ValueError(
            f"Substation GeoJSON is missing required columns: {sorted(missing_columns)}"
        )

    geometry["site_name"] = geometry["site_name"].astype(str).str.strip().str.upper()
    gdf = gpd.GeoDataFrame(geometry, geometry="geometry", crs=geometry.crs)
    print(f"      --> Total raw substations loaded: {len(gdf)}")

    if boundary_geojson_path and Path(boundary_geojson_path).exists():
        print(f"\n[1/6] Restricting to Boundary: {Path(boundary_geojson_path).name}")
        boundary_gdf = gpd.read_file(boundary_geojson_path)
        if boundary_gdf.crs != gdf.crs:
            boundary_gdf = boundary_gdf.to_crs(gdf.crs)

        boundary_poly = (
            boundary_gdf.geometry.union_all()
            if hasattr(boundary_gdf.geometry, "union_all")
            else boundary_gdf.geometry.union_all
        )
        gdf = gdf[gdf.geometry.within(boundary_poly)].copy().reset_index(drop=True)
        print(f"      --> Kept {len(gdf)} substations inside study area.")

    return gdf


# main processing pipeline

def process_substation_data(
    output_geojson_path,
    dtm_tif_path,
    boundary_geojson_path=None,
    weights=None,
    geometry_path=None,
):
    if weights is None:
        weights = DEFAULT_WEIGHTS

    gdf = load_and_filter_substations(geometry_path, boundary_geojson_path)
    gdf = sample_dtm_windowed(gdf, dtm_tif_path)

    print("\n[3/6] Sampling raw RoFRS and RoFSW polygon layers...")
    gdf = load_raw_flood_depths(gdf, Path(geometry_path).parent)

    print("\n[4/6] Calculating Roughness, Terrain Norms, and Consequence...")
    gdf["slope_dimensionless"] = pd.to_numeric(gdf["slope"], errors="coerce").apply(
        lambda deg: math.tan(math.radians(deg)) if pd.notnull(deg) else 0.0
    )

    if "class" not in gdf:
        gdf["class"] = "Pasture/Arable"
    gdf["mannings"] = gdf["class"].apply(lambda c: UKCEH_MAPPING.get(c, {}).get("mannings", 0.035))
    gdf["df_class"] = gdf["class"].apply(lambda c: UKCEH_MAPPING.get(c, {}).get("df_class", "Pasture/Arable"))

    def parse_customers(val):
        if pd.isnull(val):
            return 0
        s = str(val).strip()
        if "≤" in s or "<=" in s or s == "≤5" or "?5" in s:
            return 5
        try:
            return float(s)
        except ValueError:
            return 5

    numeric_customers = gdf["customer_numbers"].apply(parse_customers)
    gt_5 = numeric_customers[numeric_customers > 5]
    c_p25, c_p50, c_p75 = np.percentile(gt_5, [25, 50, 75]) if len(gt_5) > 0 else (22, 103, 224)

    def classify_customer(val):
        c = parse_customers(val)
        if c <= 5:
            return 1
        elif c <= c_p25:
            return 2
        elif c <= c_p50:
            return 3
        elif c <= c_p75:
            return 4
        else:
            return 5

    gdf["customers_class"] = gdf["customer_numbers"].apply(classify_customer)
    gdf["customers_class_norm"] = (gdf["customers_class"] - 1) / 4.0

    def classify_terrain(values):
        valid = pd.to_numeric(values, errors="coerce").dropna()
        if valid.empty or valid.nunique() <= 1:
            classes = pd.Series(1.0, index=values.index)
        else:
            bins = [-np.inf] + list(np.percentile(valid, [20, 40, 60, 80])) + [np.inf]
            classes = pd.cut(pd.to_numeric(values, errors="coerce"), bins=bins, labels=[1, 2, 3, 4, 5]).astype(float)
        return classes, (classes - 1) / 4.0

    gdf["twi_class"], gdf["twi_class_norm"] = classify_terrain(gdf["twi"])
    gdf["spi_class"], gdf["spi_class_norm"] = classify_terrain(gdf["spi"])
    gdf["combined_norm"] = (gdf["twi_class_norm"] + gdf["spi_class_norm"]) / 2.0

    print("\n[5/6] Calculating Multi-Tier Flood Hazards (High, Medium, Low)...")
    for tier in tqdm(TIERS, desc="      --> Processing return periods"):
        for prefix in ("rofrs", "rofsw"):
            column = f"{prefix}_{tier}"
            if column not in gdf:
                gdf[column] = np.nan
            gdf[column] = pd.to_numeric(gdf[column], errors="coerce")

        rof_column = f"rof_{tier}"
        gdf[rof_column] = gdf[[f"rofrs_{tier}", f"rofsw_{tier}"]].max(axis=1)

        gdf[f"velocity_{tier}"] = gdf.apply(
            lambda row: calculate_manning_velocity(row[f"rof_{tier}"], row["slope_dimensionless"], row["mannings"])
            if pd.notnull(row[f"rof_{tier}"]) else None,
            axis=1,
        )

        gdf[f"df_{tier}"] = gdf.apply(
            lambda row: get_debris_factor(row[f"rof_{tier}"], row[f"velocity_{tier}"], row["df_class"])
            if pd.notnull(row[f"rof_{tier}"]) else None,
            axis=1,
        )

        gdf[f"hazard_{tier}"] = gdf.apply(
            lambda row: round(row[f"rof_{tier}"] * (row[f"velocity_{tier}"] + 0.5) + row[f"df_{tier}"], 3)
            if pd.notnull(row[f"rof_{tier}"]) else None,
            axis=1,
        )

        hazard_classes = gdf[f"hazard_{tier}"].apply(classify_hazard)
        gdf[f"degree_{tier}"] = [hc[0] for hc in hazard_classes]
        gdf[f"degree_{tier}_class"] = [hc[1] for hc in hazard_classes]
        gdf[f"degree_{tier}_norm"] = [hc[2] for hc in hazard_classes]

        def get_site_type_class(row, t=tier):
            if pd.isnull(row[f"rof_{t}"]):
                return None
            
            st = str(row.get("site_type", "")).lower()
            df_val = row.get(f"df_{t}")
            deg_val = row.get(f"degree_{t}")
            
            if "pole" in st and df_val == 1.0:
                return 2
            if "ground" in st and deg_val == "Extreme":
                return 2
            
            return 1

        gdf[f"site_type_class_{tier}"] = gdf.apply(get_site_type_class, axis=1)
        gdf[f"site_type_norm_{tier}"] = gdf[f"site_type_class_{tier}"].apply(
            lambda c: 1.0 if c == 2 else (0.0 if c == 1 else None)
        )

    print("\n[6/6] Computing Final MCA Weighted Risk Scores & Exporting...")
    for tier in TIERS:
        def calc_score(row, t=tier):
            if pd.isnull(row[f"rof_{t}"]):
                return None
                
            p_norm = row.get(f"degree_{t}_norm", 0.0) or 0.0
            t_norm = row.get("combined_norm", 0.0) or 0.0
            v_norm = row.get(f"site_type_norm_{t}", 0.0) or 0.0
            c_norm = row.get("customers_class_norm", 0.0) or 0.0

            return round(
                weights["physical"] * p_norm
                + weights["terrain"] * t_norm
                + weights["vulnerability"] * v_norm
                + weights["consequence"] * c_norm,
                4,
            )

        gdf[f"scores_{tier}"] = gdf.apply(calc_score, axis=1)

    # export GeoJSON
    generated_columns = [
        "elevation_m",
        "slope",
        "slope_dimensionless",
        "twi",
        "spi",
        "twi_class",
        "twi_class_norm",
        "spi_class",
        "spi_class_norm",
        "combined_norm",
        "mannings",
        "df_class",
        "customers_class",
        "customers_class_norm",
    ]

    for tier in TIERS:
        generated_columns.extend([
            f"rof_{tier}",
            f"rofsw_{tier}",
            f"rofrs_{tier}",
            f"velocity_{tier}",
            f"df_{tier}",
            f"hazard_{tier}",
            f"degree_{tier}",
            f"degree_{tier}_class",
            f"degree_{tier}_norm",
            f"site_type_class_{tier}",
            f"site_type_norm_{tier}",
            f"scores_{tier}",
        ])

    flood_columns = [
        column for column in gdf.columns
        if column.startswith(("rofsw_", "rofrs_", "rof_"))
    ]
    generated_columns.extend(flood_columns)
    generated_columns = list(dict.fromkeys(generated_columns))

    gdf = gdf.loc[:, ~gdf.columns.duplicated()].copy()
    keep_columns = [
        column for column in gdf.columns
        if column != gdf.geometry.name
    ] + [gdf.geometry.name]

    output_gdf = gdf[keep_columns]
    Path(output_geojson_path).parent.mkdir(parents=True, exist_ok=True)
    output_gdf.to_file(output_geojson_path, driver="GeoJSON")
    print(f"DONE: Exported {len(output_gdf)} records to: {output_geojson_path}\n")


# execution entry point
if __name__ == "__main__":
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"

    process_substation_data(
        geometry_path=data_dir / "substation_sites_list.geojson",
        boundary_geojson_path=data_dir / "county_durham.geojson",
        dtm_tif_path=data_dir / "LIDAR_Composite_10m_DTM_2022.tif",
        output_geojson_path=data_dir / "substation_sites_processed.geojson",
    )
