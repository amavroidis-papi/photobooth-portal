import streamlit as st
import dropbox
import json
import pandas as pd
import io
import os
import time

# --- CONFIGURATION ---
# Prioritize Refresh Token Flow for Permanent Access
DROPBOX_APP_KEY = os.environ.get("DROPBOX_APP_KEY")
DROPBOX_APP_SECRET = os.environ.get("DROPBOX_APP_SECRET")
DROPBOX_REFRESH_TOKEN = os.environ.get("DROPBOX_REFRESH_TOKEN")
DROPBOX_TOKEN = os.environ.get("DROPBOX_TOKEN") # Fallback legacy token

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
    if DROPBOX_APP_KEY and DROPBOX_APP_SECRET and DROPBOX_REFRESH_TOKEN:
        # AUTOMATIC REFRESH FLOW (Permanent)
        dbx = dropbox.Dropbox(
            app_key=DROPBOX_APP_KEY,
            app_secret=DROPBOX_APP_SECRET,
            oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
        )
    elif DROPBOX_TOKEN:
        # LEGACY FLOW (Temporary/Dev)
        dbx = dropbox.Dropbox(DROPBOX_TOKEN)
    else:
        st.error("❌ Missing Dropbox Credentials! Please set DROPBOX_APP_KEY, DROPBOX_APP_SECRET, and DROPBOX_REFRESH_TOKEN in Heroku Config Vars.")
        st.stop()
        
    # REMOVED: dbx.users_get_current_account() 
    # This check caused the "missing_scope" error. 
    # We proceed assuming file permissions (files.content.read/write) are correct.
    
