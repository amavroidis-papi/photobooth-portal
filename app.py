import streamlit as st
import dropbox
import json
import io
import os
import pandas as pd
import time
from datetime import datetime

# --- CONFIGURATION (ENV VARS) ---
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")

# FOLDER PATHS
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
@st.cache_resource
def get_dropbox_client():
    try:
        if DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN:
            return dropbox.Dropbox(
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
            )
        else:
            return None
    except Exception as e:
        st.error(f"Dropbox Connection Error: {e}")
        return None

dbx = get_dropbox_client()

# --- DATA FUNCTIONS ---

def get_server_health():
    """Reads the v52+ Server Health Reports."""
    servers = {}
    if not dbx: return {}
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

def get_global_actions():
    """Lists .atn files in the global Actions folder."""
    files = []
    if not dbx: return []
    try:
        res = dbx.files_list_folder(ACTIONS_FOLDER)
        for entry in res.entries:
            if isinstance(entry, dropbox.files.FileMetadata) and entry.name.endswith('.atn'):
                files.append(entry.name)
    except: pass
    return sorted(files)

def get_station_config(station_id):
    if not dbx: return None
    try:
        _, res = dbx.files_download(f"/{station_id}/config.json")
        return json.load(io.BytesIO(res.content))
    except: return None

def save_config(station_id, config_data):
    if not dbx: return False
    path = f"/{station_id}/config.json"
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_station_asset(uploaded_file, dest_path):
    """Direct upload to station template folder."""
    if not dbx: return False
    try:
        dbx.files_upload(uploaded_file.getvalue(), dest_path, mode=dropbox.files.WriteMode.overwrite)
        return True
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return False

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command v2.1", layout="wide", page_icon="📷")

if not dbx:
    st.error("⚠️ Dropbox Credentials Missing.")
    st.stop()

# --- SIDEBAR ---
st.sidebar.title("📷 Command v2.1")
view_mode = st.sidebar.radio("Navigation", ["Fleet Dashboard", "Station Manager"])
st.sidebar.divider()
st.sidebar.caption(f"Connected to Dropbox")

# --- PAGE 1: FLEET DASHBOARD ---
if view_mode == "Fleet Dashboard":
    st.title("🌍 Fleet Dashboard")
    
    servers = get_server_health()
    if not servers:
        st.warning("No Server Health Reports found.")
    
    for sid, data in servers.items():
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 1, 1, 2])
            c1.subheader(f"🖥️ Server: {sid}")
            c2.metric("Status", data.get('status', 'Unknown'))
            c3.metric("Free Disk", f"{data.get('disk_free_gb', 0)} GB")
            c4.caption(f"Last Seen: {data.get('last_seen')}\nVersion: {data.get('version')}")
            
            active = data.get('active_stations', [])
            standby = data.get('standby_stations', [])
            ghosts = data.get('unconfigured_stations', [])
            
            t1, t2, t3 = st.tabs([f"🟢 Active ({len(active)})", f"🟡 Standby ({len(standby)})", f"🔴 Unconfigured ({len(ghosts)})"])
            with t1: st.success(", ".join(active)) if active else st.caption("None")
            with t2: st.warning(", ".join(standby)) if standby else st.caption("None")
            with t3: st.error(", ".join(ghosts)) if ghosts else st.caption("None")
        st.divider()

