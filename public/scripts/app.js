const map = L.map('map').setView([54.6949868501283, -1.7758302950742813], 10);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);

const boundaryGroup = L.featureGroup().addTo(map);
const substationGroup = L.featureGroup().addTo(map);
const powerCutGroup = L.featureGroup().addTo(map);
const durhamGeoJsonPath = 'public/data/county_durham.geojson';
const substationsGeoJsonPath = 'public/data/substation_sites_processed.geojson';
const powerCutPopupOptions = { maxWidth: 800, minWidth: 450, className: 'powercut-popup-container' };
const originalDurhamView = { center: [54.6949868501283, -1.7758302950742813], zoom: 10 };
let durhamBoundary;
let processedSubstationsData;
let currentWeights = { physical: 0.25, terrain: 0.25, vulnerability: 0.25, consequence: 0.25 };
let riskSettings = {
    poleMounted: 0.5,
    groundMounted: 0.5,
    lowThreshold: 0,
    moderateThreshold: 0.75,
    significantThreshold: 1.25,
    extremeThreshold: 2.5,
    climateIncrease: 0
};
let showClassifiedOnly = false;
let showPowerCuts = true;

function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function parseRiskScore(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : 0;
}

function interpolateColor(start, end, amount) {
    const clampedAmount = Math.max(0, Math.min(1, amount));
    const channels = start.map((channel, index) => Math.round(channel + (end[index] - channel) * clampedAmount));
    return `#${channels.map(channel => channel.toString(16).padStart(2, '0')).join('')}`;
}

function getRiskMeta(score) {
    if (score === null || score === undefined || score === '' || !Number.isFinite(Number(score))) return { label: 'No Risk', color: '#0078d4', background: 'rgba(0, 120, 212, 0.12)' };
    const normalizedScore = Math.max(0, Math.min(1, Number(score)));
    const color = normalizedScore <= 1 / 3
        ? interpolateColor([42, 157, 143], [255, 214, 10], normalizedScore * 3)
        : normalizedScore <= 2 / 3
            ? interpolateColor([255, 214, 10], [247, 127, 0], (normalizedScore - 1 / 3) * 3)
            : interpolateColor([247, 127, 0], [214, 40, 40], (normalizedScore - 2 / 3) * 3);
    if (score >= 0.75) return { label: 'High Risk', color, background: `${color}1a` };
    if (score >= 0.5) return { label: 'Medium Risk', color, background: `${color}1a` };
    if (score > 0) return { label: 'Low Risk', color, background: `${color}1a` };
    return { label: 'No Risk', color: '#0078d4', background: 'rgba(0, 120, 212, 0.12)' };
}

function getHazardMeta(score) {
    if (score > riskSettings.extremeThreshold) return { label: 'Extreme', classValue: 4, norm: 1 };
    if (score >= riskSettings.significantThreshold) return { label: 'Significant', classValue: 3, norm: 2 / 3 };
    if (score >= riskSettings.moderateThreshold) return { label: 'Moderate', classValue: 2, norm: 1 / 3 };
    if (score >= riskSettings.lowThreshold) return { label: 'Low', classValue: 1, norm: 0 };
    return { label: null, classValue: null, norm: null };
}

function getVulnerabilityScore(props, tier) {
    if (!Number.isFinite(Number(props[`hazard_${tier}`]))) return null;
    const siteType = String(props.site_type || '').toLowerCase();
    if (siteType.includes('pole')) return riskSettings.poleMounted;
    if (siteType.includes('ground')) return riskSettings.groundMounted;
    return 0;
}

function createSubstationIcon(score) {
    const risk = getRiskMeta(score);
    const markerOpacity = risk.label === 'No Risk' ? 0.62 : 1;
    const isHighRisk = risk.label === 'High Risk';
    const isMediumRisk = risk.label === 'Medium Risk';
    const isClassifiedLowRisk = risk.label === 'Low Risk';
    const iconSize = isHighRisk ? 27 : isMediumRisk ? 16 : isClassifiedLowRisk ? 24 : 18;
    const shape = risk.label === 'High Risk'
        ? '<path d="M12 1.5 L14.7 8.2 L21.8 8.2 L16.1 12.8 L18.7 19.5 L12 15.2 L5.3 19.5 L7.9 12.8 L2.2 8.2 L9.3 8.2 Z"/>'
        : risk.label === 'Medium Risk'
            ? '<path d="M12 3 L21 20 H3 Z"/>'
            : '<circle cx="12" cy="12" r="4.25"/>';
    return L.divIcon({ className: 'substation-marker-icon', html: `<svg viewBox="0 0 24 24" width="${iconSize}" height="${iconSize}" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><g fill="${risk.color}" opacity="${markerOpacity}" stroke="#000000" stroke-width="1.5" stroke-linejoin="round">${shape}</g></svg>`, iconSize: [iconSize, iconSize], iconAnchor: [iconSize / 2, iconSize / 2], popupAnchor: [0, -iconSize / 2] });
}

