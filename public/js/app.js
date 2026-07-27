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
const powerCutGroup = L.featureGroup().addTo(map); 

const durhamGeoJsonPath = 'public/data/county_durham.geojson';
const substationsGeoJsonPath = 'public/data/substation_sites_list.geojson';

let durhamBoundary; 

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

        durhamBoundary = durhamData.type === 'FeatureCollection' 
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

                const marker = L.circleMarker([lat, lon], {
                    radius: 6,
                    className: 'substation-marker'
                });

                // Substation Details Popup
                marker.bindPopup(`
                    <div class="popup-content popup-substation">
                        <h4>${props.site_name || 'Unknown Substation'}</h4>
                        <div><b>ID:</b> ${props.substation_id || 'N/A'}</div>
                        <div><b>Type:</b> ${props.site_type || 'N/A'}</div>
                        <div><b>Voltage:</b> ${props.primary_voltage_kv ?? 'N/A'} kV / ${props.secondary_voltage_kv ?? 'N/A'} kV</div>
                        <div><b>Rating:</b> ${props.transformer_rating_kva ?? 'N/A'} kVA</div>
                        <div><b>Customers Fed:</b> ${props.customer_numbers || 'N/A'}</div>
                        <div><b>Upstream:</b> ${props.upstream_substation || 'N/A'}</div>
                        <div><b>Postcode:</b> ${props.postcode || 'N/A'}</div>
                    </div>
                `);

                markerGroup.addLayer(marker);
                }
            }
        });

        // Update counter badge
        const counterContainer = document.getElementById('counter');
        counterContainer.className = 'badge-container'; 
        counterContainer.innerHTML = `
            <div id="powercut-counter" class="badge badge-red">0 Power Cuts</div>
            <div class="badge badge-blue">${count} Substations Mapped</div>
        `;

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

        // Fetch live power cuts data, and then set interval
        await fetchLivePowerCuts();
        setInterval(fetchLivePowerCuts, 300000); // every 5 minutes

    } catch (err) {
        console.error("Map setup failed:", err);
        document.getElementById('counter').innerText = err.message;
    }
}

async function fetchLivePowerCuts() {
    try {
        const url = 'https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/datasets/live-power-cuts-data/exports/geojson?lang=en&timezone=Europe%2FLondon';
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        
        const data = await response.json();
        powerCutGroup.clearLayers();
        let activePowerCuts = 0; 
        
        L.geoJSON(data, {
            filter: feature => feature.geometry?.coordinates && turf.booleanPointInPolygon(feature, durhamBoundary),
            pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
                radius: 8, fillColor: "#e74c3c", color: "#900C3F", weight: 2, opacity: 1, fillOpacity: 0.9, className: 'live-power-cut-marker'
            }),
            onEachFeature: (feature, layer) => {
                activePowerCuts++; 
                const props = feature.properties || {};
                const postcodes = Array.isArray(props.postcode) ? props.postcode.join(', ') : (props.postcode || 'N/A');
                
                // Power Cut Details Popup
                layer.bindPopup(`
                    <div class="popup-content popup-powercut">
                        <h4>Live Power Cut</h4>
                        <div><b>Reference:</b> ${props.reference || 'N/A'}</div>
                        <div><b>Type:</b> ${props.type || 'N/A'}</div>
                        <div><b>Status:</b> ${props.natureofoutage || 'Information unavailable'}</div>
                        <div><b>Affected Postcodes:</b> ${postcodes}</div>
                    </div>
                `);
            }
        }).addTo(powerCutGroup);

        const pcCounter = document.getElementById('powercut-counter');
        if (pcCounter) pcCounter.innerText = `${activePowerCuts} Power Cuts`;

    } catch (err) {
        console.error("Failed to load live power cut data:", err);
    }
}

initMap();
