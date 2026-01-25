import streamlit as st
import dropbox
import json
import io
import os
import pandas as pd

# --- CONFIGURATION ---
# Auth Keys
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")

GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# --- CONNECT TO DROPBOX ---
try:
    if DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN:
        dbx = dropbox.Dropbox(
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET,
            oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
        )
    elif DROPBOX_TOKEN:
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    else:
        st.error("Missing Credentials")
        st.stop()
except Exception as e:
    st.error(f"Connection Error: {e}")
    st.stop()

# --- DATA FUNCTIONS ---
@st.cache_data(ttl=60)
def get_fleet_status():
    """Reads server health JSONs to see who is online."""
    servers = {}
    try:
        res = dbx.files_list_folder(HEALTH_FOLDER)
        for entry in res.entries:
            if entry.name.endswith('.json'):
                try:
                    _, res = dbx.files_download(entry.path_lower)
                    data = json.load(io.BytesIO(res.content))
                    servers[data['server_id']] = data
                except: pass
    except: pass
    return servers

@st.cache_data(ttl=300)
def discover_stations():
    """Scans root for folders containing config.json."""
    stations = []
    try:
        res = dbx.files_list_folder("", recursive=False)
        for entry in res.entries:
            if isinstance(entry, dropbox.files.FolderMetadata):
                # Check for config.json inside (lightweight check)
                try:
                    dbx.files_get_metadata(f"/{entry.name}/config.json")
                    stations.append(entry.name)
                except: pass
    except: pass
    return sorted(stations)

def get_station_config(station_id):
    try:
        _, res = dbx.files_download(f"/{station_id}/config.json")
        return json.load(io.BytesIO(res.content))
    except: return None

def save_config(station_id, config_data):
    path = f"/{station_id}/config.json"
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)

# --- UI ---
st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")

# 1. HEADER & SERVER METRICS
servers = get_fleet_status()
server_ids = list(servers.keys())

c1, c2, c3 = st.columns([1,3,1])
c1.title("📷 Fleet")
if servers:
    for sid, data in servers.items():
        c2.info(f"**{sid}**: {len(data.get('active_stations',[]))} Active | {data.get('disk_free_gb')}GB Free | {data.get('version')}")
else:
    c2.warning("No Servers Online")

st.divider()

# 2. NAVIGATION
mode = st.radio("View Mode", ["Fleet Overview", "Station Manager"], horizontal=True)

if mode == "Fleet Overview":
    st.header("🌍 Global Fleet Status")
    
    # Discovery (Cached)
    all_stations = discover_stations()
    
    # Build Table Data
    rows = []
    for s_name in all_stations:
        # We need to fetch config to see assignment
        # Note: This might be slow for 50+ stations. 
        # Ideally we'd cache the config reads too or process in parallel.
        conf = get_station_config(s_name)
        if conf:
            assigned = conf.get('assigned_server', 'Unassigned')
            enabled = conf.get('station_enabled', False)
            
            # Status Logic
            status_icon = "⚪"
            if enabled:
                if assigned in server_ids:
                    # Check if Server actually confirms it
                    if s_name in servers[assigned].get('active_stations', []):
                        status_icon = "🟢 Online" 
                    else:
                        status_icon = "🟡 Syncing..." 
                else:
                    status_icon = "🔴 Offline (Server Missing)"
            else:
                status_icon = "⚫ Disabled"

            rows.append({
                "Station": s_name,
                "Status": status_icon,
                "Assigned Server": assigned,
                "Enabled": "Yes" if enabled else "No"
            })
            
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    if st.button("Refresh Fleet Data"):
        st.cache_data.clear()
        st.rerun()

elif mode == "Station Manager":
    all_stations = discover_stations()
    selected = st.selectbox("Select Station", all_stations)
    
    if selected:
        config = get_station_config(selected)
        if config:
            st.markdown(f"## 🔧 Managing: {selected}")
            
            # --- STRICT LOCK ASSIGNMENT ---
            curr_assign = config.get("assigned_server", "Unassigned")
            
            # Logic: If assigned to a valid server, you can only see THAT server or 'Unassigned'
            # You cannot jump from Server A to Server B directly.
            
            assign_options = ["Unassigned"]
            
            if curr_assign != "Unassigned":
                # Strict Mode: Only current server and unassigned
                assign_options.append(curr_assign)
                locked = True
                help_text = "⚠️ You must Unassign this station before moving it to another server."
            else:
                # Free Mode: Unassigned + All Online Servers
                assign_options.extend(server_ids)
                locked = False
                help_text = "Select a server to activate."

            # UI Controls
            col1, col2 = st.columns(2)
            with col1:
                new_enabled = st.toggle("Station Processing Enabled", value=config.get("station_enabled", True))
            
            with col2:
                # Handle case where current assignment is offline/unknown (force add to list)
                if curr_assign not in assign_options:
                    assign_options.append(curr_assign)
                    
                new_assign = st.selectbox(
                    "Assigned Server", 
                    options=assign_options,
                    index=assign_options.index(curr_assign),
                    help=help_text
                )
                if locked:
                    st.caption("🔒 Locked to current server. Select 'Unassigned' to release.")

            # Save Block
            if new_enabled != config.get("station_enabled") or new_assign != curr_assign:
                config['station_enabled'] = new_enabled
                config['assigned_server'] = new_assign
                save_config(selected, config)
                st.success("Configuration Updated! Server will sync in ~60s.")
                st.cache_data.clear() # Clear cache so Overview updates
                time.sleep(1)
                st.rerun()

            # --- ASSETS & PROFILES (Existing Logic) ---
            st.divider()
            with st.expander("⚙️ Advanced Configuration (Profiles & Actions)"):
                 # (This matches your previous logic, kept simple for now)
                 st.json(config.get('active_profile'))
                 st.warning("Please use the previous tabs for full detailed editing (omitted here for brevity).")