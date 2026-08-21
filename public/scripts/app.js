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
const csvMarkerGroup = L.featureGroup().addTo(map);
const powerCutGroup = L.featureGroup().addTo(map); 

const durhamGeoJsonPath = 'public/data/county_durham.geojson';
const substationsGeoJsonPath = 'public/data/substation_sites_list.geojson';
const substationsCsvPath = 'public/data/substation_sites_filtered.csv';
const SUBSTATION_POPUP_WIDTH_WITH_CSV = 640;
const substationPopupOptionsDefault = { maxWidth: 10000 };
const powerCutPopupOptions = { 
    maxWidth: 800, 
    minWidth: 450,
    className: 'powercut-popup-container' 
};

let durhamBoundary; 

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function parseCsvLine(line) {
    const cells = [];
    let current = '';
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
        const char = line[i];

        if (char === '"') {
            if (inQuotes && line[i + 1] === '"') {
                current += '"';
                i++;
            } else {
                inQuotes = !inQuotes;
            }
            continue;
        }

        if (char === ',' && !inQuotes) {
            cells.push(current);
            current = '';
            continue;
        }

        current += char;
    }

    cells.push(current);
    return cells;
}

function parseCsv(csvText) {
    const lines = csvText
        .split(/\r?\n/)
        .map(line => line.trimEnd())
        .filter(line => line.length > 0);

    if (lines.length < 2) {
        return { headers: [], rows: [] };
    }

    const headers = parseCsvLine(lines[0]);
    const rows = lines.slice(1).map(line => {
        const values = parseCsvLine(line);
        const row = {};

        headers.forEach((header, index) => {
            row[header] = values[index] ?? '';
        });

        return row;
    });

    return { headers, rows };
}

function normalizeId(value) {
    if (value === null || value === undefined || value === '') return '';
    const raw = String(value).trim();

    const numeric = Number(raw);
    if (!Number.isNaN(numeric) && Number.isFinite(numeric)) {
        return numeric.toFixed(0);
    }

    return raw;
}

function normalizeText(value) {
    return String(value || '').trim().toLowerCase();
}

function buildCsvLookup(rows) {
    const byId = new Map();
    const byNamePostcode = new Map();

    rows.forEach(row => {
        const id = normalizeId(row.Substation_ID);
        if (id) byId.set(id, row);

        const siteName = normalizeText(row.Site_Name);
        const postcode = normalizeText(row.Postcode);
        if (siteName && postcode) {
            byNamePostcode.set(`${siteName}|${postcode}`, row);
        }
    });

    return { byId, byNamePostcode };
}

const CSV_POPUP_FIELDS = [
    'slope',
    'slope_dimensionless',
    'class',
    'mannings',
    'df_class',
    'rofrs_0_2m',
    'rofrs_0_3m',
    'rofrs_0_6m',
    'rofrs_0_9m',
    'rofrs_1_2m',
    'rofsw_0_2m',
    'rofsw_0_3m',
    'rofsw_0_6m',
    'rofsw_0_9m',
    'rofsw_1_2m',
    'rofrs_high',
    'rofrs_med',
    'rofrs_low',
    'rofsw_high',
    'rofsw_med',
    'rofsw_low',
    'rof_high',
    'rof_med',
    'rof_low',
    'velocity_high',
    'velocity_med',
    'velocity_low',
    'df_high',
    'df_med',
    'df_low',
    'hazard_high',
    'hazard_med',
    'hazard_low',
    'degree_high',
    'degree_med',
    'degree_low'
];

function getSubstationRiskMeta(csvRow) {
    if (!csvRow) {
        return {
            label: 'Unclassified Risk',
            color: '#0078d4',
            background: 'rgba(0, 120, 212, 0.08)'
        };
    }

    const highRiskScore = parseRiskScore(csvRow.rof_high);
    const mediumRiskScore = parseRiskScore(csvRow.rof_med);
    const lowRiskScore = parseRiskScore(csvRow.rof_low);

    if (highRiskScore > 0) {
        return {
            label: 'High Risk',
            color: '#d62828',
            background: 'rgba(214, 40, 40, 0.08)'
        };
    }

    if (mediumRiskScore > 0) {
        return {
            label: 'Medium Risk',
            color: '#f77f00',
            background: 'rgba(247, 127, 0, 0.1)'
        };
    }

    if (lowRiskScore > 0) {
        return {
            label: 'Low Risk',
            color: '#2a9d8f',
            background: 'rgba(42, 157, 143, 0.1)'
        };
    }

    return {
        label: 'Unclassified Risk',
        color: '#0078d4',
        background: 'rgba(0, 120, 212, 0.08)'
    };
}

