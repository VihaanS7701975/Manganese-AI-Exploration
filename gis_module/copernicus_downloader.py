from pathlib import Path
import json
import os
from urllib.parse import quote

import requests
from dotenv import load_dotenv


# ============================================================
# S.I.H - COPERNICUS SENTINEL-2 BAND DOWNLOADER
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

ENV_FILE = PROJECT_ROOT / ".env"

SEARCH_RESULTS = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "copernicus_search_results.json"
)

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "satellite_images"
)


# ============================================================
# COPERNICUS API
# ============================================================

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

CATALOG_URL = (
    "https://catalogue.dataspace.copernicus.eu/"
    "odata/v1/Products"
)

DOWNLOAD_URL = (
    "https://download.dataspace.copernicus.eu/"
    "odata/v1"
)


# ============================================================
# REQUIRED FILES
# ============================================================

REQUIRED_FILE_MARKERS = {

    "B02": "_B02_10m.jp2",

    "B03": "_B03_10m.jp2",

    "B04": "_B04_10m.jp2",

    "B08": "_B08_10m.jp2",

    "B11": "_B11_20m.jp2",

    "B12": "_B12_20m.jp2",

    "SCL": "_SCL_20m.jp2",
}


# ============================================================
# LOAD ENVIRONMENT
# ============================================================

load_dotenv(ENV_FILE)

CLIENT_ID = os.getenv(
    "CDSE_CLIENT_ID"
)

CLIENT_SECRET = os.getenv(
    "CDSE_CLIENT_SECRET"
)


# ============================================================
# GET BEST SCENE
# ============================================================

def get_best_scene():

    if not SEARCH_RESULTS.exists():

        raise FileNotFoundError(
            "\nSearch results not found:\n"
            f"{SEARCH_RESULTS}\n\n"
            "Run first:\n"
            "python gis_module/copernicus_search.py"
        )

    with open(
        SEARCH_RESULTS,
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(file)

    results = data.get(
        "results",
        []
    )

    if not results:

        raise RuntimeError(
            "No Copernicus scenes are available."
        )

    # Search results are sorted by cloud cover.
    return results[0]


# ============================================================
# AUTHENTICATION
# ============================================================

def get_access_token():

    print("Authenticating with Copernicus CDSE...")
    print()

    username = os.getenv("CDSE_USERNAME")
    password = os.getenv("CDSE_PASSWORD")

    if not username:
        raise RuntimeError(
            "CDSE_USERNAME is missing from .env"
        )

    if not password:
        raise RuntimeError(
            "CDSE_PASSWORD is missing from .env"
        )

    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        },
        timeout=30,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "\nCDSE authentication failed.\n\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text}"
        )

    data = response.json()

    access_token = data.get(
        "access_token"
    )

    if not access_token:

        raise RuntimeError(
            "No access token returned by CDSE."
        )

    print(
        "✓ CDSE download authentication successful."
    )

    print()

    return access_token


# ============================================================
# FIND PRODUCT UUID
# ============================================================

def get_product_id(
    access_token,
    scene_name
):

    print(
        "Finding Copernicus product UUID..."
    )

    headers = {
        "Authorization":
            f"Bearer {access_token}"
    }

    params = {

        "$filter":
            f"Name eq '{scene_name}'",

        "$select":
            "Id,Name,Online",
    }

    response = requests.get(
        CATALOG_URL,
        headers=headers,
        params=params,
        timeout=60,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "\nProduct lookup failed.\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text}"
        )

    products = response.json().get(
        "value",
        []
    )

    if not products:

        raise RuntimeError(
            f"\nProduct not found:\n{scene_name}"
        )

    product = products[0]

    product_id = product.get(
        "Id"
    )

    if not product_id:

        raise RuntimeError(
            "Product has no UUID."
        )

    print(
        f"✓ Product ID found: {product_id}"
    )

    print(
        f"✓ Online: {product.get('Online')}"
    )

    print()

    return product_id


