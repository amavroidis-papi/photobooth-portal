import streamlit as st
import dropbox
from dropbox.exceptions import ApiError, AuthError
import json
import io
import os

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------
GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# MASTER STATION LIST (later we can move this to a Dropbox manifest)
KNOWN_STATIONS = sorted([
    "DC Standard",
    "Dell Laptop",
    "Dell XPS",
    "DellNew1",
    "DellNew2",
    "DellNew3",
    "DellNew4",
    "HP_Envy",
    "HP1",
    "HP2",
    "HP3",
    "HP4",
    "Laptop 3",
    "Lenovo 1",
    "Lenovo 2",
    "Mini1BackUp",
    "Mini1Standard",
    "Mini2BackUp",
    "Mini2Standard",
    "Mini3",
    "Mini3BackUp",
    "Mini4Standard",
    "TXStandard",
])

# Dropbox credentials (preferred: refresh-token auth)
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")

# Legacy fallback (not recommended)
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")

# --------------------------------------------------
# DROPBOX INIT
# --------------------------------------------------

def init_dropbox() -> dropbox.Dropbox:
    try:
        if DROPBOX_REFRESH_TOKEN and DROPBOX_APP_KEY and DROPBOX_APP_SECRET:
            return dropbox.Dropbox(
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN,
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
            )
        if DROPBOX_TOKEN:
            st.sidebar.warning("Using legacy DROPBOX_TOKEN (static). Prefer refresh-token auth.")
            return dropbox.Dropbox(DROPBOX_TOKEN)

        st.error("Dropbox credentials missing. Set DROPBOX_REFRESH_TOKEN, DROPBOX_APP_KEY, DROPBOX_APP_SECRET.")
        st.stop()
    except AuthError as e:
        st.error(f"Dropbox auth failed: {e}")
        st.stop()


dbx = init_dropbox()

# --------------------------------------------------
# DROPBOX HELPERS (NO SILENT FAILURES)
# --------------------------------------------------

def dbx_list_folder(path: str):
    try:
        return dbx.files_list_folder(path).entries
    except ApiError as e:
        st.sidebar.error(f"Dropbox list_folder failed: {path}")
        st.sidebar.exception(e)
        return []


def dbx_download_json(path: str):
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content))
    except ApiError as e:
        st.sidebar.error(f"Dropbox download failed: {path}")
        st.sidebar.exception(e)
        return None
    except json.JSONDecodeError:
        st.sidebar.error(f"Invalid JSON: {path}")
        return None


def dbx_upload_json(path: str, data: dict) -> bool:
    try:
        payload = json.dumps(data, indent=2).encode("utf-8")
        dbx.files_upload(payload, path, mode=dropbox.files.WriteMode.overwrite)
        return True
    except ApiError as e:
        st.error(f"Dropbox upload failed: {path}")
        st.exception(e)
        return False


def dbx_upload_bytes(path: str, raw: bytes) -> bool:
    try:
        dbx.files_upload(raw, path, mode=dropbox.files.WriteMode.overwrite)
        return True
    except ApiError as e:
        st.error(f"Dropbox upload failed: {path}")
        st.exception(e)
        return False

# --------------------------------------------------
# APP HELPERS
# --------------------------------------------------

def get_fleet_data():
    servers = []
    for entry in dbx_list_folder(HEALTH_FOLDER):
        if entry.name.endswith(".json"):
            data = dbx_download_json(entry.path_lower)
            if data:
                servers.append(data)
    return servers


def load_config(station_id: str):
    path = f"/{station_id}/config.json"
    cfg = dbx_download_json(path)
    return cfg, path


def save_config(cfg: dict, path: str) -> bool:
    return dbx_upload_json(path, cfg)


def upload_asset(uploaded_file, target_path: str) -> bool:
    return dbx_upload_bytes(target_path, uploaded_file.getvalue())


def get_available_actions():
    actions = []
    for entry in dbx_list_folder(ACTIONS_FOLDER):
        if entry.name.endswith(".atn"):
            actions.append(entry.name.replace(".atn", ""))
    return sorted(actions)


