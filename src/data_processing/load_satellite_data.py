"""
Sentinel-2 Level-2A downloader for the Manganese_AI_Project.

Source: Copernicus Data Space Ecosystem (CDSE) — https://dataspace.copernicus.eu/

What this script does, end to end:
  1. Takes an AOI (area of interest), a date range, and a max cloud
     percentage from the user (CLI args).
  2. Searches CDSE's public product catalogue for the best-matching
     Sentinel-2 L2A scene.
  3. Authenticates with CDSE via OAuth2 (Resource Owner Password
     Credentials grant, using the public "cdse-public" client) and
     downloads the requested bands (B02, B03, B04, B08, B11, B12) plus
     the SCL (Scene Classification Layer) and MTD_MSIL2A.xml, by
     browsing the product's internal file tree (the OData "Nodes" API),
     instead of the full ~1GB product zip.
  4. Saves everything as a normal Sentinel-2 SAFE product (matching what
     preprocess_satellite.py expects) plus a metadata.json, under
     <out-root>/<safe_name>.SAFE/ (default out-root:
     data/raw/satellite_images/; pass --out-root for a separate AOI,
     e.g. data/raw/chennai, without touching the default location's
     existing data):
       <out-root>/<safe_name>.SAFE/
         MTD_MSIL2A.xml
         GRANULE/<granule_id>/IMG_DATA/R10m/*_{B02,B03,B04,B08}_10m.jp2
         GRANULE/<granule_id>/IMG_DATA/R20m/*_{B11,B12,SCL}_20m.jp2
         metadata.json

This performs real downloads against the live CDSE API — no dummy or
mocked data is generated. It requires a real CDSE account.

Prerequisites:
  pip install -r requirements.txt   (installs requests, python-dotenv)
  Free CDSE account: https://dataspace.copernicus.eu/

Authentication:
  - Catalogue search (step 2) is public metadata — no auth required.
  - Band downloads (step 3) use an OAuth2 access token obtained via the
    password grant against the public "cdse-public" client — this is
    the CDSE identity/zipper flow, distinct from Sentinel Hub OAuth
    clients (client_id starting "sh-..."), whose client_credentials
    tokens carry no CDSE zipper audience and are rejected with
    DAT-ZIP-609 "Token audience not allowed". Credentials are your
    actual CDSE account login, loaded from a local .env file (never
    committed — see .gitignore) via python-dotenv:
      CDSE_USERNAME
      CDSE_PASSWORD
  Neither OAuth client credentials (CDSE_CLIENT_ID / CDSE_CLIENT_SECRET)
  nor S3 keys (CDSE_S3_ACCESS_KEY / CDSE_S3_SECRET_KEY) are used
  anywhere in this script.

.env file (create this yourself, do not commit it):
  CDSE_USERNAME=your-cdse-account-email
  CDSE_PASSWORD=your-cdse-account-password

Usage examples:
  # Named manganese-belt preset (Odisha)
  python src/data_processing/load_satellite_data.py \\
      --aoi keonjhar --start 2025-11-01 --end 2025-12-31 --max-cloud 20

  # Named preset (Madhya Pradesh)
  python src/data_processing/load_satellite_data.py \\
      --aoi balaghat --start 2025-11-01 --end 2025-12-31 --max-cloud 20

  # Any custom AOI, given as a bounding box:
  #   lon_min,lat_min,lon_max,lat_max  (WGS84 degrees)
  python src/data_processing/load_satellite_data.py \\
      --bbox 85.45,21.75,85.75,22.05 \\
      --start 2025-11-01 --end 2025-12-31 --max-cloud 20

  # Separate AOI written to its own directory, leaving the default
  # data/raw/satellite_images/ (T45QUE) untouched:
  python src/data_processing/load_satellite_data.py \\
      --aoi chennai --start 2025-11-01 --end 2025-12-31 --max-cloud 20 \\
      --out-root data/raw/chennai

Fallback data source:
  CDSE's catalogue/search endpoint is the primary source and is tried
  first, unchanged. If that specific request fails (HTTP error or
  connection failure -- e.g. CDSE's WAF returning 403), this script
  automatically falls back to AWS's public "Earth Search" STAC API
  (Element84, https://earth-search.aws.element84.com/), which serves the
  same real Sentinel-2 L2A products as public, anonymously-readable
  Cloud-Optimized GeoTIFFs on the "sentinel-cogs" S3 bucket -- no AWS
  account or credentials required. Only the catalogue/search step has a
  fallback; CDSE band downloads are not attempted at all once the
  catalogue step has failed over, so no CDSE credentials are touched by
  the fallback path.
"""

