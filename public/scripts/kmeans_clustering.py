import os
from pathlib import Path
import warnings

import geopandas as gpd
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np
from scipy.cluster.vq import kmeans2, whiten

warnings.filterwarnings("ignore")

def run_kmeans_clustering():
    script_dir = Path(__file__).resolve().parent
    public_dir = script_dir.parent
    data_path = public_dir / "data" / "substation_sites_processed.geojson"
    img_dir = public_dir / "data" / "images"
    img_path = img_dir / "kmeans_substation_clusters.png"
    shaped_img_path = img_dir / "kmeans_substation_clusters_risk_shapes.png"
    classified_img_path = img_dir / "kmeans_classified_substation_clusters.png"

    # Ensure the images directory exists
    img_dir.mkdir(parents=True, exist_ok=True)

    if not data_path.exists():
        raise FileNotFoundError(f"Processed GeoJSON not found at: {data_path}")

    # load the GeoJSON data
    print("[1/3] Loading and preparing data...")
    print(f"      --> Loading data from: {data_path.name}")
    gdf = gpd.read_file(data_path)

    # select features to cluster by
    # We use physical terrain (elevation, slope), customer impact, and the high-tier flood risk score
    features = ['elevation_m', 'slope', 'customers_class_norm', 'scores_high']

    print(f"      --> Extracting features for clustering: {features}")
    
    # Extract the subset and fill any unexpected NaNs with 0.0 to prevent SciPy math errors
    cluster_data = gdf[features].copy().fillna(0.0)

    # Convert to a standard numpy array (float)
    data_matrix = cluster_data.values.astype(float)

    # Normalize data - called whitening in scipy
    print("      --> Normalizing the feature data...")
    whitened_data = whiten(data_matrix)

    # Perform K-Means Clustering using SciPy
    k = 4
    print(f"Running SciPy K-Means clustering (K={k})...")
    
    # kmeans2 returns:
    # - centroids: the coordinates of the cluster centers
    # - labels: an array mapping each substation to its cluster index (0, 1, 2, or 3)
    centroids, labels = kmeans2(whitened_data, k, minit='points', seed=42)

    # Assign the resulting labels back to our GeoDataFrame
    gdf['cluster'] = labels

    # Generate Graph Visualizations
    print("\n[3/3] Generating output graphs...")
    
    # Create a 1x2 grid of plots
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    # Define a custom colormap using the requested colors
    cmap = ListedColormap(['#DC267F', '#785EF0', '#648FFF', '#FFB000'])


    # --- Plot A: Geographic Layout ---
    # Plotting standard Longitude (X) and Latitude (Y)
    x = gdf.geometry.x
    y = gdf.geometry.y

    scatter1 = ax1.scatter(x, y, c=gdf['cluster'], cmap=cmap, s=15, alpha=0.7, edgecolors='none')
    ax1.set_title('Substation Clusters: Geographic Distribution', fontsize=14, pad=10, fontweight='bold')
    ax1.set_xlabel('Longitude', fontsize=11)
    ax1.set_ylabel('Latitude', fontsize=11)
    ax1.grid(True, linestyle='--', alpha=0.5)

    # --- Plot B: Feature Space (Elevation vs Slope) ---
    # Visualizing how the clustering algorithm grouped the physical characteristics
    scatter2 = ax2.scatter(
        gdf['elevation_m'], 
        gdf['slope'],
        c=gdf['cluster'], 
        cmap=cmap, 
        s=20, 
        alpha=0.7,
        edgecolors='black',
        linewidth=0.3
    )
    ax2.set_title('Substation Clusters: Elevation vs Slope', fontsize=14, pad=10, fontweight='bold')
    ax2.set_xlabel('Elevation (m)', fontsize=11)
    ax2.set_ylabel('Slope (Degrees)', fontsize=11)
    ax2.grid(True, linestyle='--', alpha=0.5)

    # Add a unified colorbar to act as a legend (with adjusted padding to stop it overlapping the graph!)
    cbar = fig.colorbar(scatter2, ax=[ax1, ax2], ticks=range(k), fraction=0.03, pad=0.04, aspect=30)
    cbar.set_label('SciPy K-Means Cluster Label', fontsize=12, fontweight='bold')

    # Add a super title
    fig.suptitle('Substation Risk & Terrain Clusters (SciPy K-Means)', fontsize=18, fontweight='bold', y=1.02)

    # Clean layout and save to the images folder
    plt.tight_layout()
    plt.savefig(img_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"      --> Cluster graph saved to: {img_path}")

    # Create a second copy using marker shapes to show final risk categories.
    # Cluster colours are retained so both images can be compared directly.
    risk_score = gdf['final_risk_score']
    risk_groups = [
        ("No risk", risk_score.isna(), 'o'),
        ("Low risk", risk_score.notna() & (risk_score > 0) & (risk_score < 0.5), 's'),
        ("Medium risk", (risk_score >= 0.5) & (risk_score < 0.75), '^'),
        ("High risk", risk_score >= 0.75, '*'),
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    for label, mask, marker in risk_groups:
        if not mask.any():
            continue
        ax1.scatter(
            x[mask], y[mask], c=gdf.loc[mask, 'cluster'], cmap=cmap,
            vmin=0, vmax=k - 1, marker=marker, s=28 if marker != '*' else 55,
            alpha=0.05 if marker == 'o' else 0.7, edgecolors='none', label=label
        )
        ax2.scatter(
            gdf.loc[mask, 'elevation_m'], gdf.loc[mask, 'slope'],
            c=gdf.loc[mask, 'cluster'], cmap=cmap, vmin=0, vmax=k - 1,
            marker=marker, s=32 if marker != '*' else 65,
            alpha=0.05 if marker == 'o' else 0.7, edgecolors='black', linewidth=0.3, label=label
        )

    ax1.set_title('Substation Clusters: Geographic Distribution', fontsize=14, pad=10, fontweight='bold')
    ax1.set_xlabel('Longitude', fontsize=11)
    ax1.set_ylabel('Latitude', fontsize=11)
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend(title='Final risk category')

    ax2.set_title('Substation Clusters: Elevation vs Slope', fontsize=14, pad=10, fontweight='bold')
    ax2.set_xlabel('Elevation (m)', fontsize=11)
    ax2.set_ylabel('Slope (Degrees)', fontsize=11)
    ax2.grid(True, linestyle='--', alpha=0.5)

    cbar = fig.colorbar(scatter2, ax=[ax1, ax2], ticks=range(k), fraction=0.03, pad=0.04, aspect=30)
    cbar.set_label('SciPy K-Means Cluster Label', fontsize=12, fontweight='bold')
    fig.suptitle('Substation Risk & Terrain Clusters: Risk Shapes', fontsize=18, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(shaped_img_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"      --> Risk-shape graph saved to: {shaped_img_path}")

    # Run a separate clustering analysis using classified substations only.
    classified_gdf = gdf[gdf['final_risk_score'].notna()].copy()
    classified_data = classified_gdf[features].fillna(0.0).values.astype(float)
    classified_whitened = whiten(classified_data)
    classified_centroids, classified_labels = kmeans2(
        classified_whitened, k, minit='points', seed=42
    )
    classified_gdf['cluster'] = classified_labels

    classified_x = classified_gdf.geometry.x
    classified_y = classified_gdf.geometry.y
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

    scatter1 = ax1.scatter(
        classified_x, classified_y, c=classified_gdf['cluster'], cmap=cmap,
        vmin=0, vmax=k - 1, s=15, alpha=0.7, edgecolors='none'
    )
    ax1.set_title('Classified Substations: Geographic Clusters', fontsize=14, pad=10, fontweight='bold')
    ax1.set_xlabel('Longitude', fontsize=11)
    ax1.set_ylabel('Latitude', fontsize=11)
    ax1.grid(True, linestyle='--', alpha=0.5)

    scatter2 = ax2.scatter(
        classified_gdf['elevation_m'], classified_gdf['slope'],
        c=classified_gdf['cluster'], cmap=cmap, vmin=0, vmax=k - 1,
        s=20, alpha=0.7, edgecolors='black', linewidth=0.3
    )
    ax2.set_title('Classified Substations: Elevation vs Slope', fontsize=14, pad=10, fontweight='bold')
    ax2.set_xlabel('Elevation (m)', fontsize=11)
    ax2.set_ylabel('Slope (Degrees)', fontsize=11)
    ax2.grid(True, linestyle='--', alpha=0.5)

    cbar = fig.colorbar(scatter2, ax=[ax1, ax2], ticks=range(k), fraction=0.03, pad=0.04, aspect=30)
    cbar.set_label('SciPy K-Means Cluster Label', fontsize=12, fontweight='bold')
    fig.suptitle('Classified Substation Risk & Terrain Clusters (SciPy K-Means)', fontsize=18, fontweight='bold', y=1.02)
    plt.tight_layout()
    plt.savefig(classified_img_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"      --> Classified-only graph saved to: {classified_img_path}")

if __name__ == "__main__":
    run_kmeans_clustering()
