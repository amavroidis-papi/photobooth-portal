import streamlit as st
import dropbox
import json
import pandas as pd
from datetime import datetime
import io
import os

# --- CONFIGURATION ---
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN")
GLOBAL_ASSETS = "/_Global_Assets"
ACTIONS_FOLDER = f"{GLOBAL_ASSETS}/Actions"
HEALTH_FOLDER = f"{GLOBAL_ASSETS}/_Server_Health"

# YOUR STATION LIST
KNOWN_STATIONS = [
    "DC Standard", "Dell Laptop", "Dell XPS", "DellNew1", "DellNew2", 
    "DellNew3", "DellNew4", "HP_Envy", "HP1", "HP2", "HP3", "HP4", 
    "Laptop 3", "Lenovo 1", "Lenovo 2", "Mini1BackUp", "Mini1Standard", 
    "Mini2BackUp", "Mini2Standard", "Mini3", "Mini3BackUp", 
    "Mini4Standard", "TXStandard"
]

# --- CONNECT TO DROPBOX ---
try:
    if not DROPBOX_TOKEN:
        st.error("DROPBOX_TOKEN is missing in Heroku Config Vars!")
        st.stop()
    dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    dbx.users_get_current_account() 
except Exception as e:
    st.error(f"Failed to connect to Dropbox: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_fleet_status():
    """Reads all JSON files in _Server_Health to find active stations."""
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

def get_available_actions():
    """Lists all .atn files in the Global Actions folder."""
    actions = []
    try:
        res = dbx.files_list_folder(ACTIONS_FOLDER)
        for entry in res.entries:
            if entry.name.endswith('.atn'):
                actions.append(entry.name.replace(".atn", ""))
    except: pass
    return sorted(actions)

def load_config(station_id):
    """Downloads config.json for a specific station."""
    path = f"/{station_id}/config.json"
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content)), path
    except:
        return None, path

def create_default_config(station_id):
    """Creates a fresh config file if one is missing."""
    default_data = {
        "server_id": "Unknown",
        "station_id": station_id,
        "settings": {
            "remove_background": False,
            "remove_bg_api_key": "",
            "orientation_mode": "auto",
            "temperature": 0
        },
        "active_profile": {
            "portrait": {"action_set": "Global_Actions", "action_name": "Default_Portrait"},
            "landscape": {"action_set": "Global_Actions", "action_name": "Default_Landscape"}
        },
        "subfolder_action_set": "Event_Subfolders"
    }
    path = f"/{station_id}/config.json"
    save_config(default_data, path)
    return default_data, path

def save_config(config_data, path):
    """Uploads the modified config back to Dropbox."""
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_asset(uploaded_file, target_path):
    """Uploads a file to a specific path."""
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command Center", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

# SIDEBAR: FLEET STATUS (Real-time)
st.sidebar.header("📡 Live Fleet Status")
servers = get_fleet_status()

if servers:
    df = pd.DataFrame(servers)
    st.sidebar.dataframe(
        df[['server_id', 'watching_station', 'status']], 
        hide_index=True, 
        use_container_width=True
    )
else:
    st.sidebar.info("No servers currently online.")

st.sidebar.divider()

# SIDEBAR: STATION SELECTOR
st.sidebar.header("🎮 Station Manager")
selected_station = st.sidebar.selectbox("Select Station to Configure", KNOWN_STATIONS)

