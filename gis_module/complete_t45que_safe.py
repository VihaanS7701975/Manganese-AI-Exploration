from pathlib import Path
import os
import shutil
import requests
from urllib.parse import quote


# ============================================================
# S.I.H - COMPLETE T45QUE SAFE STRUCTURE
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SATELLITE_FOLDER = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "satellite_images"
)

# ------------------------------------------------------------
# Exact Copernicus product
# ------------------------------------------------------------

PRODUCT_ID = (
    "289a0a5e-ebc9-4772-b042-854965a6fb5c"
)

PRODUCT_NAME = (
    "S2B_MSIL2A_20260416T044659_N0512_R076_T45QUE_20260416T083549.SAFE"
)

GRANULE_NAME = (
    "L2A_T45QUE_A047578_20260416T045723"
)

SAFE_FOLDER = (
    SATELLITE_FOLDER
    / PRODUCT_NAME
)

GRANULE_FOLDER = (
    SAFE_FOLDER
    / "GRANULE"
    / GRANULE_NAME
)

R10M_FOLDER = (
    GRANULE_FOLDER
    / "IMG_DATA"
    / "R10m"
)

R20M_FOLDER = (
    GRANULE_FOLDER
    / "IMG_DATA"
    / "R20m"
)


# ============================================================
# COPERNICUS URLS
# ============================================================

TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/"
    "auth/realms/CDSE/protocol/openid-connect/token"
)

DOWNLOAD_BASE = (
    "https://download.dataspace.copernicus.eu"
    "/odata/v1"
)


# ============================================================
# LOAD .ENV WITHOUT NEEDING EXTRA PACKAGES
# ============================================================

def load_env_file():

    env_file = PROJECT_ROOT / ".env"

    if not env_file.exists():

        raise FileNotFoundError(
            "\n.env file was not found.\n\n"
            f"Expected:\n{env_file}"
        )

    values = {}

    with open(
        env_file,
        "r",
        encoding="utf-8"
    ) as file:

        for line in file:

            line = line.strip()

            if not line:
                continue

            if line.startswith("#"):
                continue

            if "=" not in line:
                continue

            key, value = line.split(
                "=",
                1
            )

            key = key.strip()
            value = value.strip()

            # Remove optional quotes.
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {"'", '"'}
            ):
                value = value[1:-1]

            values[key] = value

    return values


# ============================================================
# AUTHENTICATION
# ============================================================

def get_access_token():

    print(
        "Authenticating with Copernicus CDSE..."
    )

    env = load_env_file()

    username = (
        env.get("CDSE_USERNAME")
        or os.getenv("CDSE_USERNAME")
    )

    password = (
        env.get("CDSE_PASSWORD")
        or os.getenv("CDSE_PASSWORD")
    )

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

        timeout=60,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "\nCopernicus authentication failed.\n\n"
            f"HTTP: {response.status_code}\n"
            f"Response: {response.text}"
        )

    data = response.json()

    token = data.get(
        "access_token"
    )

    if not token:

        raise RuntimeError(
            "Copernicus did not return an access token."
        )

    print(
        "✓ Authentication successful."
    )

    print()

    return token


# ============================================================
# CREATE NODE URL
# ============================================================

def node_url(
    product_id,
    nodes
):

    url = (
        f"{DOWNLOAD_BASE}"
        f"/Products({product_id})"
    )

    for node in nodes:

        url += (
            "/Nodes("
            + quote(
                node,
                safe=""
            )
            + ")"
        )

    return url


# ============================================================
# DOWNLOAD ONE PRODUCT FILE
# ============================================================