import argparse
import base64
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests
from dotenv import load_dotenv

# --- CDSE endpoints -------------------------------------------------------
# OData catalogue: search for products by collection, footprint, date, cloud%.
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
# Keycloak token endpoint used for OAuth2 authentication (password and
# refresh_token grants, against the public "cdse-public" client).
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
    "protocol/openid-connect/token"
)
# Zipper service: hosts both full-product download and the Nodes API used
# to browse a product's internal file tree and fetch individual files.
ZIPPER_PRODUCTS_URL = "https://zipper.dataspace.copernicus.eu/odata/v1/Products"

# The public client used for the CDSE identity/zipper flow. This is NOT
# a Sentinel Hub OAuth client (those have client_id like "sh-..." and
# issue tokens with no CDSE zipper audience — the cause of DAT-ZIP-609
# "Token audience not allowed"). This is a fixed, publicly-documented
# client id, not a secret.
CDSE_PUBLIC_CLIENT_ID = "cdse-public"

# Refresh the access token this many seconds before it actually expires,
# so a request never starts with a token that dies mid-flight.
TOKEN_REFRESH_MARGIN_SECONDS = 60

# Some networks/proxies reset connections on requests with no User-Agent
# (seen as ConnectionResetError WinError 10054 on Windows), even though
# the same request succeeds from PowerShell's Invoke-WebRequest, which
# always sends one. Identify this script explicitly to avoid that.
USER_AGENT = "Manganese_AI_Project-SatelliteDownloader/1.0"

# --- Fallback data source (used only if CDSE catalogue/search fails) ------
# Element84's Earth Search STAC API over the AWS "sentinel-cogs" bucket:
# the same real Sentinel-2 L2A scenes as CDSE, served as public,
# anonymously-readable COGs (https://registry.opendata.aws/sentinel-2-l2a-cogs/).
# No account, API key, or AWS credentials of any kind are required.
EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1/search"
EARTH_SEARCH_COLLECTION = "sentinel-2-l2a"

# Sentinel-2 L2A boa_quantification_value is a fixed mission-wide constant
# (reflectance = (DN + BOA_ADD_OFFSET) / BOA_QUANTIFICATION_VALUE); Earth
# Search's own per-band raster:bands metadata for every item in this
# collection reports scale=0.0001, offset=-0.1, i.e. reflectance =
# DN*0.0001 - 0.1 = (DN - 1000) / 10000 -- algebraically the same formula
# with BOA_QUANTIFICATION_VALUE=10000, BOA_ADD_OFFSET=-1000. Confirmed
# against a real Chennai-AOI item's actual STAC metadata, not assumed.
EARTH_SEARCH_QUANTIFICATION_VALUE = 10000.0
EARTH_SEARCH_BOA_ADD_OFFSET = -1000.0
# NODATA=0 is confirmed per-band from the same items' real raster:bands
# metadata ("nodata": 0). SATURATED=65535 is not present in that metadata;
# it is a fixed, publicly-documented Sentinel-2 L2A PSD constant (not a
# per-scene guess), included so saturated pixels are still masked.
EARTH_SEARCH_SPECIAL_VALUES = {"NODATA": 0, "SATURATED": 65535}

# Earth Search's STAC asset keys for the exact bands this project needs,
# in the order (10m group first, then 20m group) that mirrors BANDS_10M /
# BANDS_20M + SCL_BAND above.
EARTH_SEARCH_ASSET_BY_BAND = {
    "B02": "blue", "B03": "green", "B04": "red", "B08": "nir",
    "B11": "swir16", "B12": "swir22", "SCL": "scl",
}

# --- Bands required by the project's spectral analysis --------------------
# 10m native resolution: Blue, Green, Red, NIR
BANDS_10M = ["B02", "B03", "B04", "B08"]
# 20m native resolution: SWIR 1 and SWIR 2 (useful for Mn/Fe oxide contrast)
BANDS_20M = ["B11", "B12"]
# Scene Classification Layer, 20m native resolution -- required by
# preprocess_satellite.py to build the valid/cloud mask (find_scl_file
# looks under IMG_DATA/R20m first). Fetched alongside B11/B12 from the
# same IMG_DATA/R20m folder listing.
SCL_BAND = "SCL"

