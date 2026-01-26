from pathlib import Path
import pandas as pd
import pickle
from geopy.geocoders import Nominatim

# Path to your CSV
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
removed_file = DATA_DIR / "outputs_removed" / "master_fmcsa_removed.csv"

df = pd.read_csv(removed_file)
df["City"] = df["City"].str.title()
df["State"] = df["PhysicalState"].str.strip()  # adjust if needed

# Minimal geocode function
def geocode_city_state(city, state, geolocator):
    key = f"{city}, {state}"
    return geolocator.geocode(key)

def geocode_providers(df, city_col="City", state_col="State"):
    geolocator = Nominatim(user_agent="cdl_dashboard")
    latitudes, longitudes = [], []

    for i, row in df.iterrows():
        try:
            loc = geocode_city_state(row[city_col], row[state_col], geolocator)
            if loc:
                latitudes.append(loc.latitude)
                longitudes.append(loc.longitude)
            else:
                latitudes.append(None)
                longitudes.append(None)
        except Exception as e:
            print(f"Error geocoding {row[city_col]}, {row[state_col]}: {e}")
            latitudes.append(None)
            longitudes.append(None)

    df["lat"] = latitudes
    df["lon"] = longitudes
    return df.dropna(subset=["lat", "lon"])

df_geo = geocode_providers(df.head(5))  # just first 5 rows to test
print(df_geo[["City", "State", "lat", "lon"]])
