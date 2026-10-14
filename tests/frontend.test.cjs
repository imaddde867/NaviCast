const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');

const html = fs.readFileSync(path.join(__dirname, '../static/index.html'), 'utf8');
const script = html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];

function dashboard({ configured = true } = {}) {
    const layers = new Set();
    const elements = new Map();
    const preferences = new Map();
    const fittedViews = [];
    const map = {
        hasLayer: layer => layers.has(layer),
        removeLayer: layer => layers.delete(layer),
        fitBounds: (bounds, options) => fittedViews.push({ bounds, options })
    };
    function layer(position, options = {}) {
        return {
            options,
            addTo() { layers.add(this); return this; },
            bindPopup() { return this; }, bindTooltip(text) { this.tooltip = text; return this; },
            getElement() { return null; }, setStyle(style) { Object.assign(options, style); return this; },
            off() { return this; }, on() { return this; },
            getLatLng() { return { lat: position[0], lng: position[1] }; },
            setLatLng(value) { position = value; }, isPopupOpen() { return false; }
        };
    }
    const context = vm.createContext({
        Date, console: { warn() {}, error() {}, log() {} }, map,
        L: { circleMarker: layer, polyline: layer },
        getComputedStyle: () => ({ getPropertyValue: () => '#123456' }),
        setTimeout() {}, clearTimeout() {}, setInterval() {}, clearInterval() {},
        window: { innerWidth: 1280, matchMedia: () => ({ matches: false }) },
        localStorage: { getItem: key => preferences.get(key) ?? null, setItem: (key, value) => preferences.set(key, value) },
        document: {
            addEventListener() {},
            documentElement: { getAttribute: () => 'light' },
            createElement: () => ({ innerHTML: '', style: {} }),
            getElementById(id) {
                if (!elements.has(id)) {
                    const classes = new Set();
                    elements.set(id, {
                        textContent: '', style: {}, dataset: {}, className: '', remove() {},
                        setAttribute(key, value) { this[key] = value; },
                        classList: { add: value => classes.add(value), contains: value => classes.has(value) }
                    });
                }
                return elements.get(id);
            }
        }
    });
    // Keep the real application functions; only the external Leaflet setup is omitted.
    vm.runInContext(script.slice(0, script.indexOf('// --- Map Initialization ---')) +
        script.slice(script.indexOf('// --- Event Listeners ---')), context);
    if (configured) vm.runInContext("observationStaleAfterMs = 300000; predictionHorizonMinutes = 30", context);
    return { context, layers, elements, preferences, fittedViews, run: code => vm.runInContext(code, context) };
}

function vessel(id, overrides = {}) {
    return {
        vessel_id: id, current_latitude: 60, current_longitude: 22,
        current_timestamp: new Date().toISOString(), sog: 10, cog: 90, heading: 90,
        country: 'Finland', vessel_type: 'Cargo', pos_acc: true,
        predicted_latitude: null, predicted_longitude: null,
        prediction_for_timestamp: null, prediction_made_at: null,
        prediction_method: null, ...overrides
    };
}

test('fleet reorder evicts previous markers before adding the next bounded fleet', () => {
    const app = dashboard();
    app.context.first = Array.from({ length: 600 }, (_, i) => vessel(i + 1));
    app.context.second = [...app.context.first].reverse();
    app.run('removeStaleVessels(processVesselData(first, 0).processedVesselIds)');
    app.run('removeStaleVessels(processVesselData(second, 0).processedVesselIds)');
    assert.equal(app.run('vessels.size'), 500);
    assert.equal(app.run('vessels.has(1)'), false);
    assert.equal(app.run('vessels.has(600)'), true);
});

test('invalid and duplicate records cannot consume valid fleet capacity', () => {
    const app = dashboard();
    app.context.batch = [vessel(1, { current_latitude: 120 }), vessel(2), vessel(2),
        ...Array.from({ length: 500 }, (_, i) => vessel(i + 3))];
    app.run('processVesselData(batch, 0)');
    assert.equal(app.run('vessels.size'), 500);
    assert.equal(app.run('vessels.has(1)'), false);
    assert.equal(app.run('vessels.has(501)'), true);
});

