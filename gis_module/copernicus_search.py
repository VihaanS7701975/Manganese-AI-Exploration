from pathlib import Path
import json
import os

import requests
from dotenv import load_dotenv


# ============================================================
# S.I.H - COPERNICUS SENTINEL-2 SEARCH
# ============================================================


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_FILE = PROJECT_ROOT / ".env"

OUTPUT_FOLDER = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

OUTPUT_FILE = (
    OUTPUT_FOLDER
    / "copernicus_search_results.json"
)


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv(ENV_FILE)


CLIENT_ID = os.getenv(
    "CDSE_CLIENT_ID"
)

CLIENT_SECRET = os.getenv(
    "CDSE_CLIENT_SECRET"
)


# ============================================================
# COPERNICUS API
# ============================================================

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

CATALOG_URL = (
    "https://sh.dataspace.copernicus.eu/"
    "catalog/v1/search"
)


# ============================================================
# STUDY AREA
# JODA-BARBIL MANGANESE REGION
# ODISHA, INDIA
# ============================================================

# WGS84 bounding box:
#
# [minimum longitude,
#  minimum latitude,
#  maximum longitude,
#  maximum latitude]

AOI_BBOX = [
    85.25,
    21.75,
    85.55,
    22.05
]


# ============================================================
# SEARCH SETTINGS
# ============================================================

COLLECTION = "sentinel-2-l2a"

START_DATE = (
    "2024-01-01T00:00:00Z"
)

END_DATE = (
    "2026-08-26T23:59:59Z"
)

MAX_CLOUD_COVER = 20.0

# Number of scenes requested from Copernicus.
# We filter/sort them locally afterward.
SEARCH_LIMIT = 50

# Number of best scenes displayed.
DISPLAY_LIMIT = 10


# ============================================================
# AUTHENTICATION
# ============================================================

def get_access_token():

    print(
        "Authenticating with Copernicus Data Space..."
    )

    # --------------------------------------------------------
    # Check .env
    # --------------------------------------------------------

    if not ENV_FILE.exists():

        raise RuntimeError(
            "\n.env file was not found.\n\n"
            f"Expected:\n{ENV_FILE}\n\n"
            "Create the file with:\n"
            "CDSE_CLIENT_ID=your_client_id\n"
            "CDSE_CLIENT_SECRET=your_client_secret"
        )

    if not CLIENT_ID:

        raise RuntimeError(
            "\nCDSE_CLIENT_ID is missing.\n\n"
            "Check your .env file."
        )

    if not CLIENT_SECRET:

        raise RuntimeError(
            "\nCDSE_CLIENT_SECRET is missing.\n\n"
            "Check your .env file."
        )

    # --------------------------------------------------------
    # OAuth client credentials request
    # --------------------------------------------------------

    payload = {

        "grant_type":
            "client_credentials",

        "client_id":
            CLIENT_ID,

        "client_secret":
            CLIENT_SECRET,
    }

    try:

        response = requests.post(
            TOKEN_URL,
            data=payload,
            timeout=30
        )

    except requests.RequestException as error:

        raise RuntimeError(
            "\nCould not connect to "
            "Copernicus authentication service.\n\n"
            f"Error: {error}"
        )

    # --------------------------------------------------------
    # Authentication failure
    # --------------------------------------------------------

    if response.status_code != 200:

        raise RuntimeError(
            "\nCopernicus authentication failed.\n\n"
            f"HTTP status: {response.status_code}\n"
            f"Response: {response.text}"
        )

    # --------------------------------------------------------
    # Parse response
    # --------------------------------------------------------

    try:

        token_data = response.json()

    except ValueError:

        raise RuntimeError(
            "\nCopernicus returned an invalid "
            "authentication response."
        )

    access_token = token_data.get(
        "access_token"
    )

    if not access_token:

        raise RuntimeError(
            "\nCopernicus authentication succeeded "
            "but no access token was returned."
        )

    print(
        "✓ Copernicus authentication successful."
    )

    print()

    return access_token


# ============================================================
# SEARCH SENTINEL-2 L2A
# ============================================================

