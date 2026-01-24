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
except Exception as e:
    st.error(f"Dropbox Connection Failed: {e}")
    st.stop()

# --- HELPER FUNCTIONS ---
def get_fleet_data():
    """Reads health files from Dropbox."""
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
    """Lists .atn files in the Actions folder."""
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
    except: return None, path

def save_config(config_data, path):
    """Uploads updated config.json back to Dropbox."""
    data_str = json.dumps(config_data, indent=2)
    dbx.files_upload(data_str.encode('utf-8'), path, mode=dropbox.files.WriteMode.overwrite)
    return True

def upload_asset(uploaded_file, target_path):
    """Uploads JPG/PNG/ATN files to Dropbox."""
    dbx.files_upload(uploaded_file.getvalue(), target_path, mode=dropbox.files.WriteMode.overwrite)

# --- UI LAYOUT ---
st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

# 1. TOP METRICS (Fleet Health)
fleet_data = get_fleet_data()
if fleet_data:
    m1, m2, m3 = st.columns(3)
    total_online = len(fleet_data)
    # Safely calculate disk space from any server reporting it
    disk_list = [float(s.get('disk_free_gb', 0)) for s in fleet_data if 'disk_free_gb' in s]
    avg_disk = sum(disk_list) / len(disk_list) if disk_list else 0
    
    m1.metric("Servers Online", total_online)
    m2.metric("Avg Free Disk", f"{avg_disk:.1f} GB")
    m3.metric("System Version", fleet_data[0].get('version', 'v30+'))

st.divider()

# 2. SIDEBAR - LIVE STATUS & FILTER
st.sidebar.header("📡 Live Status")
online_server_ids = []
if fleet_data:
    for server in fleet_data:
        with st.sidebar.expander(f"🖥️ Server: {server['server_id']}", expanded=True):
            # Show disk health if available
            if 'disk_free_gb' in server:
                val = float(server['disk_free_gb'])
                color = "green" if val > 15 else "orange" if val > 5 else "red"
                st.write(f"Disk: :{color}[{val} GB Free]")
            
            # Show active stations
            active = server.get('active_stations', [server.get('watching_station', 'Unknown')])
            st.write(f"Monitoring: `{', '.join(active)}`")
            st.caption(f"Last Ping: {server['last_seen']}")
            
    online_server_ids = sorted(list(set([s['server_id'] for s in fleet_data])))
    filter_server = st.sidebar.selectbox("Filter Station List by Server", ["All Stations"] + online_server_ids)
else:
    st.sidebar.warning("No servers online.")
    filter_server = "All Stations"

# 3. STATION SELECTOR
st.sidebar.divider()
st.sidebar.header("🎮 Station Manager")
if filter_server != "All Stations":
    # Show only stations monitored by this specific server
    s_data = next(s for s in fleet_data if s['server_id'] == filter_server)
    display_list = sorted(s_data.get('active_stations', [s_data.get('watching_station')]))
else:
    display_list = KNOWN_STATIONS

selected_station = st.sidebar.selectbox("Select Station to Configure", display_list)