function projection(overrides = {}) {
    return { predicted_latitude: 60, predicted_longitude: 22.1,
        prediction_for_timestamp: new Date(Date.now() + 1800000).toISOString(),
        prediction_method: 'dead_reckoning', ...overrides };
}

test('popup projection time is the exact server target timestamp', () => {
    const app = dashboard();
    app.context.data = vessel(1, projection({ prediction_for_timestamp: '2026-10-14T09:47:00Z' }));
    const result = app.run("formatPredictionInfo(data, new Date('2026-10-14T09:10:00Z'))");
    assert.equal(result.time, new Date('2026-10-14T09:47:00Z').toLocaleString('en-US', {
        month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit'
    }));
    assert.match(result.source, /server/i);
});

test('stale or invalid AIS timestamps do not produce a forecast', () => {
    const app = dashboard();
    for (const timestamp of ['2020-01-01T00:00:00Z', 'not-a-date', null]) {
        app.context.data = vessel(1, { current_timestamp: timestamp,
            predicted_latitude: 60, predicted_longitude: 22.1 });
        assert.equal(app.run('determinePrediction(data, [60, 22]).predictedPos'), null);
        assert.equal(app.run('isVesselStale(data.current_timestamp)'), true);
    }
});

test('metadata supplies the observation staleness and projection horizon', async () => {
    const app = dashboard();
    app.context.AbortController = AbortController;
    app.context.fetch = async () => ({ ok: true, json: async () => ({
        mode: 'live', observation_stale_after_seconds: 300, prediction_horizon_minutes: 45
    }) });
    await app.run('fetchMetadata()');
    assert.equal(app.run('isVesselStale(new Date(Date.now() - 180000).toISOString())'), false);
    assert.equal(app.run('isVesselStale(new Date(Date.now() - 360000).toISOString())'), true);
    assert.equal(app.run('predictionHorizonMinutes'), 45);
    assert.match(app.elements.get('mode-banner').textContent, /45 minutes/);
});

test('missing or invalid metadata hides projections without a browser default', async () => {
    for (const metadata of [
        { mode: 'live' },
        { mode: 'live', observation_stale_after_seconds: 0 },
        { mode: 'live', observation_stale_after_seconds: 300, prediction_horizon_minutes: 0 },
        { mode: 'live', observation_stale_after_seconds: '300' }
    ]) {
        const app = dashboard();
        app.context.AbortController = AbortController;
        app.context.fetch = async () => ({ ok: true, json: async () => metadata });
        await app.run('fetchMetadata()');
        assert.equal(app.run('observationStaleAfterMs'), null);
        assert.equal(app.run('predictionHorizonMinutes'), null);
        app.context.data = vessel(1, projection());
        assert.equal(app.run('determinePrediction(data).predictedPos'), null);
        assert.match(app.elements.get('mode-banner').textContent, /configuration unavailable/i);
    }
});

test('expired API forecast is hidden without a substitute', () => {
    const app = dashboard();
    app.context.data = vessel(1, { predicted_latitude: 60, predicted_longitude: 22.1,
        prediction_for_timestamp: '2020-01-01T00:00:00Z', prediction_method: 'dead_reckoning' });
    const result = app.run('determinePrediction(data, [60, 22])');
    assert.equal(result.isApiPrediction, false);
    assert.equal(result.predictedPos, null);
});

test('vessel identity, country and type are escaped in popup HTML', () => {
    const app = dashboard();
    app.context.data = vessel('<img src=x onerror=alert(1)>', {
        country: '<svg onload=alert(2)>', vessel_type: '<script>alert(3)</script>'
    });
    const content = app.run('createPopupContent(data).innerHTML');
    assert.equal(content.includes('<img'), false);
    assert.equal(content.includes('<svg'), false);
    assert.equal(content.includes('<script'), false);
    assert.match(content, /&lt;img src=x onerror=alert\(1\)&gt;/);
    assert.match(content, /&lt;svg onload=alert\(2\)&gt;/);
});

test('popup suppresses stale forecast details as well as the map forecast', () => {
    const app = dashboard();
    app.context.data = vessel(1, { current_timestamp: '2020-01-01T00:00:00Z',
        predicted_latitude: 60, predicted_longitude: 22.1 });
    assert.equal(app.run('createPopupContent(data).innerHTML').includes('popup-prediction'), false);
});