function getSubstationMarkerColor(csvRow) {
    return getSubstationRiskMeta(csvRow).color;
}

function formatCsvFieldLabel(fieldName) {
    return fieldName.replace(/_/g, ' ');
}

function buildCsvDetailsHtml(csvRow) {
    if (!csvRow) return '';

    const riskMeta = getSubstationRiskMeta(csvRow);
    const details = CSV_POPUP_FIELDS.map(field => {
        const value = csvRow[field];
        const displayValue = value === '' || value === undefined ? 'N/A' : value;
        return `<div class="popup-csv-item"><b>${escapeHtml(formatCsvFieldLabel(field))}:</b> ${escapeHtml(displayValue)}</div>`;
    }).join('');

    return `
        <div class="popup-csv-section" style="--risk-color: ${riskMeta.color}; --risk-background: ${riskMeta.background};">
            <div class="popup-csv-title">${escapeHtml(riskMeta.label)}</div>
            <div class="popup-csv-grid">
                ${details}
            </div>
        </div>
    `;
}

function parseRiskScore(value) {
    const num = Number(value);
    return Number.isFinite(num) ? num : 0;
}

function getSubstationPopupOptions(hasCsvData) {
    if (!hasCsvData) return substationPopupOptionsDefault;

    return {
        maxWidth: 680,
        minWidth: 320,
        className: 'popup-csv-scroll'
    };
}

function createSubstationCsvIcon(fillColor, fillOpacity = 0.9) {
    const starPath = 'M12 1.5 L14.7 8.2 L21.8 8.2 L16.1 12.8 L18.7 19.5 L12 15.2 L5.3 19.5 L7.9 12.8 L2.2 8.2 L9.3 8.2 Z';

    return L.divIcon({
        className: 'substation-marker-csv-icon',
        html: `
            <svg viewBox="0 0 24 24" width="18" height="18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
                <path d="${starPath}" fill="${fillColor}" fill-opacity="${fillOpacity}" stroke="#000000" stroke-width="1.5" stroke-linejoin="round"/>
            </svg>
        `,
        iconSize: [18, 18],
        iconAnchor: [9, 9],
        popupAnchor: [0, -8]
    });
}

