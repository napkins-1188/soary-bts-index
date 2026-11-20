"""Build the rolling public BTS lookup files served by Soary."""
import argparse
import calendar
import csv
import gzip
import io
import json
import re
import shutil
import subprocess
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

BTS = "https://transtats.bts.gov/PREZIP/"
ARCHIVE = "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_"
BUCKETS = 16
FIELDS = (
    "Origin", "Dest", "CRSDepTime", "DepTime", "ArrTime", "DepDelay",
    "ActualElapsedTime",
)


def published_months():
    with urlopen(BTS, timeout=45) as response:
        listing = response.read().decode()
    all_months = {
        (int(year), int(month))
        for year, month in re.findall(rf"{ARCHIVE}(\d{{4}})_(\d{{1,2}})\.zip", listing)
    }
    months = sorted(all_months)[-24:]
    if len(months) != 24 or any(
        y2 * 12 + m2 != y1 * 12 + m1 + 1
        for (y1, m1), (y2, m2) in zip(months, months[1:])
    ):
        raise ValueError("BTS listing does not contain 24 consecutive months")
    return months


def build_month(job):
    (year, month), cache, output = job
    stem = f"{year}-{month:02d}"
    filename = f"{ARCHIVE}{year}_{month}.zip"
    archive = cache / f"bts-{stem}.zip"
    if not archive.exists():
        temporary = archive.with_suffix(".part")
        subprocess.run(
            ["curl", "--fail", "--silent", "--show-error", "--retry", "3",
             "--connect-timeout", "20", "--max-time", "240", "--output",
             str(temporary), BTS + filename],
            check=True,
        )
        temporary.replace(archive)

    shards = defaultdict(list)
    published_days = set()
    with ZipFile(archive) as zipped:
        name, = [member for member in zipped.namelist() if member.lower().endswith(".csv")]
        with zipped.open(name) as member:
            for row in csv.DictReader(io.TextIOWrapper(member, encoding="utf-8-sig")):
                day = row["FlightDate"]
                if not day.startswith(stem + "-"):
                    raise ValueError(f"Unexpected flight date {day} in {filename}")
                published_days.add(day)
                if row["Cancelled"] not in ("0", "0.00") or row["Diverted"] not in ("0", "0.00"):
                    continue
                carrier = row["Reporting_Airline"]
                number = int(row["Flight_Number_Reporting_Airline"])
                shards[day, number % BUCKETS].append(
                    [carrier, number, *(row[field] for field in FIELDS)]
                )

    expected_days = {
        f"{stem}-{day:02d}" for day in range(1, calendar.monthrange(year, month)[1] + 1)
    }
    if published_days != expected_days or not shards:
        raise ValueError(f"Missing flight records in {filename}")
    for day in sorted(expected_days):
        directory = output / "v1" / day
        directory.mkdir(parents=True)
        for bucket in range(BUCKETS):
            data = json.dumps(shards[day, bucket], separators=(",", ":")).encode()
            (directory / f"{bucket}.json.gz").write_bytes(gzip.compress(data, compresslevel=6, mtime=0))
    print(f"Indexed {stem}: {sum(map(len, shards.values())):,} completed segments", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=False)
    months = published_months()
    with ProcessPoolExecutor(max_workers=args.workers) as workers:
        list(workers.map(build_month, [(month, args.cache, args.output) for month in months]))
    first_year, first_month = months[0]
    last_year, last_month = months[-1]
    (args.output / "coverage.json").write_text(json.dumps({
        "first": f"{first_year}-{first_month:02d}-01",
        "last": f"{last_year}-{last_month:02d}-{calendar.monthrange(last_year, last_month)[1]}",
        "source": BTS,
    }) + "\n")
    shutil.copyfile(Path(__file__).with_name("index.html"), args.output / "index.html")


if __name__ == "__main__":
    main()