def search_sentinel2(
    access_token
):

    print("=" * 70)
    print("COPERNICUS SENTINEL-2 SEARCH")
    print("=" * 70)
    print()

    # --------------------------------------------------------
    # Request headers
    # --------------------------------------------------------

    headers = {

        "Authorization":
            f"Bearer {access_token}",

        "Content-Type":
            "application/json",
    }

    # --------------------------------------------------------
    # Catalog search
    #
    # IMPORTANT:
    # We intentionally use the simple Catalog POST format.
    # Cloud filtering is performed locally after receiving
    # the metadata.
    # --------------------------------------------------------

    payload = {

        "collections": [
            COLLECTION
        ],

        "bbox":
            AOI_BBOX,

        "datetime":
            f"{START_DATE}/{END_DATE}",

        "limit":
            SEARCH_LIMIT,
    }

    print("===== SEARCH PARAMETERS =====")

    print(
        f"Collection: {COLLECTION}"
    )

    print(
        f"Longitude: "
        f"{AOI_BBOX[0]} → {AOI_BBOX[2]}"
    )

    print(
        f"Latitude:  "
        f"{AOI_BBOX[1]} → {AOI_BBOX[3]}"
    )

    print(
        f"Date range:"
    )

    print(
        f"  {START_DATE}"
    )

    print(
        f"  {END_DATE}"
    )

    print()

    print(
        "Requesting candidate scenes..."
    )

    # --------------------------------------------------------
    # Send request
    # --------------------------------------------------------

    try:

        response = requests.post(
            CATALOG_URL,
            headers=headers,
            json=payload,
            timeout=60
        )

    except requests.RequestException as error:

        raise RuntimeError(
            "\nCould not connect to "
            "Copernicus Catalog API.\n\n"
            f"Error: {error}"
        )

    # --------------------------------------------------------
    # API error
    # --------------------------------------------------------

    if response.status_code != 200:

        raise RuntimeError(
            "\nCopernicus catalog search failed.\n\n"
            f"HTTP status: {response.status_code}\n"
            f"Response: {response.text}"
        )

    # --------------------------------------------------------
    # Parse response
    # --------------------------------------------------------

    try:

        data = response.json()

    except ValueError:

        raise RuntimeError(
            "\nCopernicus returned an invalid "
            "Catalog response."
        )

    features = data.get(
        "features",
        []
    )

    print()

    print(
        f"Raw scenes returned: "
        f"{len(features)}"
    )

    print()

    if not features:

        print(
            "No Sentinel-2 scenes were found "
            "for this AOI and date range."
        )

        return []

    # ========================================================
    # LOCAL CLOUD FILTER
    # ========================================================

    filtered_results = []

    for feature in features:

        properties = feature.get(
            "properties",
            {}
        )

        # ----------------------------------------------------
        # Cloud coverage
        # ----------------------------------------------------

        cloud_cover = properties.get(
            "eo:cloud_cover"
        )

        # Some catalog responses may expose the value
        # under a different property.
        if cloud_cover is None:

            cloud_cover = properties.get(
                "cloudCover"
            )

        # ----------------------------------------------------
        # Ignore scenes with no cloud information.
        # ----------------------------------------------------

        if cloud_cover is None:

            continue

        try:

            cloud_cover = float(
                cloud_cover
            )

        except (
            TypeError,
            ValueError
        ):

            continue

        # ----------------------------------------------------
        # Apply cloud threshold
        # ----------------------------------------------------

        if cloud_cover > MAX_CLOUD_COVER:

            continue

        # ----------------------------------------------------
        # Scene metadata
        # ----------------------------------------------------

        scene_id = feature.get(
            "id",
            "Unknown"
        )

        datetime_value = properties.get(
            "datetime"
        )

        if datetime_value is None:

            datetime_value = properties.get(
                "start_datetime",
                "Unknown"
            )

        filtered_results.append(
            {

                "scene_id":
                    scene_id,

                "datetime":
                    datetime_value,

                "cloud_cover":
                    cloud_cover,

                "geometry":
                    feature.get(
                        "geometry"
                    ),

                "bbox":
                    feature.get(
                        "bbox"
                    ),

                "properties":
                    properties,

                "assets":
                    feature.get(
                        "assets"
                    ),
            }
        )

    # ========================================================
    # SORT BY CLOUD COVER
    # ========================================================

    filtered_results.sort(
        key=lambda item:
            item["cloud_cover"]
    )

    print(
        f"Scenes below "
        f"{MAX_CLOUD_COVER:.1f}% cloud cover: "
        f"{len(filtered_results)}"
    )

    print()

    # ========================================================
    # DISPLAY BEST RESULTS
    # ========================================================

    if not filtered_results:

        print(
            "No scenes passed the cloud-cover filter."
        )

        print()

        print(
            "Try increasing MAX_CLOUD_COVER "
            "if necessary."
        )

        return []

    print(
        "===== BEST SENTINEL-2 SCENES ====="
    )

    display_results = (
        filtered_results[
            :DISPLAY_LIMIT
        ]
    )

    for index, scene in enumerate(
        display_results,
        start=1
    ):

        print(
            f"{index}. {scene['scene_id']}"
        )

        print(
            f"   Date: "
            f"{scene['datetime']}"
        )

        print(
            f"   Cloud cover: "
            f"{scene['cloud_cover']:.2f}%"
        )

        print()

    return filtered_results


# ============================================================
# SAVE RESULTS
# ============================================================

def save_results(
    results
):

    OUTPUT_FOLDER.mkdir(
        parents=True,
        exist_ok=True
    )

    output_data = {

        "project":
            "S.I.H Manganese Exploration",

        "study_area": {

            "name":
                "Joda-Barbil, Odisha",

            "bbox":
                AOI_BBOX,
        },

        "search": {

            "collection":
                COLLECTION,

            "start_date":
                START_DATE,

            "end_date":
                END_DATE,

            "max_cloud_cover":
                MAX_CLOUD_COVER,
        },

        "results":
            results,
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output_data,
            file,
            indent=2,
            default=str
        )

    print(
        "✓ Search results saved:"
    )

    print(
        OUTPUT_FILE
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 70)

    print(
        "S.I.H - COPERNICUS DATA SPACE"
    )

    print(
        "MANGANESE EXPLORATION DATA SEARCH"
    )

    print("=" * 70)

    print()

    # --------------------------------------------------------
    # Step 1 - Authentication
    # --------------------------------------------------------

    access_token = (
        get_access_token()
    )

    # --------------------------------------------------------
    # Step 2 - Search
    # --------------------------------------------------------

    results = (
        search_sentinel2(
            access_token
        )
    )

    # --------------------------------------------------------
    # Step 3 - Save
    # --------------------------------------------------------

    if results:

        save_results(
            results
        )

    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

    print("=" * 70)

    print(
        "COPERNICUS SEARCH COMPLETE"
    )

    print("=" * 70)

    print()


# ============================================================
# PROGRAM ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()