# Where downloaded scenes are written, per project folder structure.
# Overridable via --out-root (e.g. data/raw/chennai) so a different AOI can
# be downloaded without touching the T45QUE data under the default path.
DATA_ROOT = Path("data/raw/satellite_images")

# Convenience presets for known manganese belts, so the user can pass a
# short name instead of typing coordinates. Custom AOIs are still
# supported via --bbox for any other location.
# bbox format: (lon_min, lat_min, lon_max, lat_max) in WGS84 degrees.
AOI_PRESETS = {
    "keonjhar": (85.45, 21.75, 85.75, 22.05),  # Odisha manganese belt
    "balaghat": (80.05, 21.65, 80.45, 21.95),  # Madhya Pradesh manganese belt
    "chennai": (79.95, 12.85, 80.45, 13.25),  # Chennai-metro-scale AOI
}


def resolve_aoi(args):
    """Turn the user's --aoi or --bbox input into a (lon_min, lat_min,
    lon_max, lat_max) tuple. Exactly one of the two must be given."""
    if args.aoi and args.bbox:
        sys.exit("Pass either --aoi or --bbox, not both.")
    if args.aoi:
        return AOI_PRESETS[args.aoi]
    if args.bbox:
        try:
            parts = [float(x) for x in args.bbox.split(",")]
        except ValueError:
            sys.exit("--bbox must be four comma-separated numbers: "
                      "lon_min,lat_min,lon_max,lat_max")
        if len(parts) != 4:
            sys.exit("--bbox must have exactly 4 values: "
                      "lon_min,lat_min,lon_max,lat_max")
        lon_min, lat_min, lon_max, lat_max = parts
        if lon_min >= lon_max or lat_min >= lat_max:
            sys.exit("--bbox values must satisfy lon_min < lon_max and "
                      "lat_min < lat_max")
        return tuple(parts)
    sys.exit("You must supply an AOI: --aoi <preset> or --bbox "
              "lon_min,lat_min,lon_max,lat_max")


def find_scene(bbox, start_date, end_date, max_cloud):
    """Query the CDSE OData catalogue for Sentinel-2 L2A scenes that:
      - intersect the AOI bounding box
      - fall within [start_date, end_date)
      - have cloud cover <= max_cloud percent
    Returns the newest matching product's metadata dict (includes the
    product Id GUID needed for the Nodes API, and Name/S3Path fields).
    No authentication is required for catalogue search."""
    lon_min, lat_min, lon_max, lat_max = bbox

    # OData wants the AOI as a WKT polygon (closed ring, 5 points).
    footprint = (
        "geography'SRID=4326;POLYGON(("
        f"{lon_min} {lat_min},{lon_max} {lat_min},"
        f"{lon_max} {lat_max},{lon_min} {lat_max},"
        f"{lon_min} {lat_min}))'"
    )

    # Build the OData $filter: collection = SENTINEL-2, product type =
    # L2A, spatial intersection, date window, and cloud-cover ceiling.
    filt = (
        "Collection/Name eq 'SENTINEL-2' and "
        "Attributes/OData.CSC.StringAttribute/any(a:a/Name eq 'productType' and "
        "a/OData.CSC.StringAttribute/Value eq 'S2MSI2A') and "
        f"OData.CSC.Intersects(area={footprint}) and "
        f"ContentDate/Start gt {start_date}T00:00:00.000Z and "
        f"ContentDate/Start lt {end_date}T00:00:00.000Z and "
        "Attributes/OData.CSC.DoubleAttribute/any(a:a/Name eq 'cloudCover' and "
        f"a/OData.CSC.DoubleAttribute/Value le {max_cloud})"
    )

    # $orderby newest first, $top a handful of candidates so we can pick
    # the best one without pulling back the whole result set.
    #
    # A plain requests.get() here can fail with ConnectionResetError
    # (WinError 10054) even though the same request succeeds via
    # PowerShell's Invoke-WebRequest — that client always sends a
    # User-Agent header and a request without one is what some
    # proxies/firewalls reset. We add a User-Agent, a longer timeout,
    # and retry a few times to ride out transient connection resets.
    max_attempts = 3
    last_error = None
    response = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(
                CATALOGUE_URL,
                params={"$filter": filt, "$orderby": "ContentDate/Start desc", "$top": 5},
                headers={"User-Agent": USER_AGENT},
                timeout=120,
            )
            break  # got a response, stop retrying
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last_error = exc
            print(f"Catalogue request failed (attempt {attempt}/{max_attempts}): {exc}")
            if attempt < max_attempts:
                time.sleep(2 * attempt)  # brief backoff before retrying

    if response is None:
        raise RuntimeError(
            f"Could not reach the CDSE catalogue after {max_attempts} attempts."
        ) from last_error

    response.raise_for_status()  # surfaces real HTTP/API errors immediately

    results = response.json().get("value", [])
    if not results:
        raise RuntimeError(
            "No scenes matched that AOI/date range/cloud threshold. "
            "Try widening --start/--end or raising --max-cloud."
        )
    return results[0]  # newest scene under the cloud-cover ceiling


