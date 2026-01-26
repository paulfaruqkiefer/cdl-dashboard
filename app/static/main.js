// mapbox token
mapboxgl.accessToken = MAPBOX_TOKEN;

const map = new mapboxgl.Map({
    container: "state-map",
    style: "mapbox://styles/mapbox/light-v11",
    center: [-98.5, 39.8],
    zoom: 4
});

map.addControl(new mapboxgl.NavigationControl());

let statesGeoJSON = null;
let popup = new mapboxgl.Popup({ closeButton: false, closeOnClick: false });
let removalsChart = null;

// -----------------------------
// Populate state dropdown
// -----------------------------
function populateStateDropdown(states) {
    const select = $("#state-select");
    select.empty();
    select.append('<option value="">All States</option>');
    states.forEach(s => select.append(`<option value="${s}">${s}</option>`));
}

// -----------------------------
// Load recent removals tracker & chart
// -----------------------------
function loadRecentRemovals(stateFilter = null) {
    const params = stateFilter ? `?state=${encodeURIComponent(stateFilter)}` : "";

    // Total removed in last 30 days
    $.getJSON(`/api/removed/metrics${params}`, data => {
        $("#total-removed").text(data.total);
    });

    // Timeseries chart
    $.getJSON(`/api/removed/timeseries${params}`, ts => {
        const labels = ts.dates || [];
        const values = ts.counts || [];
        const canvas = document.getElementById("removals-chart");

        if (!canvas || labels.length === 0) return;

        if (removalsChart) {
            removalsChart.data.labels = labels;
            removalsChart.data.datasets[0].data = values;
            removalsChart.options.scales.y.min = 0;
            removalsChart.options.scales.y.max = stateFilter ? 300 : 4000;
            removalsChart.update();
            return;
        }

        removalsChart = new Chart(canvas.getContext("2d"), {
            type: "line",
            data: {
                labels,
                datasets: [{
                    label: "Providers removed per month",
                    data: values,
                    fill: true,
                    tension: 0.35
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false } },
                scales: {
                    x: { grid: { display: false } },
                    y: {
                        beginAtZero: true,
                        min: 0,
                        max: stateFilter ? 300 : 4000,
                        ticks: { precision: 0 }
                    }
                }
            }
        });
    });
}

// -----------------------------
// Map + layers
// -----------------------------
map.on("load", () => {
    fetch("/static/us-states.json")
        .then(res => res.json())
        .then(geojson => {
            statesGeoJSON = geojson;

            // -----------------------------
            // States source
            // -----------------------------
            map.addSource("states", { type: "geojson", data: statesGeoJSON });

            // -----------------------------
            // State fills
            // -----------------------------
            map.addLayer({
                id: "state-fills",
                type: "fill",
                source: "states",
                paint: {
                    "fill-color": "#eeeeee",
                    "fill-opacity": 0.4,
                    "fill-outline-color": "#888"
                }
            });

            // -----------------------------
            // State borders
            // -----------------------------
            map.addLayer({
                id: "state-borders",
                type: "line",
                source: "states",
                paint: {
                    "line-color": "#888",
                    "line-width": 0.5
                }
            });

            // -----------------------------
            // State hover tooltip
            // -----------------------------
            map.on("mousemove", "state-fills", e => {
                if (!e.features?.length) return;
                const { NAME, count = 0 } = e.features[0].properties;
                popup.setLngLat(e.lngLat)
                    .setHTML(`<strong>${NAME}</strong><br>${count} providers`)
                    .addTo(map);
            });

            map.on("mouseleave", "state-fills", () => popup.remove());

            // -----------------------------
            // State click → filter table
            // -----------------------------
                map.on("click", "state-fills", e => {
                    if (!e.features?.length) return;

                    const stateName = e.features[0].properties.NAME.trim(); // "New Mexico"
                    const activeStatus =
                        $(".toggle-buttons button.active").attr("id") === "btn-in-review"
                            ? "in_review"
                            : "removed";

                    $("#current-filter").text(`Showing providers in: ${stateName}`);
                    $("#state-select").val(stateName);

                    // Filter table using startsWith to match "New Mexico (NM)"
                    loadProviderTable(activeStatus, stateName);
                    loadRecentRemovals(stateName);
                });


            // -----------------------------
            // Initial data loads
            // -----------------------------
            loadStateCounts("removed");
            loadProviderTable("removed");
            loadRecentRemovals();

            // -----------------------------
            // State dropdown
            // -----------------------------
            const allStates = statesGeoJSON.features.map(f => f.properties.NAME).sort();
            populateStateDropdown(allStates);

            $("#state-select").on("change", function () {
                const state = $(this).val() || null;
                const activeStatus = $(".toggle-buttons button.active").attr("id") === "btn-in-review"
                    ? "in_review" : "removed";

                $("#current-filter").text(state ? `Showing providers in: ${state}` : "");
                loadProviderTable(activeStatus, state);
                loadRecentRemovals(state);
            });

            // -----------------------------
            // Provider point layers (removed / in_review)
            // -----------------------------
            ["removed", "in_review"].forEach(status => loadProviderSymbols(status));
        })
        .catch(err => console.error("Error loading US states GeoJSON:", err));
});