function calculateWeightedScore(props, tier) {
    const total = Object.values(currentWeights).reduce((sum, value) => sum + value, 0);
    if (total === 0) return 0;
    const score = currentWeights.physical * parseRiskScore(props[`degree_${tier}_norm`])
        + currentWeights.terrain * parseRiskScore(props.combined_norm)
        + currentWeights.vulnerability * parseRiskScore(props[`site_type_norm_${tier}`])
        + currentWeights.consequence * parseRiskScore(props.customers_class_norm);
    return Number((score / total).toFixed(4));
}

function calculateCombinedWeightedScore(props) {
    const tierWeights = { low: 1, med: 1.5, high: 3.3 };
    let weightedTotal = 0;
    let totalWeight = 0;
    Object.entries(tierWeights).forEach(([tier, tierWeight]) => {
        const exposure = Number(props[`rof_${tier}`]);
        if (!Number.isFinite(exposure) || exposure <= 0) return;
        weightedTotal += parseRiskScore(props[`weighted_score_${tier}`]) * tierWeight;
        totalWeight += tierWeight;
    });
    return totalWeight > 0 ? Number((weightedTotal / totalWeight).toFixed(4)) : null;
}

function calculateDerivedProperties(props, tier) {
    const sourceHazard = props[`hazard_${tier}`];
    if (sourceHazard === undefined || sourceHazard === null || sourceHazard === '') {
        return {
            [`degree_${tier}`]: null,
            [`degree_${tier}_class`]: null,
            [`degree_${tier}_norm`]: null,
            [`site_type_norm_${tier}`]: null
        };
    }
    const rawHazard = parseRiskScore(sourceHazard);
    const climateMultiplier = 1 + Math.max(0, riskSettings.climateIncrease) / 100;
    const adjustedHazard = rawHazard * climateMultiplier;
    const hazard = getHazardMeta(adjustedHazard);
    return {
        [`hazard_${tier}`]: Number(adjustedHazard.toFixed(3)),
        [`degree_${tier}`]: hazard.label,
        [`degree_${tier}_class`]: hazard.classValue,
        [`degree_${tier}_norm`]: hazard.norm,
        [`site_type_norm_${tier}`]: getVulnerabilityScore(props, tier)
    };
}

function buildWeightedGeoJson() {
    return {
        ...processedSubstationsData,
        features: (processedSubstationsData.features || []).map(feature => {
            const baseProps = feature.properties || {};
            const derivedProps = ['high', 'med', 'low'].reduce((values, tier) => ({
                ...values,
                ...calculateDerivedProperties(baseProps, tier)
            }), {});
            const props = { ...baseProps, ...derivedProps };
            return {
                ...feature,
                properties: {
                    ...props,
                    weighted_score_high: calculateWeightedScore(props, 'high'),
                    weighted_score_med: calculateWeightedScore(props, 'med'),
                    weighted_score_low: calculateWeightedScore(props, 'low'),
                    map_weighted_score: calculateCombinedWeightedScore({
                        ...props,
                        weighted_score_high: calculateWeightedScore(props, 'high'),
                        weighted_score_med: calculateWeightedScore(props, 'med'),
                        weighted_score_low: calculateWeightedScore(props, 'low')
                    })
                }
            };
        })
    };
}

function buildDetailsHtml(props) {
    const risk = getRiskMeta(props.map_weighted_score);
    const fields = ['final_risk_score', 'map_weighted_score', 'slope', 'combined_norm', 'mannings', 'rof_high', 'rof_med', 'rof_low', 'hazard_high', 'hazard_med', 'hazard_low', 'degree_high', 'degree_med', 'degree_low', 'weighted_score_high', 'weighted_score_med', 'weighted_score_low'];
    const details = fields.map(field => {
        const value = props[field] === undefined || props[field] === '' ? 'N/A' : props[field];
        return `<div class="popup-csv-item"><b>${escapeHtml(field.replace(/_/g, ' '))}:</b> ${escapeHtml(value)}</div>`;
    }).join('');
    return `<div class="popup-csv-section" style="--risk-color:${risk.color};--risk-background:${risk.background}"><div class="popup-csv-title">${risk.label}</div><div class="popup-csv-grid">${details}</div></div>`;
}