# ============================================================
# FALLBACK: AWS EARTH SEARCH (used only if CDSE catalogue/search fails)
# ============================================================

def find_scene_fallback(bbox, start_date, end_date, max_cloud):
    """Query Element84's public Earth Search STAC API (no auth) for real
    Sentinel-2 L2A scenes over `bbox`/[start_date, end_date]. Returns the
    lowest-cloud STAC item found; if none are under `max_cloud`, still
    returns the lowest-cloud one available and logs that the ceiling
    couldn't be met (never fabricates a scene -- if literally nothing
    covers the AOI/dates, this raises)."""
    lon_min, lat_min, lon_max, lat_max = bbox
    print(f"[FALLBACK] Searching Earth Search (AWS/Element84) for Sentinel-2 L2A "
          f"over bbox={bbox}, {start_date} to {end_date}...")

    response = requests.post(
        EARTH_SEARCH_URL,
        json={
            "collections": [EARTH_SEARCH_COLLECTION],
            "bbox": [lon_min, lat_min, lon_max, lat_max],
            "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
            "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
            "limit": 50,
        },
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    response.raise_for_status()

    features = response.json().get("features", [])
    if not features:
        raise RuntimeError(
            "[FALLBACK] No real Sentinel-2 L2A scenes found on Earth Search for "
            "that AOI/date range either. Try widening --start/--end. "
            "Refusing to fabricate a result."
        )

    best = features[0]  # already sorted by cloud_cover ascending
    cloud = best["properties"].get("eo:cloud_cover")
    print(f"[FALLBACK] alternative source used: AWS Earth Search (Element84, "
          f"sentinel-cogs)")
    print(f"[FALLBACK] product/scene ID       : {best['id']}")
    print(f"[FALLBACK] acquisition date        : {best['properties'].get('datetime')}")
    print(f"[FALLBACK] cloud cover percentage  : {cloud}")
    if cloud is not None and cloud > max_cloud:
        print(f"[FALLBACK] NOTE: no scene under --max-cloud={max_cloud}% was found "
              f"for this AOI/date range; using the lowest-cloud real scene "
              f"available ({cloud}%) instead of fabricating a cleaner one.")
    return best


def _normalize_band_code(band):
    """'B02' -> 'B2', 'B11' -> 'B11' (matches the physicalBand attribute
    values preprocess_satellite.py's parse_reflectance_metadata() expects;
    mirrors that module's identically-named helper, duplicated here since
    this is a standalone script)."""
    match = re.match(r"^B0?(\d+)$", band)
    if not match:
        raise ValueError(f"Unrecognized band code: {band}")
    return f"B{int(match.group(1))}"


def _build_mtd_msil2a_xml(mtd_path, bands, baseline):
    """Write a minimal MTD_MSIL2A.xml that preprocess_satellite.py's
    parse_reflectance_metadata() can read as-is. Every value written is
    real, sourced from the actual STAC item / the mission-wide L2A
    reflectance-scaling convention (see EARTH_SEARCH_* constants above) --
    nothing here is a per-scene fabrication:
      - BOA_QUANTIFICATION_VALUE / BOA_ADD_OFFSET: derived from this
        collection's own real raster:bands scale/offset metadata.
      - PROCESSING_BASELINE: the real value from the STAC item's own
        properties.
      - NODATA: confirmed from the same real raster:bands metadata.
      - SATURATED: the fixed, publicly-documented Sentinel-2 L2A PSD
        constant (not scene-specific).
    """
    root = ET.Element("Level-2A_User_Product")
    gp = ET.SubElement(root, "General_Info")
    qv = ET.SubElement(gp, "BOA_QUANTIFICATION_VALUE")
    qv.text = str(EARTH_SEARCH_QUANTIFICATION_VALUE)
    if baseline is not None:
        pb = ET.SubElement(gp, "PROCESSING_BASELINE")
        pb.text = str(baseline)

    spectral_list = ET.SubElement(gp, "Spectral_Information_List")
    offset_list = ET.SubElement(gp, "BOA_ADD_OFFSET_VALUES_LIST")
    for band in bands:
        physical_band = _normalize_band_code(band)
        ET.SubElement(
            spectral_list, "Spectral_Information",
            {"bandId": band, "physicalBand": physical_band},
        )
        offset_elem = ET.SubElement(offset_list, "BOA_ADD_OFFSET", {"band_id": band})
        offset_elem.text = str(EARTH_SEARCH_BOA_ADD_OFFSET)

    for name, index in EARTH_SEARCH_SPECIAL_VALUES.items():
        sv = ET.SubElement(gp, "Special_Values")
        ET.SubElement(sv, "SPECIAL_VALUE_TEXT").text = name
        ET.SubElement(sv, "SPECIAL_VALUE_INDEX").text = str(index)

    ET.ElementTree(root).write(mtd_path, encoding="utf-8", xml_declaration=True)


def download_scene_fallback(item, out_root):
    """Download the required real bands + SCL for one Earth Search STAC
    item, laid out exactly like a normal Sentinel-2 SAFE product (same
    shape download_scene() writes for CDSE), so preprocess_satellite.py
    can consume it unmodified. Every band file is the real, unmodified
    pixel data streamed directly from the public sentinel-cogs bucket --
    only the on-disk filenames/extensions are adapted to match the
    existing pipeline's naming convention (preprocess_satellite.py's
    find_band_file/find_scl_file match by filename pattern, not by
    inspecting file headers; rasterio itself opens by content, not
    extension, so a real GeoTIFF saved with a .jp2 suffix still opens
    correctly)."""
    props = item["properties"]
    scene_id = item["id"]
    tile = (props.get("grid:code") or "").removeprefix("MGRS-") or "UNKNOWN"
    dt = props.get("datetime", "")
    date_compact = dt.replace("-", "").replace(":", "").split(".")[0]  # e.g. 20260802T051513
    baseline = props.get("s2:processing_baseline")

    safe_name = f"{scene_id}.SAFE"  # real STAC item id -- not a fabricated ESA-style ID
    scene_dir = out_root / safe_name
    granule_name = f"L2A_T{tile}_{scene_id}"
    granule_dir = scene_dir / "GRANULE" / granule_name
    scene_dir.mkdir(parents=True, exist_ok=True)

    bands_by_resolution = [(BANDS_10M, "10"), (BANDS_20M + [SCL_BAND], "20")]
    downloaded_bands = {}
    for bands, resolution_m in bands_by_resolution:
        res_dir = granule_dir / "IMG_DATA" / f"R{resolution_m}m"
        res_dir.mkdir(parents=True, exist_ok=True)
        for band in bands:
            asset_key = EARTH_SEARCH_ASSET_BY_BAND[band]
            asset = item["assets"].get(asset_key)
            if asset is None:
                raise RuntimeError(
                    f"[FALLBACK] Expected asset '{asset_key}' (band {band}) not "
                    f"present on STAC item {scene_id}."
                )
            href = asset["href"]
            filename = f"T{tile}_{date_compact}_{band}_{resolution_m}m.jp2"
            local_path = res_dir / filename
            print(f"[FALLBACK] Downloading {band} ({resolution_m}m) <- {href}")
            response = requests.get(href, headers={"User-Agent": USER_AGENT}, stream=True, timeout=300)
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
            size_mb = local_path.stat().st_size / (1024 * 1024)
            print(f"[FALLBACK] Saved -> {local_path} ({size_mb:.1f} MB)")
            downloaded_bands[band] = str(local_path.relative_to(out_root))

    mtd_path = scene_dir / "MTD_MSIL2A.xml"
    _build_mtd_msil2a_xml(mtd_path, BANDS_10M + BANDS_20M, baseline)
    print(f"[FALLBACK] Wrote reflectance-scaling metadata -> {mtd_path}")

    # Best-effort: also fetch the item's real tile-level metadata XML
    # (granule_metadata asset) for provenance. Not required by
    # preprocess_satellite.py, so a failure here is non-fatal.
    granule_meta_asset = item["assets"].get("granule_metadata")
    if granule_meta_asset is not None:
        try:
            r = requests.get(granule_meta_asset["href"], headers={"User-Agent": USER_AGENT}, timeout=60)
            r.raise_for_status()
            (granule_dir / "MTD_TL.xml").write_bytes(r.content)
            print(f"[FALLBACK] Saved real tile metadata -> {granule_dir / 'MTD_TL.xml'}")
        except requests.RequestException as exc:
            print(f"[FALLBACK] (non-fatal) could not fetch granule metadata: {exc}")

    metadata = {
        "source": "AWS Earth Search (Element84) / sentinel-cogs",
        "source_url": EARTH_SEARCH_URL,
        "scene_id": scene_id,
        "product_name": safe_name,
        "sensing_start": dt,
        "cloud_cover_percent": props.get("eo:cloud_cover"),
        "processing_baseline": baseline,
        "mgrs_tile": tile,
        "bands": downloaded_bands,
    }
    (scene_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"\n[FALLBACK] Saved scene to {scene_dir}")
    return scene_dir


def decode_jwt_claims(access_token):
    """Decode (not verify) the payload segment of a JWT access token, so
    we can inspect what CDSE actually issued — in particular "aud"
    (audience) and "scope", which is what determines whether the zipper
    service will accept the token. This is local base64 decoding only,
    no network call and no signature check."""
    try:
        payload_segment = access_token.split(".")[1]
        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError, json.JSONDecodeError) as exc:
        print(f"Could not decode access token as a JWT: {exc}")
        return {}


