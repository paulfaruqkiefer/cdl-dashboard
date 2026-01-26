import requests
from bs4 import BeautifulSoup
from pathlib import Path
from datetime import datetime
import hashlib
import pandas as pd

BASE_URL = "https://tpr.fmcsa.dot.gov"
SEARCH_URL = f"{BASE_URL}/Search"

OUTPUT_DIR = Path("data/outputs_current")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CURRENT_FILE = OUTPUT_DIR / "fmcsa_training_locations.xlsx"
KEEP_LAST_N = 5  # keep only the most recent N versions
DIFF_LOG = OUTPUT_DIR / "fmcsa_training_locations_column_diffs.log"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )
}


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def get_latest_xlsx_url(session: requests.Session) -> str:
    resp = session.get(SEARCH_URL, headers=HEADERS)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")

    link = soup.find("a", href=lambda x: x and x.endswith(".xlsx"))
    if not link:
        raise RuntimeError("Could not find XLSX download link on page")

    return BASE_URL + link["href"]


def rotate_old_files():
    files = sorted(
        OUTPUT_DIR.glob("fmcsa_training_locations_*.xlsx"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for old in files[KEEP_LAST_N:]:
        old.unlink()
        print(f"Removed old archive: {old.name}")


def normalize_training_location_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normalize FMCSA training location headers:
    - Appends license class modifiers to column names
    - Drops the first two header rows
    - Promotes the third row to column headers
    """

    HEADER_ROW = 2  # third row (0-based)

    COLUMN_GROUPS = {
        "Class A": range(13, 16),
        "Class B": range(16, 19),
        "Passenger": range(19, 22),
        "School Bus": range(22, 25),
        "Hazardous Materials": range(25, 26),
    }

    for label, cols in COLUMN_GROUPS.items():
        for col in cols:
            base_name = df.iloc[HEADER_ROW, col]
            if pd.notna(base_name):
                df.iloc[HEADER_ROW, col] = f"{base_name} ({label})"

    # Drop first two rows
    df = df.iloc[2:].reset_index(drop=True)

    # Promote modified row to headers
    df.columns = df.iloc[0].astype(str).str.strip()
    df = df.iloc[1:].reset_index(drop=True)

    return df


def log_column_diffs(old_df: pd.DataFrame, new_df: pd.DataFrame):
    """Log differences between old and new column headers."""
    old_cols = set(old_df.columns)
    new_cols = set(new_df.columns)

    added = new_cols - old_cols
    removed = old_cols - new_cols

    if added or removed:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(DIFF_LOG, "a") as f:
            f.write(f"\n--- {timestamp} ---\n")
            if added:
                f.write(f"Added columns: {sorted(added)}\n")
            if removed:
                f.write(f"Removed columns: {sorted(removed)}\n")
        print(f"Logged column changes: +{len(added)}, -{len(removed)}")


def download_latest_xlsx():
    with requests.Session() as session:
        session.headers.update(HEADERS)

        xlsx_url = get_latest_xlsx_url(session)
        print(f"Found XLSX: {xlsx_url}")

        resp = session.get(
            xlsx_url,
            headers={**HEADERS, "Referer": SEARCH_URL},
            stream=True,
        )
        resp.raise_for_status()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")
        archive_path = OUTPUT_DIR / f"fmcsa_training_locations_{timestamp}.xlsx"

        with open(archive_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        # ---- sanity check: make sure it's a real Excel file ----
        try:
            df = pd.read_excel(archive_path, header=None)
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise RuntimeError("Downloaded file is not a valid XLSX")

        # ---- normalize headers ----
        df = normalize_training_location_headers(df)

        # ---- skip if suspiciously small ----
        if len(df) < 1000:
            archive_path.unlink(missing_ok=True)
            raise RuntimeError(f"Suspiciously small XLSX ({len(df)} rows)")

        # ---- log column diffs if current file exists ----
        if CURRENT_FILE.exists():
            old_df = pd.read_excel(CURRENT_FILE)
            log_column_diffs(old_df, df)

            # skip if unchanged
            if file_hash(CURRENT_FILE) == file_hash(archive_path):
                print("No change from previous version — skipping update")
                archive_path.unlink()
                return

        # ---- promote to current ----
        df.to_excel(CURRENT_FILE, index=False)
        print(f"Updated current file: {CURRENT_FILE.name}")

        # ---- rotate old versions ----
        rotate_old_files()


if __name__ == "__main__":
    download_latest_xlsx()
