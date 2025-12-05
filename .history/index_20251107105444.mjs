// index.mjs — Ontario Hair/Beauty map + API (free, OSM/Overpass)
// Run once to install deps: npm i express node-fetch@3 csv-stringify p-limit

import express from "express";
import fetch from "node-fetch";
import { stringify } from "csv-stringify/sync";
import pLimit from "p-limit";

const app = express();
const PORT = process.env.PORT || 8080;

/* --------------------------- INLINE MAP HOMEPAGE --------------------------- */
app.get("/", (_req, res) => {
  res.type("html").send(`<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Ontario Hair/Beauty — Map</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
  <script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
  <style>
    :root { --b:#0b1020; --p:#111831; --t:#e5e7eb; --mut:#94a3b8; --acc:#60a5fa; }
    body{margin:0;font-family:system-ui,Segoe UI,Roboto,Arial;background:#fff;color:#111}
    header{padding:.5rem .75rem;border-bottom:1px solid #e5e7eb;background:#fff;position:sticky;top:0;z-index:10}
    .row{display:flex;gap:.5rem;align-items:center;flex-wrap:wrap}
    input,select,button{padding:.45rem .6rem;border:1px solid #d1d5db;border-radius:.5rem}
    a{color:#2563eb;text-decoration:none}
    #map{height:calc(100vh - 56px)}
    .badge{font-size:.9rem;color:#6b7280}
  </style>
</head>
<body>
  <header>
    <div class="row">
      <strong>Ontario Hair / Beauty</strong>
      <input id="q" type="search" placeholder="Search name, city, or 'Niagara'…"/>
      <select id="type">
        <option value="">All types</option>
        <option value="hairdresser">Hairdresser (tag)</option>
        <option value="beauty">Beauty (tag)</option>
        <option value="spa">Spa (tag)</option>
        <option value="barber">Barber (name)</option>
        <option value="salon">Salon (name)</option>
        <option value="saloon">Saloon (name)</option>
      </select>
      <button id="reset">Reset</button>
      <span class="badge" id="count">loading…</span>
      <a href="/api/ontario/hair-salons.csv" style="margin-left:auto">Download CSV</a>
    </div>
  </header>
  <div id="map"></div>

  <script>
    const API_URL = '/api/ontario/hair-salons';

    const map = L.map('map', { preferCanvas: true }).setView([44, -79.5], 6);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
      maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    const cluster = L.markerClusterGroup({ disableClusteringAtZoom: 16 }).addTo(map);

    let raw = [], markers = [];

    function cityFromAddress(addr){
      if(!addr) return '';
      const parts = addr.split(',').map(s=>s.trim());
      if(parts.length>=2) return parts[parts.length-2];
      return parts[0]||'';
    }

    function matches(it, q, type){
      const name = (it.name || '').toLowerCase();
      const city = cityFromAddress(it.address).toLowerCase();
      const fullAddr = (it.address || '').toLowerCase();
      const hay = [name, city, fullAddr].join(' ');

      // dropdown type
      if (type) {
        const tag = (it.shop || '').toLowerCase();
        if (type === 'barber') { if (!name.includes('barber')) return false; }
        else if (type === 'salon') { if (!name.includes('salon')) return false; }
        else if (type === 'saloon') { if (!name.includes('saloon')) return false; }
        else if (type === 'spa') { if (tag !== 'spa' && !fullAddr.includes('spa')) return false; }
        else { if (tag !== type) return false; } // hairdresser/beauty tag
      }

      // text search
      if (q) {
        const t = q.toLowerCase().trim();
        const niagaraCities = [
          "niagara falls","niagara-on-the-lake","st. catharines","st catharines",
          "welland","thorold","pelham","grimsby","lincoln","fort erie",
          "port colborne","wainfleet","west lincoln"
        ];
        if (t === 'niagara') {
          const hit = niagaraCities.some(c => hay.includes(c)) || fullAddr.includes('niagara');
          if (!hit) return false;
        } else {
          const terms = t.split(/\\s+/).filter(Boolean);
          for (const term of terms) { if (!hay.includes(term)) return false; }
        }
      }
      return true;
    }

    function popup(it){
      const rows = [];
      rows.push('<strong>' + (it.name||'Unknown').replace(/</g,'&lt;') + '</strong>');
      if (it.address) rows.push(it.address.replace(/</g,'&lt;'));
      if (it.phone) rows.push('📞 ' + it.phone);
      const links = [];
      if (it.website) links.push('<a target="_blank" rel="noopener" href="'+it.website+'">Website</a>');
      links.push('<a target="_blank" rel="noopener" href="https://www.openstreetmap.org/'+it.osm_type+'/'+it.osm_id+'">OSM</a>');
      rows.push(links.join(' · '));
      return rows.join('<br/>');
    }

    function refresh(){
      const q = document.getElementById('q').value.trim();
      const type = document.getElementById('type').value;
      cluster.clearLayers(); markers.length = 0;
      const shown = [];
      for (const it of raw){
        if (!it.lat || !it.lon) continue;
        if (!matches(it, q, type)) continue;
        const m = L.marker([it.lat, it.lon]).bindPopup(popup(it));
        markers.push(m); shown.push(it);
      }
      cluster.addLayers(markers);
      document.getElementById('count').textContent = shown.length.toLocaleString() + ' shown';
      if (markers.length){
        const group = L.featureGroup(markers);
        map.fitBounds(group.getBounds().pad(0.1));
      }
    }

    async function boot(){
      try{
        let r = await fetch(API_URL);
        let j = await r.json();
        if ((!j.data || j.data.length === 0)) {
          await fetch(API_URL + '?force=1');
          await new Promise(res => setTimeout(res, 1500));
          r = await fetch(API_URL);
          j = await r.json();
        }
        raw = j.data || [];
        refresh();
      }catch(e){
        console.error(e);
        alert('Failed to load data. Try opening '+API_URL+'?force=1 once, then reload.');
      }
    }

    document.getElementById('q').addEventListener('input',()=>{ clearTimeout(window.__t); window.__t=setTimeout(refresh,150); });
    document.getElementById('type').addEventListener('change',refresh);
    document.getElementById('reset').addEventListener('click',()=>{ q.value=''; type.value=''; refresh(); });
    boot();
  </script>
</body>
</html>`);
});

