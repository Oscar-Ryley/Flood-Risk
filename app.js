// Initialize Map centered on Durham area
const map = L.map('map').setView([54.7761, -1.5733], 10);

// Add OpenStreetMap base tile layer
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
}).addTo(map);

// Feature groups
const boundaryGroup = L.featureGroup().addTo(map);
const markerGroup = L.featureGroup().addTo(map);

const durhamGeoJsonPath = 'data/county_durham.geojson';
const substationsGeoJsonPath = 'data/substation_sites_list.geojson';

async function initMap() {
    try {
        const boundaryResp = await fetch(durhamGeoJsonPath);
        if (!boundaryResp.ok) throw new Error(`Missing ${durhamGeoJsonPath} (HTTP ${boundaryResp.status})`);

        const substationsResp = await fetch(substationsGeoJsonPath);
        if (!substationsResp.ok) throw new Error(`Missing ${substationsGeoJsonPath} (HTTP ${substationsResp.status})`);

        const durhamData = await boundaryResp.json();
        const substationsData = await substationsResp.json();

        // Draw County Durham boundary on map
        L.geoJSON(durhamData, {
            style: {
                color: '#68246d',
                weight: 2.5,
                fillColor: '#68246d',
                fillOpacity: 0.08,
                dashArray: '5, 5'
            }
        }).addTo(boundaryGroup);

        const durhamBoundary = durhamData.type === 'FeatureCollection' 
            ? durhamData.features[0] 
            : durhamData;

        markerGroup.clearLayers();
        let count = 0;

        const features = substationsData.features || [];

        features.forEach(feature => {
            const coords = feature.geometry && feature.geometry.coordinates;
            if (!coords || coords.length < 2) return;

            const [lon, lat] = coords; // GeoJSON coordinates are [longitude, latitude]

            if (!isNaN(lat) && !isNaN(lon)) {
                // Point-in-polygon check against County Durham boundary
                const isInside = turf.booleanPointInPolygon(feature, durhamBoundary);

                if (isInside) {
                    count++;

                    const props = feature.properties || {};

                    // Direct property mapping from your GeoJSON schema
                    const siteName = props.site_name || 'Unknown Substation';
                    const id = props.substation_id || 'N/A';
                    const siteType = props.site_type || 'N/A';
                    const primaryVolt = props.primary_voltage_kv != null ? `${props.primary_voltage_kv} kV` : 'N/A';
                    const secondaryVolt = props.secondary_voltage_kv != null ? `${props.secondary_voltage_kv} kV` : 'N/A';
                    const rating = props.transformer_rating_kva != null ? `${props.transformer_rating_kva} kVA` : 'N/A';
                    const upstream = props.upstream_substation || 'N/A';
                    const postcode = props.postcode || 'N/A';
                    const customers = props.customer_numbers || 'N/A';

                    // Create Circle Marker
                    const marker = L.circleMarker([lat, lon], {
                        radius: 6,
                        className: 'substation-marker'
                    });

                    marker.bindPopup(`
                        <div class="popup-content">
                            <h4>${siteName}</h4>
                            <div><b>ID:</b> ${id}</div>
                            <div><b>Type:</b> ${siteType}</div>
                            <div><b>Voltage:</b> ${primaryVolt} / ${secondaryVolt}</div>
                            <div><b>Rating:</b> ${rating}</div>
                            <div><b>Customers Fed:</b> ${customers}</div>
                            <div><b>Upstream:</b> ${upstream}</div>
                            <div><b>Postcode:</b> ${postcode}</div>
                        </div>
                    `);

                    markerGroup.addLayer(marker);
                }
            }
        });

        // Update counter badge
        document.getElementById('counter').innerText = `${count} Substations Mapped`;

        // Fit map view to County Durham boundary
        if (boundaryGroup.getLayers().length > 0) {
            map.fitBounds(boundaryGroup.getBounds().pad(0.05));
        }

        // Risk of Flooding from Surface Water Data added ontop of the map as a png
        const surfaceWaterFloodLayer = L.tileLayer.wms(
            'https://environment.data.gov.uk/spatialdata/nafra2-risk-of-flooding-from-surface-water/wms', 
            {
                layers: 'rofsw',
                format: 'image/png',
                transparent: true,
                opacity: 0.8,
                attribution: '&copy; Environment Agency',
                
                minZoom: 6,
                maxZoom: 19,
                maxNativeZoom: 15    // Stretches images at closer zoom levels
            }
        ).addTo(map); 


    } catch (err) {
        console.error("Map setup failed:", err);
        document.getElementById('counter').innerText = err.message;
    }
}

initMap();