def _log_token_diagnostics(token_json):
    """Print the issued token's claims, aud, and scope — this is what
    actually determines whether zipper.dataspace will accept the token
    (a Sentinel Hub client_credentials token, for example, decodes fine
    but carries no CDSE zipper audience, which is why it gets rejected
    with DAT-ZIP-609 "Token audience not allowed")."""
    claims = decode_jwt_claims(token_json["access_token"])
    print("Access token claims:", json.dumps(claims, indent=2))
    print("aud:", claims.get("aud"))
    print("scope:", claims.get("scope", token_json.get("scope")))


def _token_state_from_response(token_json):
    """Turn a Keycloak token response into the token_state dict threaded
    through the rest of the script, recording a wall-clock expiry time
    so callers can tell when a refresh is needed."""
    return {
        "access_token": token_json["access_token"],
        "refresh_token": token_json["refresh_token"],
        "expires_at": time.time() + token_json.get("expires_in", 600),
    }


def get_access_token():
    """Authenticate with CDSE using the Resource Owner Password
    Credentials grant against the public "cdse-public" client — the
    official CDSE identity/zipper flow:
      POST https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token
      client_id=cdse-public, grant_type=password,
      username=<CDSE_USERNAME>, password=<CDSE_PASSWORD>

    This is your actual CDSE account login, not a Sentinel Hub OAuth
    client (client_id "sh-...") — those issue client_credentials tokens
    with no CDSE zipper audience, which zipper rejects with DAT-ZIP-609
    "Token audience not allowed".

    Returns a token_state dict (access_token, refresh_token, expires_at).
    Credentials are loaded from a local .env file via python-dotenv, so
    they never need to be hardcoded or committed to the repo."""
    load_dotenv()  # populates os.environ from a .env file in the project root

    username = os.environ.get("CDSE_USERNAME")
    password = os.environ.get("CDSE_PASSWORD")
    if not username or not password:
        sys.exit(
            "Missing CDSE_USERNAME / CDSE_PASSWORD. Put your CDSE account "
            "email and password (not a Sentinel Hub OAuth client) in a "
            ".env file (see the module docstring for the format)."
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": CDSE_PUBLIC_CLIENT_ID,
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
    )
    response.raise_for_status()  # surfaces bad credentials / auth failures immediately
    token_json = response.json()
    _log_token_diagnostics(token_json)
    return _token_state_from_response(token_json)


