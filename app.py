import streamlit as st
import dropbox
import json
import pandas as pd
import io
import os
import time

# --- CONFIGURATION ---
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")
GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# MASTER STATION LIST
KNOWN_STATIONS = sorted([
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2", 
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4", 
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard", 
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp", 
    "Mini4Standard", "TXStandard"
])

# --- CONNECT TO DROPBOX ---
try:
    if not DROPBOX_TOKEN:
        st.error("DROPBOX_TOKEN is missing!")
        st.stop()
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    dbx.users_get_current_account() 
except Exception as e:
    st.error(f"Dropbox Connection Failed: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_fleet_data():
    """Reads health files to see who is ONLINE."""
    servers = []
    try:
        res = dbx.files_list_folder(HEALTH_FOLDER)
        for entry in res.entries:
            if entry.name.endswith('.json'):
                try:
                    _, res = dbx.files_download(entry.path_lower)
                    data = json.load(io.BytesIO(res.content))
                    servers.append(data)
                except: pass
    except: pass
    return servers

def load_config(station_id):
    path = f"/{station_id}/config.json"
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content)), path
    except:
        return None, path

def save_config(config_data, path):
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

# --- 1. TOP LEVEL METRICS (NEW) ---
fleet_data = get_fleet_data()
if fleet_data:
    m1, m2, m3 = st.columns(3)
    total_online = len(fleet_data)
    
    # Calculate total disk health across fleet
    avg_disk = sum([float(s.get('disk_free_gb', 0)) for s in fleet_data]) / total_online
    
    m1.metric("Servers Online", total_online)
    m2.metric("Avg Free Disk", f"{avg_disk:.1f} GB")
    m3.metric("Fleet Version", fleet_data[0].get('version', 'v30+'))

st.divider()

# --- 2. SIDEBAR - DETAILED FLEET VIEW ---
st.sidebar.header("📡 Live Fleet Health")

if fleet_data:
    for server in fleet_data:
        with st.sidebar.expander(f"🖥️ Server: {server['server_id']}", expanded=True):
            # Disk Health Progress Bar
            disk_val = float(server.get('disk_free_gb', 0))
            disk_color = "green" if disk_val > 20 else "orange" if disk_val > 10 else "red"
            st.write(f"**Disk Space:** :{disk_color}[{disk_val} GB Free]")
            st.progress(min(disk_val/100, 1.0))
            
            # Active Stations List (New v33 Logic)
            active = server.get('active_stations', [server.get('watching_station', 'Unknown')])
            st.write(f"**Monitoring:** `{', '.join(active)}` Status: :green[ONLINE]")
            st.caption(f"Last Ping: {server['last_seen']}")

    online_server_ids = sorted(list(set([s['server_id'] for s in fleet_data])))
    filter_server = st.sidebar.selectbox("Filter Manager by Server", ["All Servers"] + online_server_ids)
else:
    st.sidebar.warning("No servers online.")
    filter_server = "All Servers"

# --- 3. STATION MANAGER ---
st.sidebar.divider()
st.sidebar.header("🎮 Station Manager")

# Logic to show which stations can be edited
if filter_server != "All Servers":
    # Show only stations currently being managed by the selected server
    server_info = next(s for s in fleet_data if s['server_id'] == filter_server)
    display_list = server_info.get('active_stations', KNOWN_STATIONS)
else:
    display_list = KNOWN_STATIONS

selected_station = st.sidebar.selectbox("Select Station to Configure", display_list)

if selected_station:
    st.header(f"🔧 Configuration: {selected_station}")
    config, config_path = load_config(selected_station)
    
    if config:
        # --- MASTER SWITCH & ASSIGNMENT ---
        col_sw, col_assign, col_status = st.columns([2, 3, 2])
        
        with col_sw:
            is_enabled = config.get("station_enabled", True)
            new_enabled = st.toggle("Enable Station", value=is_enabled)
        
        with col_assign:
            curr_assign = config.get("assigned_server", "Unassigned")
            assign_options = ["Unassigned"] + sorted(list(set(online_server_ids + [curr_assign])))
            new_assign = st.selectbox("Assign to Mac Mini", assign_options, 
                                     index=assign_options.index(curr_assign) if curr_assign in assign_options else 0)

        with col_status:
            if new_enabled and new_assign in online_server_ids:
                st.success("🟢 Active & Processing")
            elif not new_enabled:
                st.error("🔴 Station Disabled")
            else:
                st.warning("🟡 Waiting for Server")
        
        # Auto-save changes
        if new_enabled != is_enabled or new_assign != curr_assign:
            config["station_enabled"] = new_enabled
            config["assigned_server"] = new_assign
            save_config(config, config_path)
            st.rerun()

        # The rest of your existing Settings/Assets/Actions tabs go here...
        # (Tabs 1, 2, and 3 from your original app.py)