except Exception as e:
    st.error(f"Dropbox Connection Failed: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_fleet_data():
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
    except: return None, path

def save_config(config_data, path):
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_asset(uploaded_file, target_path):
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

fleet_data = get_fleet_data()

# --- 1. DASHBOARD METRICS ---
if fleet_data:
    m1, m2, m3 = st.columns(3)
    total_online = len(fleet_data)
    avg_disk = sum([float(s.get('disk_free_gb', 0)) for s in fleet_data]) / total_online
    m1.metric("Servers Online", total_online)
    m2.metric("Avg Free Disk", f"{avg_disk:.1f} GB")
    m3.metric("Manager Version", fleet_data[0].get('version', 'v33'))

st.divider()

# --- 2. SIDEBAR (DETAILED FLEET HEALTH) ---
st.sidebar.header("📡 Live Fleet Health")
online_server_ids = []
if fleet_data:
    for server in fleet_data:
        with st.sidebar.expander(f"🖥️ Server: {server['server_id']}", expanded=True):
            disk_val = float(server.get('disk_free_gb', 0))
            disk_color = "green" if disk_val > 20 else "orange" if disk_val > 10 else "red"
            st.write(f"**Disk Space:** :{disk_color}[{disk_val} GB Free]")
            st.progress(min(disk_val/100, 1.0))
            active = server.get('active_stations', [])
            st.write(f"**Monitoring:** `{', '.join(active)}`")
            st.caption(f"Last Seen: {server['last_seen']}")
    online_server_ids = sorted(list(set([s['server_id'] for s in fleet_data])))
else:
    st.sidebar.warning("No servers online.")

# --- 3. STATION MANAGER ---
st.sidebar.divider()
st.sidebar.header("🎮 Station Manager")
selected_station = st.sidebar.selectbox("Select Station to Configure", KNOWN_STATIONS)

if selected_station:
    st.header(f"🔧 Managing: {selected_station}")
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"Config file missing for {selected_station}.")
    else:
        # MASTER ASSIGNMENT
        col_sw, col_assign, col_status = st.columns([2, 3, 2])
        with col_sw:
            is_enabled = config.get("station_enabled", True)
            new_enabled = st.toggle("Station Processing ON/OFF", value=is_enabled)
        with col_assign:
            curr_assign = config.get("assigned_server", "Unassigned")
            assign_options = ["Unassigned"] + sorted(list(set(online_server_ids + [curr_assign])))
            new_assign = st.selectbox("Assign to Manager", assign_options, index=assign_options.index(curr_assign) if curr_assign in assign_options else 0)
        with col_status:
            if new_enabled: st.success("🟢 Active")
            else: st.error("🔴 Disabled")

        if new_enabled != is_enabled or new_assign != curr_assign:
            config["station_enabled"] = new_enabled
            config["assigned_server"] = new_assign
            save_config(config, config_path)
            st.rerun()

        st.divider()

        # SETTINGS TABS
        tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets (Templates)", "🎬 Profiles & Actions"])
        
        with tab1:
            c1, c2 = st.columns(2)
            with c1:
                curr_bg = config['settings'].get('remove_background', False)
                new_bg = st.toggle("Remove Background (API)", value=curr_bg)
                
                curr_key = config['settings'].get('remove_bg_api_key', '')
                new_key = st.text_input("API Key", value=curr_key, type="password")

                curr_temp = config['settings'].get('temperature', 0)
                new_temp = st.slider("Color Temperature", -100, 100, curr_temp)

            with c2:
                modes = ["auto", "force_portrait", "force_landscape"]
                curr_mode = config['settings'].get('orientation_mode', 'auto')
                new_mode = st.selectbox("Orientation Mode", modes, index=modes.index(curr_mode))

            if st.button("Save Global Settings"):
                config['settings'].update({
                    "remove_background": new_bg,
                    "remove_bg_api_key": new_key,
                    "temperature": new_temp,
                    "orientation_mode": new_mode
                })
                save_config(config, config_path)
                st.success("Settings Saved!")

        with tab2:
            st.subheader("Upload Templates")
            st.caption(f"Path: /{selected_station}/templates/")
            ca, cb = st.columns(2)
            with ca:
                bg = st.file_uploader("Upload Background (.jpg)", type=['jpg', 'jpeg'])
                if bg and st.button("Save BG"):
                    upload_asset(bg, f"/{selected_station}/templates/background.jpg")
                    st.success("Uploaded!")
            with cb:
                ol = st.file_uploader("Upload Overlay (.png)", type=['png'])
                if ol and st.button("Save Overlay"):
                    upload_asset(ol, f"/{selected_station}/templates/overlay.png")
                    st.success("Uploaded!")

        with tab3:
            available_sets = get_available_actions()
            if not available_sets: available_sets = ["Default"]

            st.markdown("### 🎬 Action Profiles")
            col_p, col_l = st.columns(2)
            with col_p:
                st.caption("Portrait")
                cur_p_set = config['active_profile']['portrait'].get('action_set', '')
                cur_p_name = config['active_profile']['portrait'].get('action_name', '')
                new_p_set = st.selectbox("Action File (Portrait)", available_sets, index=available_sets.index(cur_p_set) if cur_p_set in available_sets else 0)
                new_p_name = st.text_input("Action Name (Portrait)", cur_p_name)

            with col_l:
                st.caption("Landscape")
                cur_l_set = config['active_profile']['landscape'].get('action_set', '')
                cur_l_name = config['active_profile']['landscape'].get('action_name', '')
                new_l_set = st.selectbox("Action File (Landscape)", available_sets, index=available_sets.index(cur_l_set) if cur_l_set in available_sets else 0)
                new_l_name = st.text_input("Action Name (Landscape)", cur_l_name)

            if st.button("Update Profiles"):
                config['active_profile']['portrait'].update({"action_set": new_p_set, "action_name": new_p_name})
                config['active_profile']['landscape'].update({"action_set": new_l_set, "action_name": new_l_name})
                save_config(config, config_path)
                st.success("Actions Updated!")

            st.divider()
            st.subheader("Subfolder Management")
            cur_sub = config.get('subfolder_action_set', 'Event_Subfolders')
            new_sub = st.selectbox("Subfolder Action Set", available_sets, index=available_sets.index(cur_sub) if cur_sub in available_sets else 0)
            if new_sub != cur_sub:
                if st.button("Save Subfolder Set"):
                    config['subfolder_action_set'] = new_sub
                    save_config(config, config_path)
                    st.success("Subfolders Updated!")