function renderSubstations() {
    const weightedSubstationsData = buildWeightedGeoJson();
    substationGroup.clearLayers();
    let count = 0;
    weightedSubstationsData.features.forEach(feature => {
        const coords = feature.geometry?.coordinates;
        if (!coords || coords.length < 2 || !turf.booleanPointInPolygon(feature, durhamBoundary)) return;
        const props = feature.properties || {};
        const hasMapScore = props.map_weighted_score !== null && props.map_weighted_score !== undefined && props.map_weighted_score !== '';
        const visualScore = hasMapScore && Number.isFinite(Number(props.map_weighted_score)) ? Number(props.map_weighted_score) : null;
        if (showClassifiedOnly && visualScore === null) return;
        count++;
        const marker = L.marker([coords[1], coords[0]], {
            icon: createSubstationIcon(visualScore),
            zIndexOffset: visualScore === null ? 0 : 1000 + Math.round(Math.max(0, Math.min(1, visualScore)) * 1000)
        });
        marker.bindPopup(`<div class="popup-content popup-substation"><h4>${escapeHtml(props.site_name || 'Unknown Substation')}</h4><div class="popup-substation-layout"><div class="popup-substation-main"><div><b>ID:</b> ${escapeHtml(props.substation_id || 'N/A')}</div><div><b>Type:</b> ${escapeHtml(props.site_type || 'N/A')}</div><div><b>Voltage:</b> ${escapeHtml(props.primary_voltage_kv || 'N/A')} kV / ${escapeHtml(props.secondary_voltage_kv || 'N/A')} kV</div><div><b>Rating:</b> ${escapeHtml(props.transformer_rating_kva || 'N/A')} kVA</div><div><b>Customers Fed:</b> ${escapeHtml(props.customer_numbers || 'N/A')}</div><div><b>Upstream:</b> ${escapeHtml(props.upstream_substation || 'N/A')}</div><div><b>Postcode:</b> ${escapeHtml(props.postcode || 'N/A')}</div></div>${buildDetailsHtml(props)}</div></div>`, { maxWidth: 680, minWidth: 320, className: 'popup-csv-scroll' });
        substationGroup.addLayer(marker);
    });
    const badge = document.querySelector('.badge-blue');
    if (badge) badge.innerText = `${count} Substations Mapped`;
}

function setupWeightControls() {
    document.getElementById('recenter-map')?.addEventListener('click', () => {
        map.closePopup();
        map.setView(originalDurhamView.center, originalDurhamView.zoom);
    });

    document.querySelectorAll('#weight-controls input').forEach(input => input.addEventListener('input', event => {
        const control = event.target.closest('.weight-control');
        currentWeights[control.dataset.weight] = Number(event.target.value) / 100;
        control.querySelector('output').innerText = `${event.target.value}%`;
        renderSubstations();
    }));

    document.querySelectorAll('.risk-setting').forEach(input => input.addEventListener('input', event => {
        const value = Number(event.target.value);
        if (!Number.isFinite(value)) return;
        riskSettings[event.target.dataset.setting] = value;
        renderSubstations();
    }));

    const riskSettings = document.getElementById('risk-settings');
    const settingsPanel = riskSettings?.querySelector('.settings-panel');
    const positionSettingsPanel = () => {
        if (!riskSettings?.open || !settingsPanel) return;
        const buttonBounds = riskSettings.querySelector('summary').getBoundingClientRect();
        settingsPanel.style.top = `${buttonBounds.bottom + 10}px`;
    };
    riskSettings?.addEventListener('toggle', positionSettingsPanel);
    window.addEventListener('resize', positionSettingsPanel);

    const classifiedToggle = document.getElementById('classified-toggle');
    classifiedToggle?.addEventListener('click', () => {
        showClassifiedOnly = !showClassifiedOnly;
        classifiedToggle.setAttribute('aria-pressed', String(showClassifiedOnly));
        classifiedToggle.textContent = showClassifiedOnly ? 'Show all substations' : 'Classified only';
        renderSubstations();
    });

    const powercutCounter = document.getElementById('powercut-counter');
    powercutCounter?.addEventListener('click', () => {
        showPowerCuts = !showPowerCuts;
        powercutCounter.setAttribute('aria-pressed', String(showPowerCuts));
        powerCutGroup.clearLayers();
        if (showPowerCuts) fetchLivePowerCuts();
    });
}