test('projection filter includes server projections and respects display toggles', () => {
    const app = dashboard();
    app.context.batch = [vessel(1, projection())];
    app.run('processVesselData(batch, 0); activeFilter = "predictable"; applyVesselFilter()');
    assert.equal(app.run('map.hasLayer(vessels.get(1).marker)'), true);
    app.run('handlePredictionToggle.call({ checked: false })');
    assert.equal(app.run('map.hasLayer(vessels.get(1).predictionMarker)'), false);
    app.run('handlePredictionToggle.call({ checked: true })');
    assert.equal(app.run('map.hasLayer(vessels.get(1).predictionMarker)'), true);
});

test('aging AIS fixes clear their map projections between API updates', () => {
    const app = dashboard();
    app.context.batch = [vessel(1, projection())];
    app.run('processVesselData(batch, 0)');
    assert.equal(app.run('map.hasLayer(vessels.get(1).predictionMarker)'), true);
    app.run('vessels.get(1).data.current_timestamp = "2020-01-01T00:00:00Z"; updateTimeDisplays()');
    assert.equal(app.run('vessels.get(1).hasPrediction'), false);
    assert.equal(app.run('vessels.get(1).predictionMarker'), null);
});

test('empty and stale feed states are visible to the user', () => {
    const app = dashboard();
    app.run('document.getElementById("feed-status"); updateUIComponents(0)');
    assert.match(app.elements.get('feed-status').textContent, /no vessels/i);
    app.context.batch = [vessel(1, { current_timestamp: '2020-01-01T00:00:00Z' })];
    app.run('processVesselData(batch, 0); updateUIComponents(0)');
    assert.match(app.elements.get('feed-status').textContent, /stale/i);
});

test('metadata identifies synthetic demo data without inferring mode from vessels', async () => {
    const app = dashboard();
    app.context.AbortController = AbortController;
    app.context.fetch = async () => ({ ok: true, json: async () => ({
        mode: 'demo', prediction_method: 'dead_reckoning', prediction_horizon_minutes: 30, observation_stale_after_seconds: 60
    }) });
    await app.run('fetchMetadata()');
    assert.match(app.elements.get('mode-banner').textContent, /demo/i);
    assert.match(app.elements.get('mode-banner').textContent, /synthetic/i);
});

test('popup notes a coast ahead only when the projection is flagged as crossing land', () => {
    const app = dashboard();
    const fix = { predicted_latitude: 60, predicted_longitude: 22.1, prediction_method: 'dead_reckoning',
        prediction_for_timestamp: new Date(Date.now() + 1800000).toISOString() };
    app.context.flagged = vessel(1, { ...fix, projection_land_conflict: true });
    app.context.clear = vessel(2, { ...fix, projection_land_conflict: false });
    assert.match(app.run('createPopupContent(flagged).innerHTML'), /Coast ahead: straight-line estimate crosses land/);
    assert.doesNotMatch(app.run('createPopupContent(clear).innerHTML'), /Coast ahead/);
});

test('basemap credits OpenStreetMap and Digitraffic data and its licence', () => {
    const requests = [];
    const map = { setView() { return this; } };
    const context = vm.createContext({ L: {
        map: () => map, canvas() {}, control: { zoom: () => ({ addTo() {} }) },
        tileLayer: (url, options) => { requests.push({ url, options }); return {}; }
    } });
    vm.runInContext(script.slice(script.indexOf('// --- Map Initialization ---'), script.indexOf('// --- Event Listeners ---')), context);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].url, 'https://tile.openstreetmap.org/{z}/{x}/{y}.png');
    assert.match(requests[0].options.attribution, /openstreetmap\.org\/copyright/);
    assert.match(requests[0].options.attribution, /opendatacommons\.org\/licenses\/odbl/);
    assert.match(requests[0].options.attribution, /digitraffic\.fi\/en\/marine-traffic/);
    assert.match(requests[0].options.attribution, /creativecommons\.org\/licenses\/by\/4\.0/);
    assert.match(requests[0].options.attribution, /constant-course estimates added/);
});