# 4. CONFIGURATION PANEL
if selected_station:
    st.header(f"🔧 Configuration: {selected_station}")
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"Config missing for {selected_station}. Run supervisor to auto-generate.")
    else:
        # --- MASTER SWITCH & ASSIGNMENT ---
        col_sw, col_assign, col_status = st.columns([2, 3, 2])
        
        with col_sw:
            is_enabled = config.get("station_enabled", True)
            new_enabled = st.toggle("Processing Status", value=is_enabled, key="master_sw")
        
        with col_assign:
            curr_assign = config.get("assigned_server", "Unassigned")
            assign_options = ["Unassigned"] + sorted(list(set(online_server_ids + [curr_assign])))
            new_assign = st.selectbox("Assign to Mac Mini", assign_options, index=assign_options.index(curr_assign) if curr_assign in assign_options else 0)

        with col_status:
            if new_enabled: st.success("🟢 Station Enabled")
            else: st.error("🔴 Station Disabled")
        
        # Save Assignment Changes immediately
        if new_enabled != is_enabled or new_assign != curr_assign:
            config["station_enabled"] = new_enabled
            config["assigned_server"] = new_assign
            save_config(config, config_path)
            st.rerun()

        st.divider()

        # --- TABS FOR SETTINGS ---
        tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles & Actions"])

        with tab1:
            c1, c2 = st.columns(2)
            with c1:
                # Background Removal
                curr_bg = config['settings'].get('remove_background', False)
                new_bg = st.toggle("Remove Background (API)", value=curr_bg)
                
                curr_key = config['settings'].get('remove_bg_api_key', '')
                new_key = st.text_input("API Key", value=curr_key, type="password")

                # Temperature
                curr_temp = config['settings'].get('temperature', 0)
                new_temp = st.slider("Color Temperature", -100, 100, curr_temp)

            with c2:
                # Orientation
                modes = ["auto", "force_portrait", "force_landscape"]
                curr_mode = config['settings'].get('orientation_mode', 'auto')
                new_mode = st.selectbox("Orientation Mode", modes, index=modes.index(curr_mode))

            if st.button("Save Global Settings", type="primary"):
                config['settings'].update({
                    "remove_background": new_bg,
                    "remove_bg_api_key": new_key,
                    "temperature": new_temp,
                    "orientation_mode": new_mode
                })
                if save_config(config, config_path):
                    st.success("Config Updated!")
                    time.sleep(1)
                    st.rerun()

        with tab2:
            st.subheader("Upload Templates")
            st.caption(f"Saving to: /{selected_station}/templates/")
            ca, cb = st.columns(2)
            with ca:
                bg_up = st.file_uploader("Upload Background (.jpg)", type=['jpg', 'jpeg'])
                if bg_up and st.button("Save Background"):
                    upload_asset(bg_up, f"/{selected_station}/templates/background.jpg")
                    st.success("Background Saved!")
            with cb:
                ol_up = st.file_uploader("Upload Overlay (.png)", type=['png'])
                if ol_up and st.button("Save Overlay"):
                    upload_asset(ol_up, f"/{selected_station}/templates/overlay.png")
                    st.success("Overlay Saved!")

        with tab3:
            available_sets = get_available_actions()
            if not available_sets: available_sets = ["Default"]

            st.markdown("### Action Profiles (Droplets)")
            cp, cl = st.columns(2)
            with cp:
                st.caption("Portrait Mode")
                curr_ps = config['active_profile']['portrait'].get('action_set', '')
                curr_pn = config['active_profile']['portrait'].get('action_name', '')
                new_ps = st.selectbox("Action Set (P)", available_sets, index=available_sets.index(curr_ps) if curr_ps in available_sets else 0)
                new_pn = st.text_input("Action Name (P)", value=curr_pn)

            with cl:
                st.caption("Landscape Mode")
                curr_ls = config['active_profile']['landscape'].get('action_set', '')
                curr_ln = config['active_profile']['landscape'].get('action_name', '')
                new_ls = st.selectbox("Action Set (L)", available_sets, index=available_sets.index(curr_ls) if curr_ls in available_sets else 0)
                new_ln = st.text_input("Action Name (L)", value=curr_ln)

            if st.button("Update Action Profiles"):
                config['active_profile']['portrait'] = {"action_set": new_ps, "action_name": new_pn}
                config['active_profile']['landscape'] = {"action_set": new_ls, "action_name": new_ln}
                save_config(config, config_path)
                st.success("Actions Assigned!")

            st.divider()
            
            # Subfolder Action logic 
            st.subheader("Subfolder Event Management")
            curr_sub = config.get('subfolder_action_set', 'Event_Subfolders')
            new_sub = st.selectbox("Default Subfolder Action Set", available_sets, index=available_sets.index(curr_sub) if curr_sub in available_sets else 0)
            if st.button("Save Subfolder Config"):
                config['subfolder_action_set'] = new_sub
                save_config(config, config_path)
                st.success("Subfolder Settings Updated!")