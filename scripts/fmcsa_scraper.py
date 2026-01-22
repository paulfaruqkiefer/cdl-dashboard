import requests
from bs4 import BeautifulSoup
import csv
import math
import os
import time
from datetime import date
from tqdm import tqdm

# ======================
# Configuration
# ======================

BASE_URL = "https://tpr.fmcsa.dot.gov"

ENDPOINTS = {
    "in_review": {
        "page": f"{BASE_URL}/Provider/InReview",
        "api": f"{BASE_URL}/api/Public/InReviewPublic",
        "master_file": "master_fmcsa_in_review.csv"
    },
    "removed": {
        "page": f"{BASE_URL}/Provider/Removed",
        "api": f"{BASE_URL}/api/Public/RemovedPublic",
        "master_file": "master_fmcsa_removed.csv"
    }
}

PAGE_SIZE = 100
MAX_RETRIES = 5
RETRY_SLEEP = 3
PAGE_SLEEP = 0.5

# ======================
# Helpers
# ======================

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

def ensure_dir(path):
    """Create directory if it doesn't exist, return absolute path."""
    abs_path = os.path.abspath(path)
    os.makedirs(abs_path, exist_ok=True)
    print(f"Ensured directory exists: {abs_path}")
    return abs_path

def get_verification_token(page_url):
    """Extract CSRF token from a page."""
    print(f"Fetching CSRF token from {page_url}...")
    r = session.get(page_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if not token_input:
        raise RuntimeError(f"CSRF token not found on {page_url}")
    return token_input["value"]

def fetch_page(api_url, start, length, token, page_name):
    """Fetch one page from API with retries."""
    payload = {
        "draw": 1,
        "start": start,
        "length": length,
        "order[0][column]": 2,
        "order[0][dir]": "desc",
        "columns[0][data]": "Name",
        "columns[1][data]": "City",
        "columns[2][data]": "PhysicalState",
        "search[regex]": "false",
        "__RequestVerificationToken": token,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": ENDPOINTS[page_name]["page"],
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.post(api_url, data=payload, headers=headers, timeout=30)
            if r.status_code == 500:
                print(f"500 error (attempt {attempt}/{MAX_RETRIES}) — retrying...")
                time.sleep(RETRY_SLEEP)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            print(f"Request failed (attempt {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(RETRY_SLEEP)
    raise RuntimeError(f"{page_name} API failed after all retries")

def save_csv(rows, path):
    if not rows:
        print(f"No rows to write: {path}")
        return
    fieldnames = sorted({k for row in rows for k in row.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved: {path}")

def update_master(all_rows, master_path):
    master_rows = []
    if os.path.exists(master_path):
        with open(master_path, "r", encoding="utf-8") as f:
            master_rows = list(csv.DictReader(f))

    existing_ids = {r.get("USDOTNumber") for r in master_rows if r.get("USDOTNumber")}
    new_rows = [row for row in all_rows if row.get("USDOTNumber") and row.get("USDOTNumber") not in existing_ids]

    if new_rows:
        master_rows.extend(new_rows)
        save_csv(master_rows, master_path)
        print(f"Added {len(new_rows)} new providers to master file")
    else:
        print("ℹNo new providers to add to master file")

# ======================
# Fetch all pages
# ======================

def fetch_all(page_name):
    endpoint = ENDPOINTS[page_name]

    # Ensure data and output subfolders exist
    data_dir = ensure_dir(os.path.join("data"))
    snapshot_dir = ensure_dir(os.path.join(data_dir, f"outputs_{page_name}"))

    # Master CSV stays in data folder
    master_file_path = os.path.join(data_dir, endpoint["master_file"])

    # Daily snapshot CSV goes in outputs_in_review or outputs_removed
    snapshot_file = os.path.join(snapshot_dir, f"{page_name}_{date.today().strftime('%Y-%m-%d')}.csv")

    token = get_verification_token(endpoint["page"])
    print(f"Fetching first page of {page_name}...")
    first_page = fetch_page(endpoint["api"], start=0, length=10, token=token, page_name=page_name)

    total_records = first_page.get("recordsTotal", 0)
    print(f"Total {page_name.replace('_',' ')} providers: {total_records}")

    total_pages = math.ceil(total_records / PAGE_SIZE)
    all_rows = first_page.get("data", [])

    for page in tqdm(range(1, total_pages), desc=f"Fetching {page_name} pages"):
        start = page * PAGE_SIZE
        page_json = fetch_page(endpoint["api"], start=start, length=PAGE_SIZE, token=token, page_name=page_name)
        all_rows.extend(page_json.get("data", []))
        time.sleep(PAGE_SLEEP)

    print(f"Downloaded {len(all_rows)} {page_name.replace('_',' ')} providers")
    save_csv(all_rows, snapshot_file)
    update_master(all_rows, master_file_path)

# ======================
# Main
# ======================

def main():
    for page_name in ["in_review", "removed"]:
        fetch_all(page_name)

if __name__ == "__main__":
    main()
