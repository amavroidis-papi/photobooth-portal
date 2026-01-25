import streamlit as st
import dropbox
from dropbox.exceptions import ApiError, AuthError
import json
import pandas as pd
import io
import os
import time

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# Dropbox credentials (preferred: refresh-token auth)
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")

# Legacy fallback (NOT recommended)
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")

# --------------------------------------------------
# DROPBOX CLIENT INITIALIZATION
# --------------------------------------------------
def init_dropbox():
    try:
        if DROPBOX_REFRESH_TOKEN and DROPBOX_APP_KEY and DROPBOX_APP_SECRET:
            return dropbox.Dropbox(
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
            )
        elif DROPBOX_TOKEN:
            st.warning("Using legacy DROPBOX_TOKEN. Consider refresh-token auth.")
            return dropbox.Dropbox(DROPBOX_TOKEN)
        else:
            st.error("Dropbox credentials missing. Configure refresh-token auth in Heroku.")
            st.stop()
    except AuthError as e:
        st.error(f"Dropbox auth failed: {e}")
        st.stop()


dbx = init_dropbox()

# --------------------------------------------------
# SAFE DROPBOX HELPERS (NO SILENT FAILURES)
# --------------------------------------------------
def list_folder(path):
    try:
        return dbx.files_list_folder(path).entries
    except ApiError as e:
        st.sidebar.error(f"Dropbox list failed: {path}")
        st.sidebar.exception(e)
        return []


def download_json(path):
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content))
    except ApiError as e:
        st.sidebar.error(f"Dropbox download failed: {path}")
        st.sidebar.exception(e)
    except json.JSONDecodeError:
        st.sidebar.error(f"Invalid JSON: {path}")
    return None

# --------------------------------------------------
# DATA LOADERS
# --------------------------------------------------
def load_fleet_health():
    servers = []
    entries = list_folder(HEALTH_FOLDER)

    for entry in entries:
        if entry.name.endswith(".json"):
            data = download_json(entry.path_lower)
            if data:
                servers.append(data)

    return servers


# MASTER STATION LIST
KNOWN_STATIONS = sorted([
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2",
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4",
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard",
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp",
    "Mini4Standard", "TXStandard"
])

# --------------------------------------------------
# UI
# --------------------------------------------------
st.set_page_config(page_title="Photobooth Fleet Command", layout="wide")

st.title("📷 Photobooth Fleet Command")

# Sidebar – Fleet Health
st.sidebar.header("📡 Live Fleet Health")
servers = load_fleet_health()

if not servers:
    st.sidebar.warning("No servers online or Dropbox unreadable.")
else:
    for s in servers:
        st.sidebar.success(
            f"Server {s.get('server_id')} ONLINE\n"
            f"Stations: {', '.join(s.get('active_stations', []))}\n"
            f"Last Seen: {s.get('last_seen')}"
        )

# Station Manager
st.sidebar.header("🎮 Station Manager")
station = st.sidebar.selectbox("Select Station to Configure", KNOWN_STATIONS)

st.subheader(f"🛠 Managing: {station}")

config_path = f"/{station}/config.json"
config = download_json(config_path)

if not config:
    st.warning(f"Config file missing for {station}.")
    st.stop()

# --------------------------------------------------
# SETTINGS UI
# --------------------------------------------------
st.checkbox("Station Enabled", value=config.get("station_enabled", True))

settings = config.get("settings", {})
settings["remove_background"] = st.checkbox(
    "Remove Background", value=settings.get("remove_background", False)
)

settings["temperature"] = st.slider(
    "Color Temperature",
    -100, 100,
    settings.get("temperature", 0)
)

st.caption("Changes are written to Dropbox and picked up by the supervisor automatically.")
