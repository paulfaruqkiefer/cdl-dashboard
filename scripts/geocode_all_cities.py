import pandas as pd
import pickle
import time
from pathlib import Path
from geopy.geocoders import Nominatim

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = DATA_DIR / "outputs_current" / "city_coords.pkl"

REMOVED = DATA_DIR / "outputs_removed" / "master_fmcsa_removed.csv"
IN_REVIEW = DATA_DIR / "outputs_in_review" / "master_fmcsa_in_review.csv"

def load_all_cities():
    dfs = []
    for path in [REMOVED, IN_REVIEW]:
        if path.exists():
            dfs.append(pd.read_csv(path, usecols=["City", "PhysicalState"]))
    df = pd.concat(dfs, ignore_index=True).dropna()
    df["City"] = df["City"].astype(str).str.strip().str.title()
    df["State"] = (
        df["PhysicalState"]
        .astype(str)
        .str.split("(").str[0]
        .str.strip()
    )
    return sorted(set(zip(df["City"], df["State"])))

def main():
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

    if CACHE_FILE.exists():
        with open(CACHE_FILE, "rb") as f:
            cache = pickle.load(f)
    else:
        cache = {}

    geolocator = Nominatim(user_agent="cdl_dashboard")

    cities = load_all_cities()
    missing = [(c, s) for c, s in cities if f"{c}, {s}" not in cache]

    print(f"Total cities: {len(cities)}")
    print(f"Already cached: {len(cache)}")
    print(f"To geocode: {len(missing)}")

    for city, state in missing:
        key = f"{city}, {state}"
        try:
            loc = geolocator.geocode(key, timeout=10)
            if loc:
                cache[key] = (loc.latitude, loc.longitude)
                print(f"✓ {key}")
            else:
                cache[key] = (None, None)
                print(f"✗ {key}")
        except Exception as e:
            cache[key] = (None, None)
            print(f"! {key}: {e}")

        time.sleep(1)

        # Save incrementally so crashes don’t lose progress
        with open(CACHE_FILE, "wb") as f:
            pickle.dump(cache, f)

    print("Geocoding complete.")

if __name__ == "__main__":
    main()
