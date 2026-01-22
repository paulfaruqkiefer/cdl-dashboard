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
PAGE_URL = f"{BASE_URL}/Provider/InReview"
API_URL = f"{BASE_URL}/api/Public/InReviewPublic"

OUTPUT_DIR = "outputs"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TODAY = date.today().strftime("%Y-%m-%d")
SNAPSHOT_CSV = os.path.join(OUTPUT_DIR, f"fmcsa_in_review_{TODAY}.csv")
MASTER_CSV = os.path.join(OUTPUT_DIR, "master_fmcsa_in_review.csv")

PAGE_SIZE = 100
MAX_RETRIES = 5
RETRY_SLEEP = 3
PAGE_SLEEP = 0.5

# ======================
# Session
# ======================

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
})

# ======================
# Helpers
# ======================

def get_verification_token():
    """Extract CSRF token from the In Review Providers page."""
    print("🔐 Fetching CSRF token...")
    r = session.get(PAGE_URL, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    token_input = soup.find("input", {"name": "__RequestVerificationToken"})

    if not token_input:
        raise RuntimeError("CSRF token not found on In Review page")

    return token_input["value"]


def fetch_page(start, length, token):
    """Fetch a single page from the InReviewPublic API with retries."""

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
        "Referer": PAGE_URL,
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = session.post(
                API_URL,
                data=payload,
                headers=headers,
                timeout=30,
            )

            if r.status_code == 500:
                print(f"⚠️ 500 error (attempt {attempt}/{MAX_RETRIES}) — retrying...")
                time.sleep(RETRY_SLEEP)
                continue

            r.raise_for_status()
            return r.json()

        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request failed (attempt {attempt}/{MAX_RETRIES}): {e}")
            time.sleep(RETRY_SLEEP)

    raise RuntimeError("FMCSA InReviewPublic API failed after all retries")


def save_csv(rows, path):
    """Write rows to CSV with dynamic columns."""
    if not rows:
        print(f"⚠️ No rows to write: {path}")
        return

    fieldnames = sorted({k for row in rows for k in row.keys()})

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"💾 Saved: {path}")

# ======================
# Main
# ======================

def main():
    token = get_verification_token()

    print("📥 Fetching first page...")
    first_page = fetch_page(start=0, length=10, token=token)

    total_records = first_page.get("recordsTotal", 0)
    print(f"📊 Total in-review providers: {total_records}")

    total_pages = math.ceil(total_records / PAGE_SIZE)
    all_rows = first_page.get("data", [])

    for page in tqdm(range(1, total_pages), desc="Fetching in-review pages"):
        start = page * PAGE_SIZE
        page_json = fetch_page(start=start, length=PAGE_SIZE, token=token)
        all_rows.extend(page_json.get("data", []))
        time.sleep(PAGE_SLEEP)

    print(f"✅ Downloaded {len(all_rows)} in-review providers")

    # --- Save snapshot ---
    save_csv(all_rows, SNAPSHOT_CSV)

    # --- Update master ---
    master_rows = []
    if os.path.exists(MASTER_CSV):
        with open(MASTER_CSV, "r", encoding="utf-8") as f:
            master_rows = list(csv.DictReader(f))

    existing_ids = {
        r.get("USDOTNumber")
        for r in master_rows
        if r.get("USDOTNumber")
    }

    new_rows = [
        row for row in all_rows
        if row.get("USDOTNumber") and row.get("USDOTNumber") not in existing_ids
    ]

    if new_rows:
        master_rows.extend(new_rows)
        save_csv(master_rows, MASTER_CSV)
        print(f"➕ Added {len(new_rows)} new providers to master file")
    else:
        print("ℹ️ No new providers to add to master file")


if __name__ == "__main__":
    main()
