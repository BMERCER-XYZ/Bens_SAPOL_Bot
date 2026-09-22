const state = {
  data: null,
  date: null,
  dark: localStorage.getItem("camera-theme") === "dark",
  fixedVisible: true,
  mobileLayer: L.layerGroup(),
  fixedLayer: L.layerGroup()
};

const typeLabels = {
  PAC: "Pedestrian crossing",
  P2P: "Point to point",
  "I/section": "Intersection",
  Rail: "Level crossing",
  MPDC: "Mobile phone detection"
};

const map = L.map("map", { zoomControl: true, preferCanvas: true }).setView([-34.9285, 138.6007], 11);

function tileUrl(theme) {
  const variant = theme === "dark" ? "dark_all" : "light_all";
  return `https://{s}.basemaps.cartocdn.com/${variant}/{z}/{x}/{y}{r}.png?key=${encodeURIComponent(state.data.tile_key)}`;
}

let tiles;
function setTheme(dark) {
  state.dark = dark;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.getElementById("theme-toggle").textContent = dark ? "Switch to light" : "Switch to dark";
  if (tiles) map.removeLayer(tiles);
  tiles = L.tileLayer(tileUrl(dark ? "dark" : "light"), {
    attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    subdomains: "abcd",
    maxZoom: 20
  }).addTo(map);
  localStorage.setItem("camera-theme", dark ? "dark" : "light");
}

function markerIcon(fixed = false) {
  return L.divIcon({ className: fixed ? "fixed-pin" : "camera-pin", iconSize: [16, 16], iconAnchor: [8, 8] });
}

function popupFor(camera, fixed = false) {
  const type = fixed ? `<br><strong>${typeLabels[camera.type] || camera.type}</strong>` : "";
  return `<strong>${camera.name}</strong>${type}${camera.region ? `<br>${camera.region}` : ""}`;
}

function addCameraMarkers(cameras, layer, fixed = false) {
  cameras.filter(camera => camera.lat !== null && camera.lon !== null).forEach(camera => {
    L.marker([camera.lat, camera.lon], { icon: markerIcon(fixed) })
      .bindPopup(popupFor(camera, fixed))
      .addTo(layer);
  });
}

function renderLegend() {
  const legend = document.getElementById("legend");
  legend.innerHTML = `<span class="legend-item"><i class="legend-dot"></i> Mobile schedule</span><span class="legend-item"><i class="legend-dot fixed"></i> Fixed location</span>`;
}

function renderList(cameras) {
  const list = document.getElementById("camera-list");
  if (!cameras.length) {
    list.innerHTML = "<p class=\"empty\">No mobile cameras are listed for this date.</p>";
    return;
  }
  list.innerHTML = cameras.map(camera => {
    const distance = camera.distance == null ? "Distance unknown" : `${camera.distance.toFixed(1)} km`;
    return `<div class="camera-row"><p class="camera-name">${camera.name}</p><span class="camera-meta">${distance}</span></div>`;
  }).join("");
}

function renderDate() {
  const cameras = state.data.dates[state.date] || [];
  state.mobileLayer.clearLayers();
  state.fixedLayer.clearLayers();
  addCameraMarkers(cameras, state.mobileLayer);
  addCameraMarkers(state.data.fixed_cameras, state.fixedLayer, true);
  state.mobileLayer.addTo(map);
  if (state.fixedVisible) state.fixedLayer.addTo(map);
  document.getElementById("selected-date").textContent = new Date(`${state.date}T12:00:00`).toLocaleDateString("en-AU", { weekday: "long", day: "numeric", month: "long" });
  document.getElementById("mobile-count").textContent = cameras.length;
  renderList(cameras);
}

function moveDate(offset) {
  const dates = Object.keys(state.data.dates).sort();
  const index = dates.indexOf(state.date);
  const next = dates[index + offset];
  if (next) {
    state.date = next;
    document.getElementById("date-select").value = next;
    renderDate();
  }
}

function initialise(data) {
  state.data = data;
  const dates = Object.keys(data.dates).sort();
  state.date = dates.find(date => date >= new Date().toISOString().slice(0, 10)) || dates[dates.length - 1];
  const select = document.getElementById("date-select");
  select.innerHTML = dates.map(date => `<option value="${date}">${new Date(`${date}T12:00:00`).toLocaleDateString("en-AU", { weekday: "short", day: "numeric", month: "short", year: "numeric" })}</option>`).join("");
  select.value = state.date;
  document.getElementById("updated-label").textContent = `${data.all_cameras.length} total mobile locations | Updated ${new Date(data.generated_at).toLocaleString("en-AU")}`;
  setTheme(state.dark);
  renderLegend();
  renderDate();
  const points = [...data.dates[state.date], ...data.fixed_cameras]
    .filter(camera => camera.lat !== null && camera.lon !== null)
    .map(camera => [camera.lat, camera.lon]);
  if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [24, 24] });
}

document.getElementById("theme-toggle").addEventListener("click", () => setTheme(!state.dark));
document.getElementById("fixed-toggle").addEventListener("change", event => {
  state.fixedVisible = event.target.checked;
  if (state.fixedVisible) state.fixedLayer.addTo(map); else map.removeLayer(state.fixedLayer);
});
document.getElementById("previous-day").addEventListener("click", () => moveDate(-1));
document.getElementById("next-day").addEventListener("click", () => moveDate(1));
document.getElementById("date-select").addEventListener("change", event => { state.date = event.target.value; renderDate(); });

fetch("data.json")
  .then(response => { if (!response.ok) throw new Error("data.json is not available yet"); return response.json(); })
  .then(initialise)
  .catch(error => {
    document.getElementById("selected-date").textContent = "Data unavailable";
    document.getElementById("camera-list").innerHTML = `<p class="empty">${error.message}. The daily GitHub Action will publish it after its next run.</p>`;
  });