async function initMap() {
    try {
        const boundaryResp = await fetch(durhamGeoJsonPath);
        if (!boundaryResp.ok) throw new Error(`Missing ${durhamGeoJsonPath} (HTTP ${boundaryResp.status})`);

        const substationsResp = await fetch(substationsGeoJsonPath);
        if (!substationsResp.ok) throw new Error(`Missing ${substationsGeoJsonPath} (HTTP ${substationsResp.status})`);

        const substationsCsvResp = await fetch(substationsCsvPath);
        if (!substationsCsvResp.ok) throw new Error(`Missing ${substationsCsvPath} (HTTP ${substationsCsvResp.status})`);

        const durhamData = await boundaryResp.json();
        const substationsData = await substationsResp.json();
        const csvData = parseCsv(await substationsCsvResp.text());
        const csvLookup = buildCsvLookup(csvData.rows);

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
        csvMarkerGroup.clearLayers();
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
                    const normalizedFeatureId = normalizeId(props.substation_id);
                    const normalizedNamePostcode = `${normalizeText(props.site_name)}|${normalizeText(props.postcode)}`;
                    const csvRow = csvLookup.byId.get(normalizedFeatureId) || csvLookup.byNamePostcode.get(normalizedNamePostcode);
                    const csvDetailsHtml = buildCsvDetailsHtml(csvRow);
                    const hasCsvData = Boolean(csvRow);
                    const markerFillColor = getSubstationMarkerColor(csvRow);
                    const markerFillOpacity = hasCsvData && markerFillColor === '#0078d4' ? 0.9 : 0.9;

                    const circleMarker = hasCsvData ? null : L.circleMarker([lat, lon], {
                        radius: 6,
                        className: 'substation-marker',
                        fillColor: markerFillColor,
                        color: '#ffffff',
                        weight: 1.5,
                        fillOpacity: markerFillColor === '#0078d4' ? 0.1 : markerFillOpacity
                    });

                    const marker = hasCsvData ? L.marker([lat, lon], {
                        icon: createSubstationCsvIcon(markerFillColor, markerFillOpacity)
                    }) : null;

                    // Substation Details Popup
                    if (circleMarker) {
                        circleMarker.bindPopup(`
                            <div class="popup-content popup-substation">
                                <h4>${props.site_name || 'Unknown Substation'}</h4>
                                <div class="popup-substation-layout">
                                    <div class="popup-substation-main">
                                        <div><b>ID:</b> ${props.substation_id || 'N/A'}</div>
                                        <div><b>Type:</b> ${props.site_type || 'N/A'}</div>
                                        <div><b>Voltage:</b> ${props.primary_voltage_kv ?? 'N/A'} kV / ${props.secondary_voltage_kv ?? 'N/A'} kV</div>
                                        <div><b>Rating:</b> ${props.transformer_rating_kva ?? 'N/A'} kVA</div>
                                        <div><b>Customers Fed:</b> ${props.customer_numbers || 'N/A'}</div>
                                        <div><b>Upstream:</b> ${props.upstream_substation || 'N/A'}</div>
                                        <div><b>Postcode:</b> ${props.postcode || 'N/A'}</div>
                                    </div>
                                    ${csvDetailsHtml}
                                </div>
                            </div>
                        `, getSubstationPopupOptions(hasCsvData));
                    }

                    if (marker) {
                        marker.bindPopup(`
                            <div class="popup-content popup-substation">
                                <h4>${props.site_name || 'Unknown Substation'}</h4>
                                <div class="popup-substation-layout">
                                    <div class="popup-substation-main">
                                        <div><b>ID:</b> ${props.substation_id || 'N/A'}</div>
                                        <div><b>Type:</b> ${props.site_type || 'N/A'}</div>
                                        <div><b>Voltage:</b> ${props.primary_voltage_kv ?? 'N/A'} kV / ${props.secondary_voltage_kv ?? 'N/A'} kV</div>
                                        <div><b>Rating:</b> ${props.transformer_rating_kva ?? 'N/A'} kVA</div>
                                        <div><b>Customers Fed:</b> ${props.customer_numbers || 'N/A'}</div>
                                        <div><b>Upstream:</b> ${props.upstream_substation || 'N/A'}</div>
                                        <div><b>Postcode:</b> ${props.postcode || 'N/A'}</div>
                                    </div>
                                    ${csvDetailsHtml}
                                </div>
                            </div>
                        `, getSubstationPopupOptions(hasCsvData));
                    }

                    if (circleMarker) markerGroup.addLayer(circleMarker);
                    if (marker) csvMarkerGroup.addLayer(marker);
                }
            }
        });

        // Update counter badge
        const counterContainer = document.getElementById('counter');
        counterContainer.className = 'badge-container'; 
        counterContainer.innerHTML = `
            <div id="powercut-counter" class="badge badge-black">0 Power Cuts</div>
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

        const livePowerCutIcon = L.divIcon({
            className: 'live-power-cut-icon-wrapper',
            html: `
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" focusable="false">
                    <path d="M13 2L4 13h5l-1 9 9-11h-5l1-9z" fill="#ffd700" stroke="#daa000" stroke-width="1.5" stroke-linejoin="round"/>
                </svg>
            `,
            iconSize: [22, 22],
            iconAnchor: [11, 18],
            popupAnchor: [0, -16]
        });

        L.geoJSON(data, {
            filter: feature => feature.geometry?.coordinates && turf.booleanPointInPolygon(feature, durhamBoundary),
            pointToLayer: (feature, latlng) => L.marker(latlng, { icon: livePowerCutIcon }),
            onEachFeature: (feature, layer) => {
                activePowerCuts++; 
                const props = feature.properties || {};
                const postcodes = Array.isArray(props.postcode) ? props.postcode.join(', ') : (props.postcode || 'N/A');
                
                // Power Cut Details Popup
                layer.bindPopup(`
                    <div class="popup-content popup-powercut">
                        <h4>Live Power Cut</h4>
                        <div class="pc-row"><b>Reference: </b> ${props.reference || 'N/A'}</div>
                        <div class="pc-row"><b>Type: </b> ${props.type || 'N/A'}</div>
                        <div class="pc-row"><b>Status: </b> ${props.natureofoutage || 'Information unavailable'}</div>
                        <div class="pc-row"><b>Affected Postcodes: </b> ${postcodes}</div>
                    </div>
                `, powerCutPopupOptions);
            }
        }).addTo(powerCutGroup);

        const pcCounter = document.getElementById('powercut-counter');
        if (pcCounter) pcCounter.innerText = `${activePowerCuts} Power Cuts`;

    } catch (err) {
        console.error("Failed to load live power cut data:", err);
    }
}

initMap();