test('first demo fleet is framed once without resetting the view on later polls', async () => {
    const app = dashboard();
    app.context.AbortController = AbortController;
    app.context.fetch = async () => ({ ok: true, json: async () => ({ mode: 'demo', prediction_horizon_minutes: 30, observation_stale_after_seconds: 60 }) });
    await app.run('fetchMetadata()');
    app.context.batch = [vessel(1, { current_latitude: 55, current_longitude: 15 }),
        vessel(2, { current_latitude: 66, current_longitude: 26 })];
    app.run('processVesselData(batch, 0); processVesselData(batch, 0)');
    assert.equal(app.fittedViews.length, 1);
    assert.deepEqual(JSON.parse(JSON.stringify(app.fittedViews[0].bounds)), [[55, 15], [66, 26]]);
    assert.equal(app.fittedViews[0].options.paddingBottomRight[0] > 200, true);
});

test('demo framing works when metadata arrives after the vessel response', async () => {
    const app = dashboard();
    app.context.batch = [vessel(1)];
    app.run('processVesselData(batch, 0)');
    app.context.AbortController = AbortController;
    app.context.fetch = async () => ({ ok: true, json: async () => ({ mode: 'demo', prediction_horizon_minutes: 30, observation_stale_after_seconds: 60 }) });
    await app.run('fetchMetadata()');
    assert.equal(app.fittedViews.length, 1);
    app.run('updateFeedStatus()');
    assert.match(app.elements.get('feed-status').textContent, /sample/i);
    assert.equal(app.elements.get('feed-status').textContent.includes('AIS fixes'), false);
});

test('mobile settings collapse initially while respecting a saved expanded preference', () => {
    for (const saved of [null, 'false']) {
        const app = dashboard();
        app.context.window.matchMedia = () => ({ matches: true });
        if (saved !== null) app.preferences.set('navicast_panel_collapsed', saved);
        app.run('initPanelState()');
        assert.equal(app.elements.get('control-panel')?.classList.contains('collapsed') ?? false, saved === null);
    }
});

test('movement validation uses time between AIS observations rather than API polls', () => {
    const app = dashboard();
    const now = Date.now();
    app.context.first = [vessel(1, { current_timestamp: new Date(now - 120000).toISOString() })];
    app.context.next = [vessel(1, { current_timestamp: new Date(now).toISOString(), current_longitude: 22.02 })];
    app.run('processVesselData(first, 10); processVesselData(next, 10)');
    assert.equal(app.run('vessels.get(1).marker.getLatLng().lng'), 22.02);
    assert.equal(app.run('vessels.get(1).data.current_longitude'), 22.02);
    assert.equal(app.run('vessels.get(1).timestamp'), app.context.next[0].current_timestamp);
});

test('rejected movement preserves the accepted fix and clears a missing server projection', () => {
    const app = dashboard();
    const now = Date.now();
    app.context.first = [vessel(1, { current_timestamp: new Date(now - 5000).toISOString(), ...projection() })];
    app.context.rejected = [vessel(1, { current_timestamp: new Date(now).toISOString(),
        current_latitude: 65, current_longitude: 26, sog: 20 })];
    app.run('processVesselData(first, 10); previousProjection = vessels.get(1).predictionMarker; processVesselData(rejected, 10)');
    assert.equal(app.run('vessels.get(1).timestamp'), app.context.first[0].current_timestamp);
    assert.equal(app.run('vessels.get(1).data.current_latitude'), 60);
    assert.equal(app.run('vessels.get(1).marker.getLatLng().lat'), 60);
    assert.notEqual(app.run('previousProjection'), null);
    assert.equal(app.run('vessels.get(1).predictionMarker'), null);
    assert.match(app.run('createPopupContent(vessels.get(1).data).innerHTML'), /60\.000000, 22\.000000/);
});

test('a realistic fix after a rejected observation uses the last accepted AIS time', () => {
    const app = dashboard();
    const now = Date.now();
    app.context.first = [vessel(1, { current_timestamp: new Date(now - 120000).toISOString() })];
    app.context.rejected = [vessel(1, { current_timestamp: new Date(now - 60000).toISOString(), current_latitude: 65 })];
    app.context.next = [vessel(1, { current_timestamp: new Date(now).toISOString(), current_longitude: 22.02 })];
    app.run('processVesselData(first, 10); processVesselData(rejected, 10); processVesselData(next, 10)');
    assert.equal(app.run('vessels.get(1).marker.getLatLng().lng'), 22.02);
});