// -----------------------------
// Load state counts + single color scale
// -----------------------------
function loadStateCounts(status) {
    $.getJSON(`/api/providers/counts_by_state/${status}`, countsRaw => {
        if (!statesGeoJSON) return;

        const geo = JSON.parse(JSON.stringify(statesGeoJSON));
        const counts = {};
        for (const key in countsRaw) {
            const cleanKey = key.split("(")[0].replace(/\s+/g, ' ').trim();
            counts[cleanKey] = countsRaw[key];
        }

        geo.features.forEach(f => {
            const stateName = f.properties.NAME.replace(/\s+/g, ' ').trim();
            f.properties.count = counts[stateName] || 0;
        });
        map.getSource("states").setData(geo);

        $.when(
            $.getJSON("/api/providers/counts_by_state/removed"),
            $.getJSON("/api/providers/counts_by_state/in_review")
        ).done((removedData, inReviewData) => {
            const allCounts = [...Object.values(removedData[0]), ...Object.values(inReviewData[0])];
            const globalMax = Math.max(...allCounts, 1);

            map.setPaintProperty("state-fills", "fill-color", [
                "interpolate",
                ["linear"],
                ["get", "count"],
                0, "#eeeeee",
                Math.ceil(globalMax * 0.25), "#ffeda0",
                Math.ceil(globalMax * 0.5), "#feb24c",
                Math.ceil(globalMax * 0.75), "#f03b20",
                globalMax, "#bd0026"
            ]);
        });
    });
}

// -----------------------------
// Load provider table
// -----------------------------
// -----------------------------
// Load provider table
// -----------------------------
function loadProviderTable(status, stateFilter = null) {
    $.getJSON(`/api/providers/${status}`, data => {
        let filteredData = data;

        if (stateFilter) {
            filteredData = data.filter(d => {
                // Normalize the state field by removing " (XX)" suffix
                const normalizedState = d.State.replace(/\s*\([A-Z]{2}\)$/, "").trim();
                return normalizedState === stateFilter;
            });
        }

        // Destroy existing DataTable if it exists
        if ($.fn.DataTable.isDataTable("#providers-table")) {
            $("#providers-table").DataTable().destroy();
            $("#providers-table tbody").empty();
        }

        // Initialize DataTable
        $("#providers-table").DataTable({
            data: filteredData,
            columns: [
                { data: "Provider Name" },
                { data: "City" },
                { data: "State" },  // keep this as "State" for DataTables
                { data: "Last Updated" },
                { data: "Reason" }
            ],
            pageLength: 25,
            lengthMenu: [10, 25, 50, 100]
        });
    });
}


// -----------------------------
// Clear filter
// -----------------------------
$("#clear-filter").click(() => {
    const activeStatus = $(".toggle-buttons button.active").attr("id") === "btn-in-review" ? "in_review" : "removed";
    loadProviderTable(activeStatus, null);
    $("#state-select").val("");
    $("#current-filter").text("");
    loadRecentRemovals();
});

// -----------------------------
// Toggle buttons
// -----------------------------
$(document).ready(() => {
    $(".toggle-buttons button").click(function() {
        $(".toggle-buttons button").removeClass("active");
        $(this).addClass("active");
        const status = this.id === "btn-in-review" ? "in_review" : "removed";
        loadStateCounts(status);
        const state = $("#state-select").val() || null;
        loadProviderTable(status, state);
    });
});

// -----------------------------
// Wire state dropdown to chart + table updates
// -----------------------------
$("#state-select").change(function () {
    const state = $(this).val() || null;
    loadRecentRemovals(state);
    const activeStatus = $(".toggle-buttons button.active").attr("id") === "btn-in-review" ? "in_review" : "removed";
    loadProviderTable(activeStatus, state);
    $("#current-filter").text(state ? `Showing providers in: ${state}` : "");
});

// -----------------------------
// Symbol map layers for removed / in_review
// -----------------------------
function loadProviderSymbols(status) {
    $.getJSON(`/api/providers/geocoded/${status}`, data => {
        const features = data.map(d => ({
            type: "Feature",
            geometry: { type: "Point", coordinates: [d.lon, d.lat] },
            properties: {
                city: d.City,
                state: d.PhysicalState,
                count: d.count
            }
        }));

        const geojson = { type: "FeatureCollection", features };

        if (map.getSource(`${status}-points`)) {
            map.getSource(`${status}-points`).setData(geojson);
        } else {
            map.addSource(`${status}-points`, { type: "geojson", data: geojson });
            // Add circle layer **above state fills**
            map.addLayer({
                id: `${status}-layer`,
                type: "circle",
                source: `${status}-points`,
                paint: {
                    "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 2, 10, 6],
                    "circle-color": status === "removed" ? "#f03b20" : "#2b8cbe",
                    "circle-opacity": 0.6,
                    "circle-stroke-color": "#fff",
                    "circle-stroke-width": 1
                }
            }, "state-fills"); // ensures points render above fills
        }

        // -----------------------------
        // Point click tooltips (informational only)
        // -----------------------------
        map.on("click", `${status}-layer`, e => {
            if (!e.features?.length) return;
            const { city, state, count } = e.features[0].properties;
            new mapboxgl.Popup({ closeButton: true, closeOnClick: true })
                .setLngLat(e.lngLat)
                .setHTML(`<strong>${city}, ${state}</strong><br>${count} provider${count === 1 ? "" : "s"} `)
                .addTo(map);
        });

        map.on("mouseenter", `${status}-layer`, () => map.getCanvas().style.cursor = "pointer");
        map.on("mouseleave", `${status}-layer`, () => map.getCanvas().style.cursor = "");
    });
}

// -----------------------------
// Wire circle togges
// -----------------------------
$("#toggle-removed").click(function() {
    $(this).toggleClass("active");
    map.setLayoutProperty("removed-layer", "visibility", $(this).hasClass("active") ? "visible" : "none");
});

$("#toggle-in-review").click(function() {
    $(this).toggleClass("active");
    map.setLayoutProperty("in_review-layer", "visibility", $(this).hasClass("active") ? "visible" : "none");
});