def refresh_access_token(token_state):
    """Exchange the current refresh_token for a new access token, using
    the refresh_token grant against the same public client. Updates
    token_state in place and returns it."""
    print("Access token expiring soon, refreshing...")
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": CDSE_PUBLIC_CLIENT_ID,
            "grant_type": "refresh_token",
            "refresh_token": token_state["refresh_token"],
        },
        timeout=30,
    )
    response.raise_for_status()
    token_json = response.json()
    _log_token_diagnostics(token_json)
    token_state.update(_token_state_from_response(token_json))
    return token_state


def get_valid_access_token(token_state):
    """Return a bearer access token guaranteed not to be on the verge of
    expiry, refreshing it first if needed. CDSE access tokens are
    short-lived (~10 minutes), so any call that hits the API should go
    through this rather than reading token_state["access_token"] directly."""
    if time.time() >= token_state["expires_at"] - TOKEN_REFRESH_MARGIN_SECONDS:
        refresh_access_token(token_state)
    return token_state["access_token"]


def zipper_auth_headers(token_state):
    """Build the Authorization header used for every zipper.dataspace
    request. Centralized so the exact header format only needs fixing
    in one place, and so it always uses a freshly-validated token."""
    token = get_valid_access_token(token_state).strip()
    return {"Authorization": f"Bearer {token}"}