/* --------------------------- DATA / API LAYER ------------------------------ */

// You can swap to another mirror if one is busy:
// const OVERPASS_URL = "https://overpass-api.de/api/interpreter";
const OVERPASS_URL = "https://overpass.kumi.systems/api/interpreter";
// Fallbacks you can try if needed:
// "https://overpass-api.nextzen.org/api/interpreter"

function buildOverpassQuery() {
  return `
[out:json][timeout:300];
area["name"="Ontario"]["boundary"="administrative"]->.searchArea;

// Pull hairdresser/beauty/spa plus names containing salon/saloon/barber
(
  node["shop"="hairdresser"](area.searchArea);
  way["shop"="hairdresser"](area.searchArea);
  relation["shop"="hairdresser"](area.searchArea);

  node["shop"="beauty"](area.searchArea);
  way["shop"="beauty"](area.searchArea);
  relation["shop"="beauty"](area.searchArea);

  node["amenity"="spa"](area.searchArea);
  way["amenity"="spa"](area.searchArea);
  relation["amenity"="spa"](area.searchArea);

  node(area.searchArea)["name"~"(salon|saloon|barber)", i];
  way(area.searchArea)["name"~"(salon|saloon|barber)", i];
  relation(area.searchArea)["name"~"(salon|saloon|barber)", i];
);

// Exclude pubs/bars that match 'saloon' by accident
(
  ._;
  - node["amenity"~"^(pub|bar)$"];
  - way["amenity"~"^(pub|bar)$"];
  - relation["amenity"~"^(pub|bar)$"];
);

out center tags;`;
}

function normalizeElement(el) {
  const lat = el.lat ?? el.center?.lat ?? null;
  const lon = el.lon ?? el.center?.lon ?? null;
  const tags = el.tags || {};
  return {
    osm_type: el.type,
    osm_id: el.id,
    name: tags.name || null,
    shop: tags.shop || null, // 'hairdresser' | 'beauty' | ...
    phone: tags.phone || tags["contact:phone"] || null,
    website: tags.website || tags["contact:website"] || null,
    opening_hours: tags.opening_hours || null,
    address: (() => {
      const parts = [];
      if (tags["addr:housenumber"]) parts.push(tags["addr:housenumber"]);
      if (tags["addr:street"]) parts.push(tags["addr:street"]);
      if (tags["addr:city"]) parts.push(tags["addr:city"]);
      if (tags["addr:postcode"]) parts.push(tags["addr:postcode"]);
      return parts.length ? parts.join(", ") : tags["addr:full"] || null;
    })(),
    lat, lon,
    raw_tags: tags
  };
}

const limit = pLimit(4);

async function queryOverpass() {
  const q = buildOverpassQuery();
  const res = await fetch(OVERPASS_URL, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
    body: "data=" + encodeURIComponent(q),
  });
  if (!res.ok) throw new Error("Overpass error: " + res.status + " " + await res.text());
  const data = await res.json();
  if (!data.elements) return [];
  const dedupe = new Map();
  for (const el of data.elements) {
    const key = `${el.type}/${el.id}`;
    if (!dedupe.has(key)) dedupe.set(key, normalizeElement(el));
  }
  return [...dedupe.values()];
}

// Simple 24h in-memory cache
let cachedResult = null;
let cacheTimestamp = 0;
const CACHE_TTL_MS = 1000 * 60 * 60 * 24;

app.get("/api/ontario/hair-salons", async (req, res) => {
  try {
    const force = req.query.force === "1";
    const now = Date.now();
    if (!force && cachedResult && (now - cacheTimestamp) < CACHE_TTL_MS) {
      return res.json({ source: "cache", count: cachedResult.length, data: cachedResult });
    }
    const data = await limit(() => queryOverpass());
    cachedResult = data; cacheTimestamp = now;
    res.json({ source: "overpass", count: data.length, data });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: String(err) });
  }
});

app.get("/api/ontario/hair-salons.csv", async (_req, res) => {
  try {
    if (!cachedResult) { cachedResult = await queryOverpass(); cacheTimestamp = Date.now(); }
    const header = ["osm_type","osm_id","name","shop","phone","website","opening_hours","address","lat","lon"];
    const rows = cachedResult.map(r => header.map(h => r[h] ?? ""));
    const csv = stringify([header, ...rows]);
    res.setHeader("Content-Type","text/csv; charset=utf-8");
    res.send(csv);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: String(err) });
  }
});

/* --------------------------------- START ---------------------------------- */
app.listen(PORT, () => {
  console.log("Overpass-based server running at http://localhost:" + PORT);
  console.log("GET /                           (Map UI)");
  console.log("GET /api/ontario/hair-salons    (JSON)");
  console.log("GET /api/ontario/hair-salons.csv (CSV)");
});