async function initMap() {
    try {
        const boundaryResponse = await fetch(durhamGeoJsonPath);
        const substationsResponse = await fetch(substationsGeoJsonPath);
        if (!boundaryResponse.ok) throw new Error(`Missing ${durhamGeoJsonPath} (HTTP ${boundaryResponse.status})`);
        if (!substationsResponse.ok) throw new Error(`Missing ${substationsGeoJsonPath} (HTTP ${substationsResponse.status})`);
        const durhamData = await boundaryResponse.json();
        processedSubstationsData = await substationsResponse.json();
        durhamBoundary = durhamData.type === 'FeatureCollection' ? durhamData.features[0] : durhamData;
        const boundaryCoordinates = durhamBoundary.geometry?.coordinates || durhamBoundary.coordinates;
        const boundaryHole = boundaryCoordinates[0].map(([longitude, latitude]) => [latitude, longitude]);
        const worldRing = [[90, -180], [90, 180], [-90, 180], [-90, -180]];
        L.polygon([worldRing, boundaryHole], { color: '#68246d', weight: 2.5, fillColor: '#68246d', fillOpacity: 0.16, dashArray: '5, 5' }).addTo(boundaryGroup);
        L.geoJSON(durhamData, { style: { color: '#68246d', weight: 2.5, fillOpacity: 0, dashArray: '5, 5' } }).addTo(boundaryGroup);
        document.getElementById('counter').className = 'badge-container';
        document.getElementById('counter').innerHTML = '<button id="powercut-counter" class="badge badge-black" type="button" aria-pressed="true">0 Power Cuts</button><div class="badge badge-blue">0 Substations Mapped</div>';
        setupWeightControls();
        renderSubstations();
        map.setView(originalDurhamView.center, originalDurhamView.zoom);
        L.tileLayer.wms('https://environment.data.gov.uk/spatialdata/nafra2-risk-of-flooding-from-surface-water/wms', {
            layers: 'rofsw',
            format: 'image/png',
            transparent: true,
            opacity: 0.8,
            attribution: '&copy; Environment Agency',
            minZoom: 6,
            maxZoom: 19,
            maxNativeZoom: 15
        }).addTo(map);
        await fetchLivePowerCuts();
        setInterval(fetchLivePowerCuts, 300000);
    } catch (error) {
        console.error('Map setup failed:', error);
        document.getElementById('counter').innerText = error.message;
    }
}

async function fetchLivePowerCuts() {
    try {
        const response = await fetch('https://northernpowergrid.opendatasoft.com/api/explore/v2.1/catalog/datasets/live-power-cuts-data/exports/geojson?lang=en&timezone=Europe%2FLondon');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        powerCutGroup.clearLayers();
        const icon = L.divIcon({ className: 'live-power-cut-icon-wrapper', html: '<svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path d="M13 2L4 13h5l-1 9 9-11h-5l1-9z" fill="#000000" stroke="#ffffff" stroke-width="0.75" stroke-linejoin="round"/></svg>', iconSize: [22, 22], iconAnchor: [11, 18], popupAnchor: [0, -16] });
        const data = await response.json();
        const inDurhamFeatures = (data.features || []).filter(feature => feature.geometry?.coordinates && turf.booleanPointInPolygon(feature, durhamBoundary));
        const activePowerCuts = inDurhamFeatures.length;
        if (showPowerCuts) {
            L.geoJSON({ ...data, features: inDurhamFeatures }, { pointToLayer: (feature, latlng) => L.marker(latlng, { icon, zIndexOffset: 10000 }), onEachFeature: (feature, layer) => { const props = feature.properties || {}; const postcodes = Array.isArray(props.postcode) ? props.postcode.join(', ') : (props.postcode || 'N/A'); layer.bindPopup(`<div class="popup-content popup-powercut"><h4>Live Power Cut</h4><div class="pc-row"><b>Reference: </b>${escapeHtml(props.reference || 'N/A')}</div><div class="pc-row"><b>Type: </b>${escapeHtml(props.type || 'N/A')}</div><div class="pc-row"><b>Status: </b>${escapeHtml(props.natureofoutage || 'Information unavailable')}</div><div class="pc-row"><b>Affected Postcodes: </b>${escapeHtml(postcodes)}</div></div>`, powerCutPopupOptions); } }).addTo(powerCutGroup);
        }
        const counter = document.getElementById('powercut-counter');
        if (counter) counter.innerText = `${activePowerCuts} Power Cuts`;
    } catch (error) { console.error('Failed to load live power cut data:', error); }
}

initMap();
