# Soary U.S. flight archive index

This repository publishes an index of the latest 24 available months of the
[U.S. Bureau of Transportation Statistics reporting carrier files](https://transtats.bts.gov/PREZIP/).
Each file contains public, completed, non-diverted U.S. domestic segments.

Request `v1/YYYY-MM-DD/BUCKET.json.gz`, where BUCKET is the numeric part of the
flight number modulo 16. This is a gzip-compressed JSON array of rows. Each row
contains the reporting carrier, numeric flight number, origin, destination,
scheduled local departure, actual local departure and arrival, departure delay
in minutes, and actual elapsed minutes. Filter by carrier and number. A published
day always includes all 16 files. See `coverage.json` for the published date range.

GitHub Actions rebuilds the index monthly from the official BTS publication.
To build locally, run `python3 build_index.py --cache /path/to/temp-input --output /path/to/new-output`.
