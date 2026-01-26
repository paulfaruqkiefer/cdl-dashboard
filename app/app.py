from flask import Flask, render_template, jsonify, request
import pandas as pd
import os
from pathlib import Path
from datetime import datetime, timedelta
import pickle
import time
from geopy.geocoders import Nominatim

app = Flask(__name__)

# ----------------------------
# Paths & Environment
# ----------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# ----------------------------
# Helpers
# ----------------------------

def simplify_df(df, status_label):
    """Standardize column names, keep Last Updated as string for tables."""
    df = df.rename(columns={
        "Name": "Provider Name",
        "PhysicalState": "State",
        "ProviderUpdatedOn": "Last Updated",
        "RemoveReason": "Reason"
    })
    if "City" in df.columns:
        df["City"] = df["City"].str.title()
    df["Last Updated"] = pd.to_datetime(df["Last Updated"], errors="coerce").dt.date.astype(str)
    df["Status"] = status_label
    return df[["Provider Name", "City", "State", "Last Updated", "Reason", "Status"]]

def load_data(status=None):
    dfs = []

    if status in [None, "in_review"]:
        in_review_file = DATA_DIR / "outputs_in_review" / "master_fmcsa_in_review.csv"
        if in_review_file.exists():
            dfs.append(simplify_df(pd.read_csv(in_review_file), "In Review"))

    if status in [None, "removed"]:
        removed_file = DATA_DIR / "outputs_removed" / "master_fmcsa_removed.csv"
        if removed_file.exists():
            dfs.append(simplify_df(pd.read_csv(removed_file), "Removed"))

    if dfs:
        return pd.concat(dfs, ignore_index=True).fillna("")
    return pd.DataFrame(columns=["Provider Name", "City", "State", "Last Updated", "Reason", "Status"])


def get_removals(state_filter=None):
    removed_file = DATA_DIR / "outputs_removed" / "master_fmcsa_removed.csv"
    if not removed_file.exists():
        return pd.DataFrame(columns=["Provider Name", "City", "State", "Last Updated", "Reason", "Removal Date"])

    df = pd.read_csv(removed_file)
    df = df.rename(columns={
        "Name": "Provider Name",
        "PhysicalState": "State",
        "ProviderUpdatedOn": "Last Updated",
        "RemoveReason": "Reason"
    })
    if "City" in df.columns:
        df["City"] = df["City"].str.title()
    df["Removal Date"] = pd.to_datetime(df["Last Updated"], errors="coerce").dt.date
    df["State"] = df["State"].str.replace(r"\s*\([A-Z]{2}\)$", "", regex=True).str.strip()
    if state_filter:
        df = df[df["State"].str.strip() == state_filter.strip()]
    return df[["Provider Name", "City", "State", "Last Updated", "Reason", "Removal Date"]]

# ----------------------------
# Routes
# ----------------------------

@app.route("/")
def index():
    token = os.environ.get("MAPBOX_TOKEN") or "YOUR_LOCAL_MAPBOX_TOKEN"
    return render_template("index.html", mapbox_token=token)

@app.route("/api/providers")
@app.route("/api/providers/<status>")
def providers_api(status=None):
    return jsonify(load_data(status).to_dict(orient="records"))

@app.route("/api/removed/metrics")
def removed_metrics():
    state_filter = request.args.get("state")
    df = get_removals(state_filter)
    if df.empty:
        return jsonify({"total": 0, "states": {}})
    today = datetime.today().date()
    last_30 = today - timedelta(days=30)
    recent = df[df["Removal Date"] >= last_30]
    total = len(recent)
    states_count = recent["State"].value_counts().to_dict()
    return jsonify({"total": total, "states": states_count})

@app.route("/api/removed/timeseries")
def removed_timeseries():
    state_filter = request.args.get("state")
    df_all = get_removals(None)
    if df_all.empty:
        return jsonify({"dates": [], "counts": [], "y_max": 0})
    df_all["Removal Date"] = pd.to_datetime(df_all["Removal Date"])
    min_month = df_all["Removal Date"].min().to_period("M")
    max_month = df_all["Removal Date"].max().to_period("M")
    all_months = pd.period_range(min_month, max_month, freq="M")
    global_monthly = df_all.groupby(df_all["Removal Date"].dt.to_period("M")).size()
    y_max = int(global_monthly.max())
    df = df_all
    if state_filter:
        df = df[df["State"] == state_filter]
    monthly = df.groupby(df["Removal Date"].dt.to_period("M")).size().reindex(all_months, fill_value=0)
    return jsonify({"dates": [p.strftime("%Y-%m") for p in all_months],
                    "counts": monthly.tolist(),
                    "y_max": y_max})

@app.route("/api/providers/counts_by_state/<status>")
def counts_by_state(status):
    df = load_data(status)
    if df.empty:
        return jsonify({})
    state_map = {"District of  Columbia": "District of Columbia",
                 "United States Minor Outlying Islands": "UM"}
    counts = {}
    for state, cnt in df["State"].value_counts().items():
        clean_state = " ".join(state.split("(")[0].strip().split())
        geo_name = state_map.get(clean_state, clean_state)
        counts[geo_name] = cnt
    return jsonify(counts)

# ----------------------------
# Geocoding
# ----------------------------
GEOCODE_CACHE = DATA_DIR / "outputs_current" / "city_coords.pkl"

def load_geocoded_points(df):
    if not GEOCODE_CACHE.exists():
        return pd.DataFrame()
    with open(GEOCODE_CACHE, "rb") as f:
        cache = pickle.load(f)
    rows = []
    for _, r in df.iterrows():
        city = str(r["City"]).strip().title()
        state = str(r["PhysicalState"]).split("(")[0].strip()
        key = f"{city}, {state}"
        if key in cache and cache[key][0] is not None:
            lat, lon = cache[key]
            rows.append((city, state, lat, lon))
    return pd.DataFrame(rows, columns=["City", "PhysicalState", "lat", "lon"])

@app.route("/api/providers/geocoded/<status>")
def geocoded_providers(status):
    file_map = {
        "removed": DATA_DIR / "outputs_removed" / "master_fmcsa_removed.csv",
        "in_review": DATA_DIR / "outputs_in_review" / "master_fmcsa_in_review.csv"
    }
    path = file_map.get(status)
    if not path or not path.exists():
        return jsonify([])
    df = pd.read_csv(path)
    df_geo = load_geocoded_points(df)
    if df_geo.empty:
        return jsonify([])
    agg = df_geo.groupby(["City", "PhysicalState", "lat", "lon"]).size().reset_index(name="count")
    return jsonify(agg.to_dict(orient="records"))

# ----------------------------
# Entry Point
# ----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
