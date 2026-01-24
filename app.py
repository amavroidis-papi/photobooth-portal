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
    except:
        return None, path

def create_default_config(station_id):
    default_data = {
        "assigned_server": "Unassigned", # NEW: Gatekeeper Field
        "station_id": station_id,
        "station_enabled": True, 
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
st.set_page_config(page_title="Photobooth Command", layout="wide", page_icon="📷")
st.title("📷 Photobooth Fleet Command")

# 1. SIDEBAR - FLEET VIEW
st.sidebar.header("📡 Live Status")
fleet_data = get_fleet_data()
online_server_ids = []

if fleet_data:
    df = pd.DataFrame(fleet_data)
    st.sidebar.dataframe(
        df[['server_id', 'watching_station', 'status']], 
        hide_index=True, use_container_width=True
    )
    online_server_ids = sorted(list(set([s['server_id'] for s in fleet_data])))
    
    # Filter
    filter_server = st.sidebar.selectbox("Filter by Server (Optional)", ["All Stations"] + online_server_ids)
else:
    st.sidebar.warning("No servers online.")
    filter_server = "All Stations"

st.sidebar.divider()

# 2. STATION SELECTOR
st.sidebar.header("🎮 Station Manager")

if filter_server != "All Stations":
    # Show only stations currently WATCHED by this server (via heartbeat data)
    filtered_list = [s['watching_station'] for s in fleet_data if s['server_id'] == filter_server]
    display_list = sorted(filtered_list)
else:
    display_list = KNOWN_STATIONS

selected_station = st.sidebar.selectbox("Select Station to Configure", display_list)

if selected_station:
    st.header(f"🔧 Managing: {selected_station}")
    
    config, config_path = load_config(selected_station)
    
    if not config:
        st.warning(f"Config missing for {selected_station}")
        if st.button("Initialize Config Now"):
            config, config_path = create_default_config(selected_station)
            st.rerun()
            
    if config:
        # --- MASTER SWITCH & ASSIGNMENT ---
        col_sw, col_assign, col_status = st.columns([2, 3, 2])
        
        with col_sw:
            is_enabled = config.get("station_enabled", True)
            new_enabled = st.toggle("Station ON/OFF", value=is_enabled)
        
        with col_assign:
            # Server Assignment Dropdown
            curr_assign = config.get("assigned_server", "Unassigned")
            # Combine current assignment with list of online servers to ensure it appears even if offline
            assign_options = ["Unassigned"] + sorted(list(set(online_server_ids + [curr_assign]))) 
            if "Unassigned" in assign_options and assign_options.count("Unassigned") > 1:
                assign_options.remove("Unassigned")
                assign_options.insert(0, "Unassigned")
                
            new_assign = st.selectbox("Assigned Server", assign_options, index=assign_options.index(curr_assign) if curr_assign in assign_options else 0)

        with col_status:
            if new_enabled:
                st.success("🟢 Active")
            else:
                st.error("🔴 Disabled")
        
        # Save Header Changes
        if new_enabled != is_enabled or new_assign != curr_assign:
            config["station_enabled"] = new_enabled
            config["assigned_server"] = new_assign
            save_config(config, config_path)
            st.rerun()

        st.divider()

        if is_enabled:
            tab1, tab2, tab3 = st.tabs(["⚙️ Settings", "🎨 Assets", "🎬 Profiles & Actions"])
            
            # --- TAB 1: SETTINGS ---
            with tab1:
                c1, c2 = st.columns(2)
                with c1:
                    curr_bg = config['settings'].get('remove_background', False)
                    new_bg = st.toggle("Remove Background (API)", value=curr_bg)
                    if new_bg != curr_bg:
                        config['settings']['remove_background'] = new_bg
                        save_config(config, config_path)
                        st.toast("Updated BG")
                    
                    curr_temp = config['settings'].get('temperature', 0)
                    new_temp = st.slider("Temperature", -100, 100, curr_temp)
                    if new_temp != curr_temp:
                        config['settings']['temperature'] = new_temp
                        save_config(config, config_path)
                        st.toast("Updated Temp")

                with c2:
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
                suffix = st.text_input("Sub-Profile (e.g., 001)", placeholder="Default")
                
                c1, c2 = st.columns(2)
                with c1:
                    bg = st.file_uploader("Background (.jpg)", type=['jpg', 'jpeg'])
                    if bg and st.button("Upload BG"):
                        name = f"background{suffix}.jpg" if suffix else "background.jpg"
                        upload_asset(bg, f"/{selected_station}/templates/{name}")
                        st.success(f"Saved {name}")
                        time.sleep(1)
                        st.rerun()
                with c2:
                    ol = st.file_uploader("Overlay (.png)", type=['png'])
                    if ol and st.button("Upload Overlay"):
                        name = f"overlay{suffix}.png" if suffix else "overlay.png"
                        upload_asset(ol, f"/{selected_station}/templates/{name}")
                        st.success(f"Saved {name}")
                        time.sleep(1)
                        st.rerun()

            # --- TAB 3: ACTIONS ---
            with tab3:
                available_sets = get_available_actions()
                if not available_sets: available_sets = ["Default"]

                st.markdown("### Root Folder Actions")
                col_p, col_l = st.columns(2)
                
                with col_p:
                    st.caption("Portrait")
                    cur_p_set = config['active_profile']['portrait'].get('action_set', '')
                    cur_p_name = config['active_profile']['portrait'].get('action_name', 'Portrait')
                    
                    idx_p = available_sets.index(cur_p_set) if cur_p_set in available_sets else 0
                    new_p_set = st.selectbox("Action File", available_sets, index=idx_p, key="p_set")
                    new_p_name = st.text_input("Action Name", cur_p_name, key="p_name")

                    if new_p_set != cur_p_set or new_p_name != cur_p_name:
                        if st.button("Save Portrait"):
                            config['active_profile']['portrait']['action_set'] = new_p_set
                            config['active_profile']['portrait']['action_name'] = new_p_name
                            save_config(config, config_path)
                            st.success("Saved!")

                with col_l:
                    st.caption("Landscape")
                    cur_l_set = config['active_profile']['landscape'].get('action_set', '')
                    cur_l_name = config['active_profile']['landscape'].get('action_name', 'Landscape')
                    
                    idx_l = available_sets.index(cur_l_set) if cur_l_set in available_sets else 0
                    new_l_set = st.selectbox("Action File", available_sets, index=idx_l, key="l_set")
                    new_l_name = st.text_input("Action Name", cur_l_name, key="l_name")

                    if new_l_set != cur_l_set or new_l_name != cur_l_name:
                        if st.button("Save Landscape"):
                            config['active_profile']['landscape']['action_set'] = new_l_set
                            config['active_profile']['landscape']['action_name'] = new_l_name
                            save_config(config, config_path)
                            st.success("Saved!")

                st.divider()

                st.markdown("### Subfolder Actions")
                cur_sub_set = config.get('subfolder_action_set', 'Event_Subfolders')
                idx_sub = available_sets.index(cur_sub_set) if cur_sub_set in available_sets else 0
                new_sub_set = st.selectbox("Subfolder Set", available_sets, index=idx_sub, key="sub_set")
                
                if new_sub_set != cur_sub_set:
                    if st.button("Update Subfolder Set"):
                        config['subfolder_action_set'] = new_sub_set
                        save_config(config, config_path)
                        st.success("Updated!")

                st.divider()
                st.subheader("Upload Action")
                up_atn = st.file_uploader("Select .atn file", type=['atn'])
                if up_atn and st.button("Upload"):
                    upload_asset(up_atn, f"{ACTIONS_FOLDER}/{up_atn.name}")
                    st.success("Uploaded!")
                    time.sleep(1)
                    st.rerun()