if selected_station:
    st.header(f"🔧 Managing Station: {selected_station}")
    
    # Try Load Config
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"No config.json found for {selected_station}.")
        if st.button(f"Initialize {selected_station} Now"):
            config, config_path = create_default_config(selected_station)
            st.rerun()
    
    if config:
        # --- TABS ---
        tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles & Actions"])
        
        # TAB 1: SETTINGS
        with tab1:
            st.subheader("Live Controls")
            col1, col2 = st.columns(2)
            
            with col1:
                current_bg = config['settings'].get('remove_background', False)
                new_bg = st.toggle("Remove Background (API)", value=current_bg)
                if new_bg != current_bg:
                    config['settings']['remove_background'] = new_bg
                    save_config(config, config_path)
                    st.toast("Settings Updated!")

                current_temp = config['settings'].get('temperature', 0)
                new_temp = st.slider("Color Temperature", -100, 100, current_temp)
                if new_temp != current_temp:
                    config['settings']['temperature'] = new_temp
                    save_config(config, config_path)
                    st.toast("Temperature Updated!")

            with col2:
                modes = ["auto", "force_portrait", "force_landscape"]
                curr_mode = config['settings'].get('orientation_mode', 'auto')
                new_mode = st.selectbox("Orientation Mode", modes, index=modes.index(curr_mode))
                if new_mode != curr_mode:
                    config['settings']['orientation_mode'] = new_mode
                    save_config(config, config_path)
                    st.toast("Orientation Updated!")

        # TAB 2: ASSETS
        with tab2:
            st.subheader("Asset Manager")
            st.info(f"Target: /{selected_station}/templates/")
            
            profile_suffix = st.text_input("Sub-Profile Suffix (e.g., 001)", placeholder="e.g., 001")
            
            c1, c2 = st.columns(2)
            with c1:
                bg_file = st.file_uploader("Upload New Background", type=['jpg', 'jpeg'])
                if bg_file and st.button("Update Background"):
                    fname = f"background{profile_suffix}.jpg" if profile_suffix else "background.jpg"
                    path = f"/{selected_station}/templates/{fname}"
                    upload_asset(bg_file, path)
                    st.success(f"Uploaded {fname}")

            with c2:
                ol_file = st.file_uploader("Upload New Overlay", type=['png'])
                if ol_file and st.button("Update Overlay"):
                    fname = f"overlay{profile_suffix}.png" if profile_suffix else "overlay.png"
                    path = f"/{selected_station}/templates/{fname}"
                    upload_asset(ol_file, path)
                    st.success(f"Uploaded {fname}")

        # TAB 3: PROFILES & ACTIONS
        with tab3:
            st.subheader("Select Active Photoshop Action")
            
            available_actions = get_available_actions()
            if not available_actions:
                st.warning("No actions found in /_Global_Assets/Actions")
                available_actions = ["Default"]

            col_a, col_b = st.columns(2)
            
            with col_a:
                st.markdown("#### Portrait Mode")
                curr_port_action = config['active_profile']['portrait']['action_name']
                idx = available_actions.index(curr_port_action) if curr_port_action in available_actions else 0
                new_port_action = st.selectbox("Select Portrait Action", available_actions, index=idx, key="port_sel")
                
                if new_port_action != curr_port_action:
                    config['active_profile']['portrait']['action_name'] = new_port_action
                    if st.button("Save Portrait Change"):
                        save_config(config, config_path)
                        st.success("Portrait Action Updated")

            with col_b:
                st.markdown("#### Landscape Mode")
                curr_land_action = config['active_profile']['landscape']['action_name']
                idx_l = available_actions.index(curr_land_action) if curr_land_action in available_actions else 0
                new_land_action = st.selectbox("Select Landscape Action", available_actions, index=idx_l, key="land_sel")
                
                if new_land_action != curr_land_action:
                    config['active_profile']['landscape']['action_name'] = new_land_action
                    if st.button("Save Landscape Change"):
                        save_config(config, config_path)
                        st.success("Landscape Action Updated")

            st.divider()
            
            st.subheader("Upload New Action File (.atn)")
            new_atn = st.file_uploader("Upload .atn file", type=['atn'])
            if new_atn and st.button("Upload to Global Assets"):
                target = f"{ACTIONS_FOLDER}/{new_atn.name}"
                upload_asset(new_atn, target)
                st.success(f"Uploaded {new_atn.name}! Refresh page to see it in the list.")