# ============================================================
# LIST CHILD NODES
# ============================================================

def list_nodes(
    session,
    url
):

    response = session.get(
        url,
        timeout=60,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "\nFailed to list Copernicus nodes.\n\n"
            f"HTTP: {response.status_code}\n"
            f"URL: {url}\n"
            f"Response: {response.text[:2000]}"
        )

    data = response.json()

    return data.get(
        "result",
        []
    )


# ============================================================
# RECURSIVELY FIND REQUIRED FILES
# ============================================================

def find_required_files(
    session,
    product_id
):

    print(
        "Searching product structure..."
    )

    print()

    root_url = (
        f"{DOWNLOAD_URL}"
        f"/Products({product_id})/Nodes"
    )

    found = {}

    # --------------------------------------------------------
    # Recursive traversal
    # --------------------------------------------------------

    def walk(
        listing_url,
        node_path
    ):

        nodes = list_nodes(
            session,
            listing_url
        )

        for node in nodes:

            name = node.get(
                "Name",
                ""
            )

            if not name:
                continue

            current_path = (
                node_path + [name]
            )

            upper_name = name.upper()

            # ------------------------------------------------
            # Check for required file
            # ------------------------------------------------

            for band, marker in (
                REQUIRED_FILE_MARKERS.items()
            ):

                if band in found:
                    continue

                if upper_name.endswith(
                    marker.upper()
                ):

                    found[band] = {
                        "name":
                            name,

                        "path":
                            current_path,
                    }

                    print(
                        f"✓ Found {band}:"
                    )

                    print(
                        f"  {('/'.join(current_path))}"
                    )

            # ------------------------------------------------
            # Folder?
            #
            # Copernicus puts child URI here:
            #
            # node["Nodes"]["uri"]
            # ------------------------------------------------

            children_number = node.get(
                "ChildrenNumber",
                0
            )

            nodes_info = node.get(
                "Nodes"
            )

            if (
                children_number
                and isinstance(
                    nodes_info,
                    dict
                )
            ):

                child_url = nodes_info.get(
                    "uri"
                )

                if child_url:

                    walk(
                        child_url,
                        current_path
                    )

            # ------------------------------------------------
            # Stop early once all seven files are found.
            # ------------------------------------------------

            if len(found) == len(
                REQUIRED_FILE_MARKERS
            ):

                return

    walk(
        root_url,
        []
    )

    print()

    missing = [
        band
        for band in REQUIRED_FILE_MARKERS
        if band not in found
    ]

    if missing:

        raise RuntimeError(
            "\nRequired Sentinel-2 files were not found:\n"
            + ", ".join(missing)
        )

    print(
        "✓ All required Sentinel-2 files found."
    )

    print()

    return found


# ============================================================
# BUILD FILE DOWNLOAD URL
# ============================================================

def build_download_url(
    product_id,
    node_path
):

    url = (
        f"{DOWNLOAD_URL}"
        f"/Products({product_id})"
    )

    for node_name in node_path:

        encoded_name = quote(
            node_name,
            safe=""
        )

        url += (
            f"/Nodes({encoded_name})"
        )

    url += "/$value"

    return url


# ============================================================
# DOWNLOAD ONE FILE
# ============================================================

def download_file(
    session,
    product_id,
    node,
    output_path
):

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    url = build_download_url(
        product_id,
        node["path"]
    )

    print(
        f"Downloading {node['name']}..."
    )

    print(
        f"URL: {url}"
    )

    print(
        f"Destination: {output_path}"
    )

    print()

    # --------------------------------------------------------
    # First request
    # --------------------------------------------------------

    response = session.get(
        url,
        stream=True,
        timeout=120,
        allow_redirects=True
    )

    if response.status_code != 200:

        raise RuntimeError(
            "\nDownload failed.\n\n"
            f"File: {node['name']}\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text[:2000]}"
        )

    total_size = response.headers.get(
        "Content-Length"
    )

    if total_size:

        total_size = int(
            total_size
        )

    downloaded = 0

    with open(
        output_path,
        "wb"
    ) as file:

        for chunk in response.iter_content(
            chunk_size=1024 * 1024
        ):

            if not chunk:
                continue

            file.write(
                chunk
            )

            downloaded += len(
                chunk
            )

            if total_size:

                percentage = (
                    downloaded
                    / total_size
                    * 100
                )

                print(
                    f"\r  Progress: "
                    f"{percentage:6.2f}%",
                    end="",
                    flush=True
                )

    print()

    print(
        f"✓ Downloaded: {output_path.name}"
    )

    print()