def node_url(product_id, path_segments):
    """Build an OData Nodes URL by chaining Nodes(name) segments, e.g.
    path_segments=['X.SAFE', 'GRANULE'] ->
    .../Products(<id>)/Nodes(X.SAFE)/Nodes(GRANULE)
    This lets us browse a product's internal SAFE folder structure
    without downloading the whole product."""
    url = f"{ZIPPER_PRODUCTS_URL}({product_id})"
    for segment in path_segments:
        url += f"/Nodes({segment})"
    return url


def list_child_nodes(url, token_state):
    """List the immediate children (files/folders) of a Nodes path."""
    response = requests.get(url, headers=zipper_auth_headers(token_state), timeout=60)
    print("DEBUG URL:", url)
    print("DEBUG STATUS:", response.status_code)
    print("DEBUG RESPONSE:", response.text[:500])
    response.raise_for_status()
    return response.json().get("result", [])


def download_node_file(url, token_state, local_path):
    """Stream-download a single file from a Nodes path's /$value endpoint,
    authenticated with the OAuth2 bearer token."""
    response = requests.get(
        f"{url}/$value",
        headers=zipper_auth_headers(token_state),
        stream=True,
        timeout=300,
    )
    response.raise_for_status()
    with open(local_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            f.write(chunk)


def locate_band_files(product_id, safe_name, bands, resolution_m, token_state):
    """Discover the granule folder and the exact band filenames for the
    requested resolution by browsing the Nodes tree, since the granule
    id is scene-specific and can't be guessed from the product name.

    Sentinel-2 L2A products are laid out as:
      <product>.SAFE/GRANULE/<granule_id>/IMG_DATA/R<res>m/*_<band>_<res>m.jp2
    """
    granule_list_url = node_url(product_id, [safe_name, "GRANULE"])
    granules = list_child_nodes(granule_list_url, token_state)
    if not granules:
        raise RuntimeError(f"No GRANULE folder found for product {safe_name}")
    granule_name = granules[0]["Name"]  # one granule per tile-scene

    img_dir_url = node_url(
        product_id, [safe_name, "GRANULE", granule_name, "IMG_DATA", f"R{resolution_m}m"]
    )
    files = list_child_nodes(img_dir_url, token_state)

    band_to_filename = {}
    for band in bands:
        matches = [
            f["Name"] for f in files if f"_{band}_{resolution_m}m.jp2" in f["Name"]
        ]
        if not matches:
            raise RuntimeError(f"Band {band} not found under {img_dir_url}")
        band_to_filename[band] = matches[0]
    return granule_name, band_to_filename


def download_scene(product, out_root, token_state):
    """Download the required bands + SCL for one product, laid out as a
    normal Sentinel-2 SAFE product (matching what preprocess_satellite.py
    already expects -- the same structure the existing T45QUE product on
    disk has):

      <out_root>/<safe_name>.SAFE/
        MTD_MSIL2A.xml
        GRANULE/<granule_id>/IMG_DATA/R10m/*_{B02,B03,B04,B08}_10m.jp2
        GRANULE/<granule_id>/IMG_DATA/R20m/*_{B11,B12,SCL}_20m.jp2
        metadata.json   (extra bookkeeping; ignored by preprocess_satellite.py)
    """
    safe_name = product["Name"]
    product_id = product["Id"]
    scene_dir = out_root / safe_name  # real SAFE root, e.g. "...T44....SAFE"
    scene_dir.mkdir(parents=True, exist_ok=True)  # create real output folder

    downloaded_bands = {}
    granule_name = None
    # 10m bands, and 20m bands + SCL (same IMG_DATA/R20m folder), live in
    # separate resolution folders, so resolve and download each group
    # separately, writing into the real GRANULE/.../IMG_DATA/R<res>m path.
    for bands, resolution_m in [(BANDS_10M, "10"), (BANDS_20M + [SCL_BAND], "20")]:
        granule_name, band_to_filename = locate_band_files(
            product_id, safe_name, bands, resolution_m, token_state
        )
        res_dir = scene_dir / "GRANULE" / granule_name / "IMG_DATA" / f"R{resolution_m}m"
        res_dir.mkdir(parents=True, exist_ok=True)
        for band, filename in band_to_filename.items():
            local_path = res_dir / filename
            print(f"Downloading {band} ({resolution_m}m) -> {local_path}")
            file_url = node_url(
                product_id,
                [safe_name, "GRANULE", granule_name, "IMG_DATA", f"R{resolution_m}m", filename],
            )
            download_node_file(file_url, token_state, local_path)  # real network download
            downloaded_bands[band] = filename

    # MTD_MSIL2A.xml at the SAFE root -- the real product metadata file
    # preprocess_satellite.py parses for BOA_QUANTIFICATION_VALUE /
    # BOA_ADD_OFFSET (reflectance scaling) and is also what its
    # find_safe_product() searches for (rglob) to locate this SAFE root.
    mtd_path = scene_dir / "MTD_MSIL2A.xml"
    print(f"Downloading MTD_MSIL2A.xml -> {mtd_path}")
    mtd_url = node_url(product_id, [safe_name, "MTD_MSIL2A.xml"])
    download_node_file(mtd_url, token_state, mtd_path)  # real network download

    # Record enough metadata to trace this scene back to its source and
    # to let downstream steps (feature extraction, notebooks) find bands
    # by name without re-parsing the Nodes tree.
    metadata = {
        "scene_id": safe_name.removesuffix(".SAFE"),
        "product_id": product_id,
        "product_name": safe_name,
        "granule_name": granule_name,
        "sensing_start": product.get("ContentDate", {}).get("Start"),
        "cloud_cover_percent": next(
            (
                a["Value"]
                for a in product.get("Attributes", [])
                if a.get("Name") == "cloudCover"
            ),
            None,
        ),
        "bands": downloaded_bands,
    }
    (scene_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"\nSaved scene to {scene_dir}")
    return scene_dir


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download Sentinel-2 L2A bands from CDSE for one scene.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--aoi", choices=AOI_PRESETS.keys(),
        help="Named manganese-belt preset (alternative to --bbox).",
    )
    parser.add_argument(
        "--bbox",
        help="Custom AOI as lon_min,lat_min,lon_max,lat_max in WGS84 degrees "
             "(alternative to --aoi).",
    )
    parser.add_argument("--start", required=True, help="Start date, YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="End date, YYYY-MM-DD")
    parser.add_argument(
        "--max-cloud", type=float, default=20.0,
        help="Maximum acceptable cloud cover percentage (default: 20).",
    )
    parser.add_argument(
        "--out-root", type=Path, default=DATA_ROOT,
        help=f"Folder to write the downloaded SAFE product into, e.g. "
             f"data/raw/chennai for a separate AOI (default: {DATA_ROOT}).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    bbox = resolve_aoi(args)

    print(f"[CDSE] Searching CDSE for Sentinel-2 L2A scenes over bbox={bbox}, "
          f"{args.start} to {args.end}, cloud <= {args.max_cloud}%...")
    try:
        product = find_scene(bbox, args.start, args.end, args.max_cloud)
    except (requests.exceptions.RequestException, RuntimeError) as exc:
        # Only the catalogue/search step falls back -- CDSE band download
        # (get_access_token/download_scene) is never reached in this branch,
        # so no CDSE credentials are touched by the fallback path.
        print(f"[CDSE] catalogue/search failed: {exc}")
        print("[FALLBACK] CDSE catalogue/search is unavailable from this "
              "environment; falling back to a public alternative source "
              "for real Sentinel-2 L2A data.")
        item = find_scene_fallback(bbox, args.start, args.end, args.max_cloud)
        download_scene_fallback(item, args.out_root)
        return

    print(f"[CDSE] Found scene: {product['Name']}")
    token_state = get_access_token()  # OAuth2 token state, refreshed as needed
    download_scene(product, args.out_root, token_state)


if __name__ == "__main__":
    main()