def download_product_file(
    session,
    token,
    nodes,
    destination
):

    url = (
        node_url(
            PRODUCT_ID,
            nodes
        )
        + "/$value"
    )

    destination = Path(
        destination
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    print(
        f"Downloading:\n"
        f"  {nodes[-1]}"
    )

    print(
        f"Destination:\n"
        f"  {destination}"
    )

    response = session.get(
        url,
        headers={
            "Authorization":
                f"Bearer {token}"
        },
        stream=True,
        timeout=120,
    )

    if response.status_code != 200:

        raise RuntimeError(
            "\nDownload failed.\n\n"
            f"File: {nodes[-1]}\n"
            f"HTTP: {response.status_code}\n"
            f"Response: "
            f"{response.text[:2000]}"
        )

    total = (
        int(
            response.headers.get(
                "Content-Length",
                0
            )
        )
    )

    downloaded = 0

    temp_file = destination.with_suffix(
        destination.suffix + ".part"
    )

    try:

        with open(
            temp_file,
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

                if total:

                    percent = (
                        downloaded
                        / total
                        * 100
                    )

                    print(
                        f"\r  Progress: "
                        f"{percent:6.2f}%",
                        end=""
                    )

        print()

        temp_file.replace(
            destination
        )

    except Exception:

        if temp_file.exists():

            temp_file.unlink()

        raise

    print(
        "✓ Downloaded."
    )

    print()


# ============================================================
# MOVE EXISTING BAND
# ============================================================

def move_existing_file(
    filename,
    destination_folder
):

    source = (
        SAFE_FOLDER
        / filename
    )

    destination_folder = Path(
        destination_folder
    )

    destination_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    destination = (
        destination_folder
        / filename
    )

    if not source.exists():

        raise FileNotFoundError(
            "\nExisting file was not found:\n"
            f"{source}"
        )

    if destination.exists():

        print(
            f"✓ Already in correct location:\n"
            f"  {destination}"
        )

        return

    print(
        f"Moving:\n"
        f"  {filename}"
    )

    shutil.move(
        str(source),
        str(destination)
    )

    print(
        f"✓ Moved to:\n"
        f"  {destination}"
    )

    print()


# ============================================================
# CREATE SAFE DIRECTORIES
# ============================================================

def create_safe_directories():

    print(
        "Creating Sentinel-2 SAFE directories..."
    )

    directories = [
        GRANULE_FOLDER,
        R10M_FOLDER,
        R20M_FOLDER,
    ]

    for directory in directories:

        directory.mkdir(
            parents=True,
            exist_ok=True
        )

        print(
            f"✓ {directory}"
        )

    print()


# ============================================================
# MOVE EXISTING SEVEN RASTER FILES
# ============================================================

def organize_existing_bands():

    print(
        "Organizing existing JP2 files..."
    )

    # --------------------------------------------------------
    # 10 m bands
    # --------------------------------------------------------

    move_existing_file(
        "T45QUE_20260416T044659_B02_10m.jp2",
        R10M_FOLDER
    )

    move_existing_file(
        "T45QUE_20260416T044659_B03_10m.jp2",
        R10M_FOLDER
    )

    move_existing_file(
        "T45QUE_20260416T044659_B04_10m.jp2",
        R10M_FOLDER
    )

    move_existing_file(
        "T45QUE_20260416T044659_B08_10m.jp2",
        R10M_FOLDER
    )

    # --------------------------------------------------------
    # 20 m bands
    # --------------------------------------------------------

    move_existing_file(
        "T45QUE_20260416T044659_B11_20m.jp2",
        R20M_FOLDER
    )

    move_existing_file(
        "T45QUE_20260416T044659_B12_20m.jp2",
        R20M_FOLDER
    )

    move_existing_file(
        "T45QUE_20260416T044659_SCL_20m.jp2",
        R20M_FOLDER
    )


# ============================================================
# DOWNLOAD PRODUCT METADATA
# ============================================================

def download_metadata(
    session,
    token
):

    print(
        "Downloading missing SAFE metadata..."
    )

    # --------------------------------------------------------
    # Product-level metadata
    # --------------------------------------------------------

    download_product_file(
        session=session,
        token=token,

        nodes=[
            PRODUCT_NAME,
            "MTD_MSIL2A.xml",
        ],

        destination=(
            SAFE_FOLDER
            / "MTD_MSIL2A.xml"
        )
    )

    # --------------------------------------------------------
    # SAFE manifest
    # --------------------------------------------------------

    download_product_file(
        session=session,
        token=token,

        nodes=[
            PRODUCT_NAME,
            "manifest.safe",
        ],

        destination=(
            SAFE_FOLDER
            / "manifest.safe"
        )
    )

    # --------------------------------------------------------
    # Granule metadata
    # --------------------------------------------------------

    download_product_file(
        session=session,
        token=token,

        nodes=[
            PRODUCT_NAME,
            "GRANULE",
            GRANULE_NAME,
            "MTD_TL.xml",
        ],

        destination=(
            GRANULE_FOLDER
            / "MTD_TL.xml"
        )
    )


# ============================================================
# VERIFY STRUCTURE
# ============================================================

def verify_structure():

    print(
        "=" * 70
    )

    print(
        "VERIFYING T45QUE SAFE STRUCTURE"
    )

    print(
        "=" * 70
    )

    print()

    required_files = {

        "MTD_MSIL2A.xml":
            SAFE_FOLDER
            / "MTD_MSIL2A.xml",

        "manifest.safe":
            SAFE_FOLDER
            / "manifest.safe",

        "MTD_TL.xml":
            GRANULE_FOLDER
            / "MTD_TL.xml",

        "B02":
            R10M_FOLDER
            / "T45QUE_20260416T044659_B02_10m.jp2",

        "B03":
            R10M_FOLDER
            / "T45QUE_20260416T044659_B03_10m.jp2",

        "B04":
            R10M_FOLDER
            / "T45QUE_20260416T044659_B04_10m.jp2",

        "B08":
            R10M_FOLDER
            / "T45QUE_20260416T044659_B08_10m.jp2",

        "B11":
            R20M_FOLDER
            / "T45QUE_20260416T044659_B11_20m.jp2",

        "B12":
            R20M_FOLDER
            / "T45QUE_20260416T044659_B12_20m.jp2",

        "SCL":
            R20M_FOLDER
            / "T45QUE_20260416T044659_SCL_20m.jp2",
    }

    all_found = True

    for name, path in required_files.items():

        if path.exists():

            size_mb = (
                path.stat().st_size
                / (1024 * 1024)
            )

            print(
                f"✓ {name:18} "
                f"{size_mb:8.2f} MB"
            )

        else:

            print(
                f"✗ {name:18} MISSING"
            )

            all_found = False

    print()

    if not all_found:

        raise RuntimeError(
            "SAFE verification failed."
        )

    print(
        "✓ Required T45QUE SAFE structure "
        "is present."
    )

    print()

    print(
        "SAFE:"
    )

    print(
        SAFE_FOLDER
    )

    print()


# ============================================================
# PRINT TREE
# ============================================================

def print_tree():

    print(
        "=" * 70
    )

    print(
        "T45QUE SAFE STRUCTURE"
    )

    print(
        "=" * 70
    )

    print()

    print(
        f"{PRODUCT_NAME}/"
    )

    print(
        "├── MTD_MSIL2A.xml"
    )

    print(
        "├── manifest.safe"
    )

    print(
        "└── GRANULE/"
    )

    print(
        f"    └── {GRANULE_NAME}/"
    )

    print(
        "        ├── MTD_TL.xml"
    )

    print(
        "        └── IMG_DATA/"
    )

    print(
        "            ├── R10m/"
    )

    print(
        "            │   ├── B02_10m.jp2"
    )

    print(
        "            │   ├── B03_10m.jp2"
    )

    print(
        "            │   ├── B04_10m.jp2"
    )

    print(
        "            │   └── B08_10m.jp2"
    )

    print(
        "            │"
    )

    print(
        "            └── R20m/"
    )

    print(
        "                ├── B11_20m.jp2"
    )

    print(
        "                ├── B12_20m.jp2"
    )

    print(
        "                └── SCL_20m.jp2"
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 70)
    print(
        "S.I.H - T45QUE SAFE COMPLETION"
    )
    print("=" * 70)
    print()

    print(
        "Product:"
    )

    print(
        PRODUCT_NAME
    )

    print()

    print(
        "Product ID:"
    )

    print(
        PRODUCT_ID
    )

    print()

    # --------------------------------------------------------
    # Verify starting files first.
    # --------------------------------------------------------

    if not SAFE_FOLDER.exists():

        raise FileNotFoundError(
            "\nT45QUE SAFE folder not found:\n"
            f"{SAFE_FOLDER}"
        )

    # --------------------------------------------------------
    # Authenticate.
    # --------------------------------------------------------

    token = get_access_token()

    # --------------------------------------------------------
    # HTTP session.
    # --------------------------------------------------------

    session = requests.Session()

    # --------------------------------------------------------
    # Create directories.
    # --------------------------------------------------------

    create_safe_directories()

    # --------------------------------------------------------
    # Move existing seven JP2 files.
    # --------------------------------------------------------

    organize_existing_bands()

    # --------------------------------------------------------
    # Download only missing metadata.
    # --------------------------------------------------------

    download_metadata(
        session=session,
        token=token
    )

    # --------------------------------------------------------
    # Verify.
    # --------------------------------------------------------

    verify_structure()

    print_tree()

    print("=" * 70)
    print(
        "T45QUE SAFE COMPLETION SUCCESSFUL"
    )
    print("=" * 70)
    print()

    print(
        "✓ Existing six bands were NOT re-downloaded."
    )

    print(
        "✓ Existing SCL was NOT re-downloaded."
    )

    print(
        "✓ Official product metadata downloaded."
    )

    print(
        "✓ Bands placed into Sentinel-2 SAFE structure."
    )

    print(
        "✓ T45QUE is ready for P1."
    )

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Operation cancelled."
        )

        raise SystemExit(1)

    except Exception as error:

        print()
        print("=" * 70)
        print("ERROR")
        print("=" * 70)
        print()

        print(
            f"{type(error).__name__}: {error}"
        )

        print()

        raise