test('an older AIS observation cannot replace the accepted fix', () => {
    const app = dashboard();
    const now = Date.now();
    app.context.first = [vessel(1, { current_timestamp: new Date(now).toISOString() })];
    app.context.older = [vessel(1, { current_timestamp: new Date(now - 10000).toISOString(), current_longitude: 22.0001 })];
    app.run('processVesselData(first, 10); processVesselData(older, 10)');
    assert.equal(app.run('vessels.get(1).timestamp'), app.context.first[0].current_timestamp);
    assert.equal(app.run('vessels.get(1).marker.getLatLng().lng'), 22);
});

test('missing speed and course stay unknown in vessel state and popup', () => {
    const app = dashboard();
    app.context.batch = [vessel(1, { sog: null, cog: null })];
    app.run('processVesselData(batch, 10)');
    assert.equal(app.run('vessels.get(1).speed'), null);
    const popup = app.run('createPopupContent(vessels.get(1).data).innerHTML');
    assert.match(popup, /Motion unavailable/);
    assert.equal(popup.includes('Stationary'), false);
    assert.equal(app.run('formatSpeed(null)'), 'Unknown');
    assert.equal(app.run('formatCourse(null)'), 'Unknown');
});

test('unknown motion is excluded from stationary count and filter on create and update', () => {
    const app = dashboard();
    app.context.batch = [vessel(1, { sog: null }), vessel(2, { sog: 0 }), vessel(3)];
    app.run('processVesselData(batch, 10); updateFilterCounts(); activeFilter = "stationary"; applyVesselFilter()');
    assert.equal(app.elements.get('filter-stationary').textContent, 'Stationary (1)');
    assert.equal(app.elements.get('filter-moving').textContent, 'Moving (1)');
    assert.equal(app.run('map.hasLayer(vessels.get(1).marker)'), false);
    assert.equal(app.run('map.hasLayer(vessels.get(2).marker)'), true);
    app.context.batch = [vessel(2, { sog: null })];
    app.run('processVesselData(batch, 10); updateFilterCounts(); applyVesselFilter()');
    assert.equal(app.run('vessels.get(2).speed'), null);
    assert.equal(app.elements.get('filter-stationary').textContent, 'Stationary (0)');
    assert.equal(app.run('map.hasLayer(vessels.get(2).marker)'), false);
});

test('missing, partial and rejected API projections never create substitute trajectories', () => {
    const app = dashboard();
    for (const fields of [
        {}, { predicted_latitude: 60 }, { predicted_longitude: 22.1 },
        projection({ predicted_latitude: 91 }), projection({ predicted_longitude: NaN }),
        projection({ prediction_for_timestamp: null }),
        projection({ prediction_for_timestamp: 'not-a-date' }),
        projection({ prediction_for_timestamp: new Date(Date.now() - 1000).toISOString() })
    ]) {
        app.context.batch = [vessel(1, projection())];
        app.run('processVesselData(batch, 0)');
        assert.notEqual(app.run('vessels.get(1).predictionLine'), null);
        app.context.batch = [vessel(1, fields)];
        app.run('processVesselData(batch, 0); updateUIComponents(); handlePredictionToggle.call({ checked: true })');
        assert.equal(app.run('vessels.get(1).predictionLine'), null);
        assert.equal(app.run('vessels.get(1).predictionMarker'), null);
        assert.equal(app.layers.size, 1);
        assert.equal(app.run('createPopupContent(batch[0]).innerHTML').includes('popup-prediction'), false);
        assert.equal(app.elements.get('prediction-count').textContent, 0);
    }
});

