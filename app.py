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
def get_fleet_data():
    """Reads health files to get Server IDs and their Stations."""
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
    path = f"/{station_id}/config.json"
    try:
        _, res = dbx.files_download(path)
        return json.load(io.BytesIO(res.content)), path
    except:
        return None, path

def create_default_config(station_id, server_id):
    default_data = {
        "server_id": server_id,
        "station_id": station_id,
        "station_enabled": True, # NEW: Master Switch
        "settings": {
            "remove_background": False,
            "remove_bg_api_key": "",
            "orientation_mode": "auto",
            "temperature": 0
        },
        "active_profile": {
            "portrait": {"action_set": "Global_Actions", "action_name": "Portrait"},
            "landscape": {"action_set": "Global_Actions", "action_name": "Landscape"}
        },
        "subfolder_action_set": "Event_Subfolders"
    }
    path = f"/{station_id}/config.json"
    save_config(default_data, path)
    return default_data, path

def save_config(config_data, path):
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_asset(uploaded_file, target_path):
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command Center", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

# 1. SERVER SELECTION (The Filter)
st.sidebar.header("📡 Server Filter")
fleet_data = get_fleet_data()

if not fleet_data:
    st.sidebar.warning("No online servers found.")
    st.stop()

# Get unique Server IDs
server_ids = sorted(list(set([s['server_id'] for s in fleet_data])))
selected_server = st.sidebar.selectbox("Select Server ID", server_ids)

# Filter Stations for this Server
available_stations = [s['watching_station'] for s in fleet_data if s['server_id'] == selected_server]
available_stations.sort()

st.sidebar.divider()

# 2. STATION SELECTION
st.sidebar.header(f"🎮 Stations on {selected_server}")
selected_station = st.sidebar.selectbox("Select Station", available_stations)