def build_assignment_map():
    assigned_to_server = {}
    server_to_stations = {}
    for s in KNOWN_STATIONS:
        cfg, _ = load_config(s)
        if not cfg:
            continue
        server = cfg.get("assigned_server")
        if server and server != "Unassigned":
            assigned_to_server[s] = server
            server_to_stations.setdefault(server, []).append(s)
    for sid in list(server_to_stations.keys()):
        server_to_stations[sid] = sorted(server_to_stations[sid])
    return assigned_to_server, server_to_stations

# --------------------------------------------------
# UI
# --------------------------------------------------

st.set_page_config(page_title="Photobooth Fleet Command", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

fleet_data = get_fleet_data()
online_server_ids = sorted(list({s.get("server_id") for s in fleet_data if s.get("server_id")}))

# Dashboard metrics
if fleet_data:
    m1, m2, m3 = st.columns(3)
    total_online = len(fleet_data)
    avg_disk = sum([float(s.get("disk_free_gb", 0)) for s in fleet_data]) / total_online
    m1.metric("Servers Online", total_online)
    m2.metric("Avg Free Disk", f"{avg_disk:.1f} GB")
    m3.metric("Manager Version", fleet_data[0].get("version", "—"))

st.divider()

# Sidebar: Fleet Health
st.sidebar.header("📡 Live Fleet Health")
if fleet_data:
    for server in fleet_data:
        sid = server.get("server_id", "—")
        active = server.get("active_stations", [])
        last_seen = server.get("last_seen", "—")
        with st.sidebar.expander(f"🖥️ Server: {sid}", expanded=True):
            disk_val = float(server.get("disk_free_gb", 0) or 0)
            disk_color = "green" if disk_val > 20 else "orange" if disk_val > 10 else "red"
            st.write(f"**Disk Space:** :{disk_color}[{disk_val} GB Free]")
            st.progress(min(disk_val / 100, 1.0))
            st.write(f"**Active Stations:** `{', '.join(active) if active else '—'}`")
            st.caption(f"Last Seen: {last_seen}")
else:
    st.sidebar.warning("No servers online (or Dropbox health folder unreadable).")

# Sidebar: Server filter
st.sidebar.divider()
st.sidebar.header("🗂️ View")
server_filter = st.sidebar.selectbox("Server View", ["All Servers"] + online_server_ids, index=0)

assigned_to_server, server_to_stations = build_assignment_map()

# Station list shown depends on filter
if server_filter == "All Servers":
    selectable_stations = KNOWN_STATIONS
else:
    selectable_stations = server_to_stations.get(server_filter, [])
    unassigned = [s for s in KNOWN_STATIONS if assigned_to_server.get(s) in (None, "Unassigned")]
    selectable_stations = sorted(list(set(selectable_stations + unassigned)))

# Sidebar: Station manager
st.sidebar.divider()
st.sidebar.header("🎮 Station Manager")
selected_station = st.sidebar.selectbox("Select Station to Configure", selectable_stations)

if not selected_station:
    st.stop()

st.header(f"🔧 Managing: {selected_station}")
config, config_path = load_config(selected_station)

if not config:
    st.warning(f"Config file missing for {selected_station}.")
    st.caption(f"Expected path: `{config_path}`")
    st.stop()

# --------------------------------------------------
# MASTER ASSIGNMENT
# --------------------------------------------------
col_sw, col_assign, col_status = st.columns([2, 3, 2])

with col_sw:
    is_enabled = bool(config.get("station_enabled", True))
    new_enabled = st.toggle("Station Processing ON/OFF", value=is_enabled)

with col_assign:
    curr_assign = config.get("assigned_server", "Unassigned") or "Unassigned"
    assign_options = ["Unassigned"] + online_server_ids
    if curr_assign != "Unassigned" and curr_assign not in assign_options:
        assign_options.append(curr_assign)
    # keep Unassigned first
    assign_options = ["Unassigned"] + sorted([x for x in assign_options if x != "Unassigned"])

    idx = assign_options.index(curr_assign) if curr_assign in assign_options else 0
    new_assign = st.selectbox("Assign to Manager", assign_options, index=idx)

with col_status:
    st.success("🟢 Active") if new_enabled else st.error("🔴 Disabled")

if new_enabled != is_enabled or new_assign != curr_assign:
    config["station_enabled"] = new_enabled
    config["assigned_server"] = new_assign
    if save_config(config, config_path):
        st.success("Saved.")
        st.rerun()

st.divider()

# --------------------------------------------------
# SETTINGS TABS (keep your existing features)
# --------------------------------------------------

tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets (Templates)", "🎬 Profiles & Actions"])

with tab1:
    c1, c2 = st.columns(2)
    settings = config.setdefault("settings", {})

    with c1:
        curr_bg = bool(settings.get("remove_background", False))
        new_bg = st.toggle("Remove Background (API)", value=curr_bg)

        curr_key = settings.get("remove_bg_api_key", "")
        new_key = st.text_input("remove.bg API Key", value=curr_key, type="password")

        curr_temp = int(settings.get("temperature", 0) or 0)
        new_temp = st.slider("Color Temperature", -100, 100, curr_temp)

    with c2:
        modes = ["auto", "force_portrait", "force_landscape"]
        curr_mode = settings.get("orientation_mode", "auto") or "auto"
        if curr_mode not in modes:
            curr_mode = "auto"
        new_mode = st.selectbox("Orientation Mode", modes, index=modes.index(curr_mode))

    if st.button("Save Global Settings"):
        settings.update({
            "remove_background": new_bg,
            "remove_bg_api_key": new_key,
            "temperature": new_temp,
            "orientation_mode": new_mode,
        })
        if save_config(config, config_path):
            st.success("Settings saved.")
            st.rerun()

with tab2:
    st.subheader("Upload Templates")
    st.caption(f"Path: /{selected_station}/templates/")
    ca, cb = st.columns(2)
    with ca:
        bg = st.file_uploader("Upload Background (.jpg)", type=["jpg", "jpeg"], key="bg_up")
        if bg and st.button("Save BG"):
            if upload_asset(bg, f"/{selected_station}/templates/background.jpg"):
                st.success("Background uploaded.")
    with cb:
        ol = st.file_uploader("Upload Overlay (.png)", type=["png"], key="ol_up")
        if ol and st.button("Save Overlay"):
            if upload_asset(ol, f"/{selected_station}/templates/overlay.png"):
                st.success("Overlay uploaded.")

with tab3:
    st.subheader("Profiles & Actions")
    available_actions = get_available_actions()
    if not available_actions:
        st.info("No .atn files found in /_Global_Assets/Actions")

    prof = config.setdefault("active_profile", {"portrait": {}, "landscape": {}})
    portrait = prof.setdefault("portrait", {})
    landscape = prof.setdefault("landscape", {})

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Portrait**")
        p_action = portrait.get("action_name", available_actions[0] if available_actions else "")
        new_p_action = (
            st.selectbox(
                "Portrait Action",
                available_actions,
                index=(available_actions.index(p_action) if p_action in available_actions else 0),
            )
            if available_actions
            else st.text_input("Portrait Action Name", value=p_action)
        )

    with c2:
        st.markdown("**Landscape**")
        l_action = landscape.get("action_name", available_actions[0] if available_actions else "")
        new_l_action = (
            st.selectbox(
                "Landscape Action",
                available_actions,
                index=(available_actions.index(l_action) if l_action in available_actions else 0),
            )
            if available_actions
            else st.text_input("Landscape Action Name", value=l_action)
        )

    if st.button("Update Profiles"):
        portrait["action_name"] = new_p_action
        landscape["action_name"] = new_l_action
        portrait.setdefault("action_set", portrait.get("action_set", "Photobooth_Actions"))
        landscape.setdefault("action_set", landscape.get("action_set", "Photobooth_Actions"))
        if save_config(config, config_path):
            st.success("Profiles updated.")
            st.rerun()

    st.divider()
    st.subheader("Subfolder Management")
    cur_sub = config.get("subfolder_action_set", "Event_Subfolders")
    new_sub = st.text_input("Subfolder Action Set", value=cur_sub)
    if st.button("Save Subfolder Set"):
        config["subfolder_action_set"] = new_sub
        if save_config(config, config_path):
            st.success("Subfolder set saved.")
            st.rerun()