test('server coordinates and land-conflict styling survive without browser projection guards', () => {
    const app = dashboard();
    app.context.batch = [vessel(1, projection({ predicted_latitude: 60.4, predicted_longitude: 23,
        projection_land_conflict: true, projection_clear_until_fraction: 0.25 }))];
    app.run('processVesselData(batch, 0)');
    assert.equal(app.run('vessels.get(1).predictionMarker.getLatLng().lng'), 23);
    assert.equal(app.run('vessels.get(1).predictionLine.options.dashArray'), '2,8');
    assert.equal(app.run('vessels.get(1).predictionMarker.options.fillOpacity'), 0);
    assert.equal(app.run('vessels.get(1).data.projection_clear_until_fraction'), 0.25);
    assert.match(app.run('createPopupContent(batch[0]).innerHTML'), /Coast ahead/);
});

test('capped fleet counts include unrendered API vessels and the notice follows filters', () => {
    const app = dashboard();
    app.context.batch = Array.from({ length: 600 }, (_, i) => vessel(i + 1,
        i >= 500 ? projection({ sog: 0 }) : {}));
    app.run('processVesselData(batch, 0); updateUIComponents()');
    assert.equal(app.run('vessels.size'), 500);
    assert.equal(app.elements.get('vessel-count').textContent, 600);
    assert.equal(app.elements.get('prediction-count').textContent, 100);
    assert.equal(app.elements.get('filter-all').textContent, 'All Vessels (600)');
    assert.equal(app.elements.get('filter-moving').textContent, 'Moving (500)');
    assert.equal(app.elements.get('filter-stationary').textContent, 'Stationary (100)');
    assert.equal(app.elements.get('filter-predictable').textContent, 'Projected (100)');
    assert.match(app.elements.get('render-status').textContent, /500 rendered of 600.*500-vessel rendering limit/);
    app.run('activeFilter = "predictable"; applyVesselFilter(); updateFeedStatus()');
    assert.match(app.elements.get('feed-status').textContent, /0 vessels visible.*500 rendered of 600/);
    app.context.batch = [vessel(1)];
    app.run('processVesselData(batch, 0); updateUIComponents()');
    assert.equal(app.elements.get('vessel-count').textContent, 1);
    assert.equal(app.elements.get('render-status').textContent, '');
    app.context.batch = [];
    app.run('processVesselData(batch, 0); updateUIComponents()');
    assert.equal(app.elements.get('vessel-count').textContent, 0);
    assert.equal(app.elements.get('prediction-count').textContent, 0);
});

test('metadata arriving after vessels enables only server projections, then expiry removes them', async () => {
    const app = dashboard({ configured: false });
    app.context.batch = [vessel(1, projection()), vessel(2)];
    app.run('processVesselData(batch, 0)');
    assert.equal(app.run('vessels.get(1).predictionMarker'), null);
    app.context.AbortController = AbortController;
    app.context.fetch = async () => ({ ok: true, json: async () => ({
        mode: 'live', observation_stale_after_seconds: 300, prediction_horizon_minutes: 45
    }) });
    await app.run('fetchMetadata()');
    assert.match(app.run('vessels.get(1).predictionMarker.tooltip'), /45 min from source fix/);
    assert.equal(app.run('vessels.get(2).predictionMarker'), null);
    app.run('vessels.get(1).data.prediction_for_timestamp = "2020-01-01T00:00:00Z"; updateTimeDisplays()');
    assert.equal(app.run('vessels.get(1).predictionMarker'), null);
    assert.equal(app.elements.get('prediction-count').textContent, 0);
});

test('metadata fetch failure hides existing projections and reports configuration unavailable', async () => {
    const app = dashboard();
    app.context.batch = [vessel(1, projection())];
    app.run('processVesselData(batch, 0)');
    app.context.AbortController = AbortController;
    app.context.fetch = async () => { throw new Error('offline'); };
    await app.run('fetchMetadata()');
    assert.equal(app.run('vessels.get(1).predictionMarker'), null);
    assert.match(app.elements.get('mode-banner').textContent, /configuration unavailable/i);
    assert.match(app.elements.get('feed-status').textContent, /configuration unavailable/i);
});

test('navigation disclaimer is on the map page and remains present on mobile', () => {
    assert.match(html, /class="mode-note">For exploration · not for navigation/);
    assert.doesNotMatch(html, /\.mode-note[^{}]*\{[^}]*display:\s*none/);
    assert.doesNotMatch(script, /calculatePredictionPosition|PREDICTION_HOURS_AHEAD|MAX_PREDICTION_DISTANCE_NM|radiansToDegrees/);
});