if selected_station:
    st.header(f"🔧 Managing: {selected_station}")
    
    # Load or Init Config
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning("Config missing.")
        if st.button("Initialize Config"):
            config, config_path = create_default_config(selected_station, selected_server)
            st.rerun()
            
    if config:
        # --- MASTER SWITCH ---
        is_enabled = config.get("station_enabled", True)
        col_switch, col_status = st.columns([1, 4])
        with col_switch:
            new_enabled = st.toggle("Station Active", value=is_enabled)
        with col_status:
            if new_enabled:
                st.success("🟢 Monitoring is ON")
            else:
                st.error("🔴 Monitoring is PAUSED")
        
        if new_enabled != is_enabled:
            config["station_enabled"] = new_enabled
            save_config(config, config_path)
            st.rerun()

        if is_enabled:
            tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles & Actions"])
            
            # --- TAB 1: SETTINGS ---
            with tab1:
                st.subheader("Global Settings")
                c1, c2 = st.columns(2)
                with c1:
                    # BG Removal
                    curr_bg = config['settings'].get('remove_background', False)
                    new_bg = st.toggle("Remove Background (API)", value=curr_bg)
                    if new_bg != curr_bg:
                        config['settings']['remove_background'] = new_bg
                        save_config(config, config_path)
                        st.toast("Updated BG Settings")
                    
                    # Temp
                    curr_temp = config['settings'].get('temperature', 0)
                    new_temp = st.slider("Temperature", -100, 100, curr_temp)
                    if new_temp != curr_temp:
                        config['settings']['temperature'] = new_temp
                        save_config(config, config_path)
                        st.toast("Updated Temp")

                with c2:
                    # Orientation
                    modes = ["auto", "force_portrait", "force_landscape"]
                    curr_mode = config['settings'].get('orientation_mode', 'auto')
                    new_mode = st.selectbox("Orientation", modes, index=modes.index(curr_mode))
                    if new_mode != curr_mode:
                        config['settings']['orientation_mode'] = new_mode
                        save_config(config, config_path)
                        st.toast("Updated Orientation")

            # --- TAB 2: ASSETS ---
            with tab2:
                st.subheader("Upload Assets")
                st.caption(f"Target: /{selected_station}/templates/")
                suffix = st.text_input("Sub-Profile (e.g., 001)", placeholder="Leave empty for default")
                
                c1, c2 = st.columns(2)
                with c1:
                    bg = st.file_uploader("Background (.jpg)", type=['jpg', 'jpeg'])
                    if bg and st.button("Upload BG"):
                        name = f"background{suffix}.jpg" if suffix else "background.jpg"
                        upload_asset(bg, f"/{selected_station}/templates/{name}")
                        st.success(f"Saved {name}")
                with c2:
                    ol = st.file_uploader("Overlay (.png)", type=['png'])
                    if ol and st.button("Upload Overlay"):
                        name = f"overlay{suffix}.png" if suffix else "overlay.png"
                        upload_asset(ol, f"/{selected_station}/templates/{name}")
                        st.success(f"Saved {name}")

            # --- TAB 3: ACTIONS (SPLIT) ---
            with tab3:
                available_sets = get_available_actions()
                if not available_sets: available_sets = ["Default"]

                # A. ROOT FOLDER ACTIONS
                st.markdown("### 1. Root Folder Actions (Single Photos)")
                st.caption(f"Photos in /{selected_station}/incoming/")
                
                col_p, col_l = st.columns(2)
                
                # Portrait Logic
                with col_p:
                    st.markdown("**Portrait Mode**")
                    cur_p_set = config['active_profile']['portrait'].get('action_set', '')
                    cur_p_name = config['active_profile']['portrait'].get('action_name', 'Portrait')
                    
                    # Set Selector
                    idx_p = available_sets.index(cur_p_set) if cur_p_set in available_sets else 0
                    new_p_set = st.selectbox("Action File (.atn)", available_sets, index=idx_p, key="p_set")
                    # Name Input
                    new_p_name = st.text_input("Action Name (Inside Photoshop)", cur_p_name, key="p_name")

                    if new_p_set != cur_p_set or new_p_name != cur_p_name:
                        if st.button("Save Portrait Config"):
                            config['active_profile']['portrait']['action_set'] = new_p_set
                            config['active_profile']['portrait']['action_name'] = new_p_name
                            save_config(config, config_path)
                            st.success("Saved!")

                # Landscape Logic
                with col_l:
                    st.markdown("**Landscape Mode**")
                    cur_l_set = config['active_profile']['landscape'].get('action_set', '')
                    cur_l_name = config['active_profile']['landscape'].get('action_name', 'Landscape')
                    
                    idx_l = available_sets.index(cur_l_set) if cur_l_set in available_sets else 0
                    new_l_set = st.selectbox("Action File (.atn)", available_sets, index=idx_l, key="l_set")
                    new_l_name = st.text_input("Action Name (Inside Photoshop)", cur_l_name, key="l_name")

                    if new_l_set != cur_l_set or new_l_name != cur_l_name:
                        if st.button("Save Landscape Config"):
                            config['active_profile']['landscape']['action_set'] = new_l_set
                            config['active_profile']['landscape']['action_name'] = new_l_name
                            save_config(config, config_path)
                            st.success("Saved!")

                st.divider()

                # B. SUBFOLDER ACTIONS
                st.markdown("### 2. Event Subfolder Actions (001, 002...)")
                st.caption("Photos in /incoming/001 use actions named HP1001, HP1002 from this set.")
                
                cur_sub_set = config.get('subfolder_action_set', 'Event_Subfolders')
                idx_sub = available_sets.index(cur_sub_set) if cur_sub_set in available_sets else 0
                
                new_sub_set = st.selectbox("Select Action Set for Subfolders", available_sets, index=idx_sub, key="sub_set")
                
                if new_sub_set != cur_sub_set:
                    if st.button("Update Subfolder Set"):
                        config['subfolder_action_set'] = new_sub_set
                        save_config(config, config_path)
                        st.success("Subfolder Set Updated!")

                st.divider()
                
                # C. UPLOADER
                st.subheader("Upload New .atn File")
                up_atn = st.file_uploader("Upload .atn", type=['atn'])
                if up_atn and st.button("Upload Action"):
                    upload_asset(up_atn, f"{ACTIONS_FOLDER}/{up_atn.name}")
                    st.success("Uploaded! Refresh to see in lists.")