let currentStatus = "in_review";
let table;
let map;
let geojsonLayer;
let currentData = [];
let selectedState = null;

/* ==========================
   UTILITIES
========================== */

// Extract state name from "Washington (WA)"
function normalizeState(providerState) {
    if (!providerState) return "";
    return providerState.split(" (")[0].trim();
}

// Count providers per state
function countByState(data) {
    const counts = {};
    data.forEach(d => {
        const state = normalizeState(d.State);
        if (!state) return;
        counts[state] = (counts[state] || 0) + 1;
    });
    return counts;
}

// Color scale for provider counts
function getColor(count) {
    return count > 200 ? "#7f2704" :
           count > 100 ? "#cc4c02" :
           count > 50  ? "#ec7014" :
           count > 20  ? "#fe9929" :
           count > 0   ? "#fdd49e" :
                         "#f0f0f0";
}

/* ==========================
   TABLE
========================== */

function loadTable(status, stateFilter = null) {
    currentStatus = status;

    if ($.fn.DataTable.isDataTable("#providers-table")) {
        table.destroy();
        $("#providers-table tbody").empty();
    }

   $.getJSON(`/api/providers/${status}`, function(data) {
    currentData = data;

    const filtered = stateFilter
        ? data.filter(d => normalizeState(d.State) === stateFilter)
        : data;

    //  IF EMPTY: inject a placeholder row
    const tableData = filtered.length === 0
        ? [{
            "Provider Name": "—",
            "City": "—",
            "State": "—",
            "Last Updated": "—",
            "Reason": "No providers have been removed yet"
        }]
        : filtered;

    table = $("#providers-table").DataTable({
        data: tableData,
        columns: [
            { data: "Provider Name" },
            { data: "City" },
            { data: "State" },
            { data: "Last Updated" },
            { data: "Reason" }
        ],
        pageLength: 25,
        lengthMenu: [10, 25, 50, 100],
        order: filtered.length === 0 ? [] : [[3, "desc"]],
        responsive: true,
        searching: filtered.length !== 0,
        paging: filtered.length !== 0,
        info: filtered.length !== 0
    });

    updateMap();
});

}

/* ==========================
   MAP
========================== */

function initMap() {
    // Initialize map without any basemap
    map = L.map("state-map", {
        zoomControl: true,
        scrollWheelZoom: false,
        attributionControl: false
    });

    // Set initial view: center on lower 48, zoom level 5 (tweak as needed)
    map.setView([39.8, -98.5], 4);

    // Load US states GeoJSON
    $.getJSON("/static/us-states.json", function(states) {
        geojsonLayer = L.geoJSON(states, {
            style: baseStyle,
            onEachFeature: onEachState
        }).addTo(map);

        // Apply initial coloring based on currentData (even if empty at first)
        updateMap();

        // Add your legend
        addLegend();
    });
}



// Helper to flatten GeoJSON coordinates (handles Polygons and MultiPolygons)
function flattenCoords(coords) {
    if (!Array.isArray(coords[0][0])) {
        // Polygon: [[lng, lat], ...]
        return coords.map(c => L.latLng(c[1], c[0]));
    } else {
        // MultiPolygon: [[[lng, lat], ...], ...]
        return coords.flatMap(p => p.map(c => L.latLng(c[1], c[0])));
    }
}


function baseStyle(feature) {
    return {
        color: "#666",
        weight: 0.5,
        fillColor: "#f0f0f0",
        fillOpacity: 0.8
    };
}

function highlightStyle() {
    return {
        weight: 1,
        color: "#333",
        fillOpacity: 0.9
    };
}

function onEachState(feature, layer) {
    const stateName = feature.properties.NAME;

    layer.on({
        mouseover: e => {
            if (selectedState && selectedState !== stateName) return;
            e.target.setStyle(highlightStyle());
        },
        mouseout: e => {
            if (selectedState && selectedState === stateName) return;
            geojsonLayer.resetStyle(e.target);
            applyStateColor(e.target);
        },
        click: () => toggleState(stateName)
    });
}

function toggleState(state) {
    if (selectedState === state) {
        selectedState = null;
        loadTable(currentStatus);
        $("#state-count").text("Click a state to filter");
    } else {
        selectedState = state;
        loadTable(currentStatus, state);
        const count = countByState(currentData)[state] || 0;
        $("#state-count").text(`${state}: ${count} providers`);
    }

    updateMap();
}

function applyStateColor(layer) {
    const state = layer.feature.properties.NAME;
    const counts = countByState(currentData);
    const count = counts[state] || 0;

    layer.setStyle({
        fillColor: getColor(count),
        fillOpacity: 0.8,
        weight: selectedState === state ? 1.5 : 0.5
    });

    layer.bindTooltip(
        `<strong>${state}</strong><br>${count} providers`,
        { sticky: true }
    );
}

function updateMap() {
    if (!geojsonLayer) return;

    geojsonLayer.eachLayer(layer => applyStateColor(layer));
}

/* ==========================
   TOGGLE BUTTONS
========================== */

$(".toggle-buttons button").click(function() {
    $(".toggle-buttons button").removeClass("active");
    $(this).addClass("active");

    selectedState = null;

    const status = this.id === "btn-in-review" ? "in_review" : "removed";
    loadTable(status);
});


/* ==========================
   INIT
========================== */

$(document).ready(function() {
    initMap();
    loadTable(currentStatus);
});
