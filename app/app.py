from flask import Flask, render_template, jsonify
import pandas as pd
import os
import glob
from pathlib import Path

# ----------------------------
# App + paths
# ----------------------------

app = Flask(__name__)

# Project root (…/cdl-dashboard)
BASE_DIR = Path(__file__).resolve().parent.parent

# data/
DATA_DIR = BASE_DIR / "data"

# ----------------------------
# Helpers
# ----------------------------

def latest_file(folder, pattern="*.csv"):
    """Return the latest file in a folder matching a pattern, or None."""
    files = glob.glob(str(Path(folder) / pattern))
    if not files:
        return None
    return max(files, key=os.path.getmtime)

def simplify_df(df, status_label):
    """
    Standardize column names, simplify 'Last Updated', title-case city names,
    and add Status column.
    """
    df = df.rename(columns={
        "Name": "Provider Name",
        "PhysicalState": "State",
        "ProviderUpdatedOn": "Last Updated",
        "RemoveReason": "Reason"
    })

    # Simplify Last Updated to YYYY-MM-DD
    df["Last Updated"] = (
        pd.to_datetime(df["Last Updated"], errors="coerce")
        .dt.date
        .astype(str)
    )

    # Title-case city names
    if "City" in df.columns:
        df["City"] = df["City"].str.title()

    df["Status"] = status_label

    return df[["Provider Name", "City", "State", "Last Updated", "Reason", "Status"]]

def load_data(status=None):
    """
    Load latest CSVs.
    status: 'in_review', 'removed', or None for both combined.
    """
    dataframes = []

    # In Review
    if status in [None, "in_review"]:
        in_review_csv = latest_file(DATA_DIR / "outputs_in_review")
        if in_review_csv:
            df_in_review = pd.read_csv(in_review_csv)
            df_in_review = simplify_df(df_in_review, "In Review")
            dataframes.append(df_in_review)

    # Removed
    if status in [None, "removed"]:
        removed_csv = latest_file(DATA_DIR / "outputs_removed")
        if removed_csv:
            df_removed = pd.read_csv(removed_csv)
            df_removed = simplify_df(df_removed, "Removed")
            dataframes.append(df_removed)

    if dataframes:
        combined = pd.concat(dataframes, ignore_index=True)
        combined.fillna("", inplace=True)
        return combined

    return pd.DataFrame(
        columns=["Provider Name", "City", "State", "Last Updated", "Reason", "Status"]
    )

# ----------------------------
# Routes
# ----------------------------

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/providers")
@app.route("/api/providers/<status>")
def providers_api(status=None):
    df = load_data(status)
    return jsonify(df.to_dict(orient="records"))

def load_removals():
    """
    Compare master CSVs and return providers that shifted from In Review → Removed.
    """
    in_review_master = DATA_DIR / "outputs_in_review" / "master_fmcsa_in_review.csv"
    removed_master = DATA_DIR / "outputs_removed" / "master_fmcsa_removed.csv"

    if not in_review_master.exists() or not removed_master.exists():
        return pd.DataFrame(
            columns=["Provider Name", "City", "State", "Last Updated", "Reason", "Removal Date"]
        )

    df_in_review = pd.read_csv(in_review_master)
    df_removed = pd.read_csv(removed_master)

    # Providers in Removed that were previously In Review
    in_review_ids = set(df_in_review["Name"])
    shifted = df_removed[df_removed["Name"].isin(in_review_ids)].copy()

    if not shifted.empty:
        shifted = shifted.rename(columns={
            "Name": "Provider Name",
            "PhysicalState": "State",
            "ProviderUpdatedOn": "Last Updated",
            "RemoveReason": "Reason"
        })

        shifted["City"] = shifted["City"].str.title()
        shifted["Removal Date"] = (
            pd.to_datetime(shifted["Last Updated"], errors="coerce")
            .dt.date
            .astype(str)
        )

        shifted = shifted[
            ["Provider Name", "City", "State", "Last Updated", "Reason", "Removal Date"]
        ]

    return shifted

@app.route("/api/removals")
def removals_api():
    df = load_removals()
    return jsonify(df.to_dict(orient="records"))

# ----------------------------
# Entry point (Render-safe)
# ----------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
