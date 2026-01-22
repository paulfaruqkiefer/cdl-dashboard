import requests
from bs4 import BeautifulSoup
import csv
import math
import os
import time
from datetime import date
from tqdm import tqdm
import pandas as pd

# ======================
# Configuration
# ======================

BASE_URL = "https://tpr.fmcsa.dot.gov"

ENDPOINTS = {
    "in_review": {
        "page": f"{BASE_URL}/Provider/InReview",
        "api": f"{BASE_URL}/api/Public/InReviewPublic",
        "master_file": "data/outputs_in_review/master_fmcsa_in_review.csv",
        "snapshot_dir": "data/outputs_in_review"
    },
    "removed": {
        "page": f"{BASE_URL}/Provider/Removed",
        "api": f"{BASE_URL}/api/Public/RemovedPublic",
        "master_file": "data/outputs_removed/master_fmcsa_removed.csv",
        "snapshot_dir": "data/outputs_removed"
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
    os.makedirs(path, exist_ok=True)
    return path

def get_verification_token(page_url):
    r = session.get(page_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})
    if not token_input:
        raise RuntimeError(f"CSRF token not found on {page_url}")
    return token_input["value"]

def fetch_page(api_url, start, length, token, page_name):
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
                time.sleep(RETRY_SLEEP)
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException:
            time.sleep(RETRY_SLEEP)
    raise RuntimeError(f"{page_name} API failed after retries")

def save_csv(rows, path):
    if not rows:
        print(f"No rows to write: {path}")
        return
    fieldnames = sorted({k for row in rows for k in row.keys()})
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

def update_master(new_rows, master_path):
    """Append only new providers to the master CSV."""
    if os.path.exists(master_path):
        master_df = pd.read_csv(master_path)
    else:
        master_df = pd.DataFrame()

    new_df = pd.DataFrame(new_rows)

    if not master_df.empty:
        # Use 'Name' + 'PhysicalState' as unique key to prevent duplicates
        master_df = pd.concat([master_df, new_df]).drop_duplicates(subset=["Name", "PhysicalState"])
    else:
        master_df = new_df

    master_df.to_csv(master_path, index=False)
    print(f"Master updated: {master_path} ({len(master_df)} rows)")

# ======================
# Fetch all pages
# ======================

def fetch_all(page_name):
    endpoint = ENDPOINTS[page_name]

    # Ensure directories exist
    ensure_dir(endpoint["snapshot_dir"])
    token = get_verification_token(endpoint["page"])

    # Fetch first page to get total count
    first_page = fetch_page(endpoint["api"], 0, PAGE_SIZE, token, page_name)
    total_records = first_page.get("recordsTotal", 0)
    total_pages = math.ceil(total_records / PAGE_SIZE)

    all_rows = first_page.get("data", [])

    for page in tqdm(range(1, total_pages), desc=f"Fetching {page_name} pages"):
        start = page * PAGE_SIZE
        page_json = fetch_page(endpoint["api"], start, PAGE_SIZE, token, page_name)
        all_rows.extend(page_json.get("data", []))
        time.sleep(PAGE_SLEEP)

    # Save daily snapshot
    snapshot_file = os.path.join(endpoint["snapshot_dir"], f"{page_name}_{date.today()}.csv")
    save_csv(all_rows, snapshot_file)
    print(f"Snapshot saved: {snapshot_file}")

    # Update master CSV
    update_master(all_rows, endpoint["master_file"])

# ======================
# Main
# ======================

def main():
    for page_name in ["in_review", "removed"]:
        fetch_all(page_name)

if __name__ == "__main__":
    main()
