import pickle
from pathlib import Path

# Path to your geocode cache
GEOCODE_CACHE = Path("data/outputs_current/city_coords.pkl")

if not GEOCODE_CACHE.exists():
    print("Cache file not found!")
    exit()

# Load the cache
with open(GEOCODE_CACHE, "rb") as f:
    city_cache = pickle.load(f)

# Manual fixes: keys = "City, State" format
manual_fixes = {
    "San Juan Capo, California": (-117.6628, 33.5019),   # corrected coordinates
    "Sacramento, Ca, California": None          
}

# Apply fixes
for key, coords in manual_fixes.items():
    if coords is None:
        if key in city_cache:
            del city_cache[key]
            print(f"Removed {key} from cache")
    else:
        city_cache[key] = coords
        print(f"Set {key} -> {coords}")

# Save updated cache
with open(GEOCODE_CACHE, "wb") as f:
    pickle.dump(city_cache, f)

print("Cache updated successfully!")