# --- PAGE 2: STATION MANAGER ---
elif view_mode == "Station Manager":
    st.title("🔧 Station Manager")
    
    selected_station = st.selectbox("Select Target Station", KNOWN_STATIONS)
    
    if selected_station:
        config = get_station_config(selected_station)
        
        if not config:
            st.error(f"Config.json not found for {selected_station}.")
            if st.button("Initialize Default Config"):
                default_conf = {
                    "station_enabled": False,
                    "assigned_server": "71946",
                    "settings": {"temperature": 0, "remove_background": False},
                    "active_profile": {
                        "portrait": {"action_set": "Photobooth_Actions", "action_name": "Portrait"},
                        "landscape": {"action_set": "Photobooth_Actions", "action_name": "Landscape"}
                    },
                    "subfolder_action_set": "Event_Subfolders"
                }
                save_config(selected_station, default_conf)
                st.rerun()
            st.stop()

        # MANAGEMENT TABS
        tab_core, tab_assets, tab_sub, tab_actions = st.tabs(["⚙️ Core", "📂 Main Assets", "🗂️ Subfolder Assets", "🎬 Actions"])
        
        # --- TAB A: CORE SETTINGS ---
        with tab_core:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Status")
                is_enabled = config.get("station_enabled", False)
                new_enabled = st.toggle("Station Enabled", value=is_enabled)
                if new_enabled: st.caption("🟢 Station Active")
                else: st.caption("🔴 Station Disabled")
                
                if new_enabled != is_enabled:
                    config['station_enabled'] = new_enabled
                    save_config(selected_station, config)
                    st.rerun()

            with c2:
                st.subheader("Settings")
                curr_temp = config.get('settings', {}).get('temperature', 0)
                new_temp = st.slider("Temperature", -100, 100, int(curr_temp))
                
                if new_temp != curr_temp:
                    if 'settings' not in config: config['settings'] = {}
                    config['settings']['temperature'] = new_temp
                    if st.button("Save Temperature"):
                        save_config(selected_station, config)
                        st.success("Saved.")
                        
        # --- TAB B: MAIN ASSETS (INCOMING) ---
        with tab_assets:
            st.info(f"Uploading to: `/{selected_station}/templates/`")
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("### 🖼️ Main Overlay")
                st.caption("Target: `overlay.png`")
                up_ol = st.file_uploader("Upload Overlay (.png)", type=['png'], key="main_ol")
                if up_ol and st.button("Upload Main Overlay"):
                    dst = f"/{selected_station}/templates/overlay.png"
                    if upload_station_asset(up_ol, dst): st.success("Uploaded!")

            with c2:
                st.markdown("### 🌄 Main Background")
                st.caption("Target: `background.jpg`")
                up_bg = st.file_uploader("Upload Background (.jpg)", type=['jpg', 'jpeg'], key="main_bg")
                if up_bg and st.button("Upload Main BG"):
                    dst = f"/{selected_station}/templates/background.jpg"
                    if upload_station_asset(up_bg, dst): st.success("Uploaded!")

        # --- TAB C: SUBFOLDER ASSETS ---
        with tab_sub:
            st.markdown("### 📂 Subfolder Assets (001-099)")
            sub_id = st.selectbox("Select Subfolder ID", [f"{i:03d}" for i in range(1, 100)])
            
            target_ol = f"overlay{sub_id}.png"
            target_bg = f"background{sub_id}.jpg"
            
            st.info(f"Target: `/{selected_station}/templates/{target_bg}` (and overlay)")
            
            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown(f"### 🖼️ Overlay ({sub_id})")
                up_ol_sub = st.file_uploader(f"Upload {target_ol}", type=['png'], key="sub_ol")
                if up_ol_sub and st.button(f"Upload Overlay {sub_id}"):
                    dst = f"/{selected_station}/templates/{target_ol}"
                    if upload_station_asset(up_ol_sub, dst): st.success(f"Uploaded {target_ol}!")

            with c2:
                st.markdown(f"### 🌄 Background ({sub_id})")
                up_bg_sub = st.file_uploader(f"Upload {target_bg}", type=['jpg', 'jpeg'], key="sub_bg")
                if up_bg_sub and st.button(f"Upload BG {sub_id}"):
                    dst = f"/{selected_station}/templates/{target_bg}"
                    if upload_station_asset(up_bg_sub, dst): st.success(f"Uploaded {target_bg}!")

        # --- TAB D: ACTIONS MANAGER ---
        with tab_actions:
            st.subheader("Global Action Configuration")
            available_sets = get_global_actions()
            # Clean names for display
            clean_sets = [f.replace(".atn", "") for f in available_sets]
            if not clean_sets: clean_sets = ["Photobooth_Actions"]

            c1, c2 = st.columns(2)
            
            with c1:
                st.markdown("**Portrait Profile**")
                p_conf = config.get('active_profile', {}).get('portrait', {})
                cur_p_set = p_conf.get('action_set', 'Photobooth_Actions')
                cur_p_name = p_conf.get('action_name', 'Portrait')
                
                idx_p = clean_sets.index(cur_p_set) if cur_p_set in clean_sets else 0
                new_p_set = st.selectbox("Action Set", clean_sets, index=idx_p, key="p_set")
                new_p_name = st.text_input("Action Name", cur_p_name, key="p_name")

            with c2:
                st.markdown("**Landscape Profile**")
                l_conf = config.get('active_profile', {}).get('landscape', {})
                cur_l_set = l_conf.get('action_set', 'Photobooth_Actions')
                cur_l_name = l_conf.get('action_name', 'Landscape')
                
                idx_l = clean_sets.index(cur_l_set) if cur_l_set in clean_sets else 0
                new_l_set = st.selectbox("Action Set", clean_sets, index=idx_l, key="l_set")
                new_l_name = st.text_input("Action Name", cur_l_name, key="l_name")

            st.markdown("---")
            if st.button("Save Actions"):
                if 'active_profile' not in config: config['active_profile'] = {}
                config['active_profile']['portrait'] = {"action_set": new_p_set, "action_name": new_p_name}
                config['active_profile']['landscape'] = {"action_set": new_l_set, "action_name": new_l_name}
                save_config(selected_station, config)
                st.success("Actions Updated!")