# ============================================================
# SAVE METADATA
# ============================================================

def save_metadata(
    scene,
    product_id,
    output_folder,
    downloaded_files
):

    metadata = {

        "scene_id":
            scene.get("scene_id"),

        "product_id":
            product_id,

        "datetime":
            scene.get("datetime"),

        "cloud_cover":
            scene.get("cloud_cover"),

        "bands":
            downloaded_files,
    }

    output_file = (
        output_folder
        / "metadata.json"
    )

    with open(
        output_file,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2
        )

    print(
        "✓ Metadata saved:"
    )

    print(
        output_file
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print("=" * 70)

    print(
        "S.I.H - COPERNICUS SENTINEL-2 DOWNLOADER"
    )

    print("=" * 70)

    print()

    # --------------------------------------------------------
    # 1. Select best scene
    # --------------------------------------------------------

    scene = get_best_scene()

    scene_name = scene[
        "scene_id"
    ]

    print(
        "Selected scene:"
    )

    print(
        scene_name
    )

    print()

    print(
        f"Cloud cover: "
        f"{scene.get('cloud_cover')}%"
    )

    print(
        f"Date: "
        f"{scene.get('datetime')}"
    )

    print()

    # --------------------------------------------------------
    # 2. Authenticate
    # --------------------------------------------------------

    access_token = (
        get_access_token()
    )

    # --------------------------------------------------------
    # 3. Get UUID
    # --------------------------------------------------------

    product_id = get_product_id(
        access_token,
        scene_name
    )

    # --------------------------------------------------------
    # 4. Prepare output
    # --------------------------------------------------------

    output_folder = (
        OUTPUT_ROOT
        / scene_name
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    # --------------------------------------------------------
    # 5. Authenticated session
    # --------------------------------------------------------

    session = requests.Session()

    session.headers.update(
        {
            "Authorization":
                f"Bearer {access_token}"
        }
    )

    # --------------------------------------------------------
    # 6. Find required files
    # --------------------------------------------------------

    required_files = (
        find_required_files(
            session,
            product_id
        )
    )

    # --------------------------------------------------------
    # 7. Download
    # --------------------------------------------------------

    print("=" * 70)

    print(
        "DOWNLOADING REQUIRED SENTINEL-2 FILES"
    )

    print("=" * 70)

    print()

    downloaded_files = {}

    for band in REQUIRED_FILE_MARKERS:

        node = required_files[
            band
        ]

        output_path = (
            output_folder
            / node["name"]
        )

        # Don't download an existing file again.
        if output_path.exists():

            print(
                f"✓ Already exists: "
                f"{output_path.name}"
            )

            print()

        else:

            download_file(
                session,
                product_id,
                node,
                output_path
            )

        downloaded_files[
            band
        ] = node["name"]

    # --------------------------------------------------------
    # 8. Metadata
    # --------------------------------------------------------

    save_metadata(
        scene,
        product_id,
        output_folder,
        downloaded_files
    )

    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

    print("=" * 70)

    print(
        "COPERNICUS DOWNLOAD COMPLETE"
    )

    print("=" * 70)

    print()

    print(
        "Scene:"
    )

    print(
        output_folder
    )

    print()

    print(
        "Files:"
    )

    for band in downloaded_files:

        print(
            f"  ✓ {band}"
        )

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()