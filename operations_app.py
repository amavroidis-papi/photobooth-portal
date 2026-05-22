import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from operations_db import (
    OperationsDatabaseError,
    check_connection,
    create_client,
    create_equipment,
    create_event,
    create_logistics_task,
    create_staff,
    create_vehicle,
    create_venue,
    list_clients,
    list_equipment,
    list_logistics_tasks,
    list_operations_events,
    list_staff,
    list_staff_jobs,
    list_vehicles,
    list_venues,
)
from operations_models import (
    EQUIPMENT_CATEGORIES,
    EVENT_STATUSES,
    LOGISTICS_TASK_STATUSES,
    LOGISTICS_TASK_TYPES,
)


APP_TIMEZONE = ZoneInfo("Europe/Athens")


def render_operations_app(current_user=None, current_role=None, access_token=None):
    """Render the Operations Portal shell.

    This module is intentionally separate from the existing Fleet Management
    views. It should not read or write the Dropbox JSON event system.
    """
    st.header("Operations Portal")
    st.caption("Weekly planning, staff assignments, logistics, equipment, and vehicles.")

    selected_view = st.radio(
        "Operations view",
        ["Dashboard", "Weekly Plan", "Events", "Logistics", "Manage Data", "Staff Jobs"],
        horizontal=True,
        label_visibility="collapsed",
        key="operations_view",
    )

    if selected_view == "Dashboard":
        render_operations_dashboard(access_token=access_token)
    elif selected_view == "Weekly Plan":
        render_weekly_plan(access_token=access_token)
    elif selected_view == "Events":
        render_operations_events(current_user=current_user, access_token=access_token)
    elif selected_view == "Logistics":
        render_logistics(current_user=current_user, access_token=access_token)
    elif selected_view == "Manage Data":
        render_manage_data(access_token=access_token)
    elif selected_view == "Staff Jobs":
        render_staff_jobs(current_user=current_user, access_token=access_token)


def render_operations_dashboard(access_token=None):
    st.subheader("Dashboard")
    try:
        check_connection(access_token=access_token)
    except OperationsDatabaseError as e:
        st.warning(f"Operations database is not ready yet: {e}")
        st.stop()

    clients = list_clients(access_token=access_token)
    venues = list_venues(access_token=access_token)
    staff = list_staff(access_token=access_token)
    events = list_operations_events(access_token=access_token)
    tasks = list_logistics_tasks(access_token=access_token)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Clients", len(clients))
    c2.metric("Venues", len(venues))
    c3.metric("Staff", len(staff))
    c4.metric("Events", len(events))
    c5.metric("Logistics Tasks", len(tasks))

    st.markdown("### Recent Events")
    if events:
        st.dataframe(events[:10], hide_index=True, use_container_width=True)
    else:
        st.info("No operations events yet.")


def render_weekly_plan(access_token=None):
    st.subheader("Weekly Plan")
    try:
        events = list_operations_events(access_token=access_token)
        tasks = list_logistics_tasks(access_token=access_token)
    except OperationsDatabaseError as e:
        st.warning(f"Operations database is not ready yet: {e}")
        st.stop()

    st.markdown("### Events")
    if events:
        st.dataframe(events, hide_index=True, use_container_width=True)
    else:
        st.info("No events for the selected period yet.")

    st.markdown("### Logistics Tasks")
    if tasks:
        st.dataframe(tasks, hide_index=True, use_container_width=True)
    else:
        st.info("No logistics tasks for the selected period yet.")


def _as_options(records, label_key):
    options = {"None": None}
    for record in records:
        label = record.get(label_key) or record.get("event_name") or record.get("id")
        options[label] = record.get("id")
    return options


def _combine_datetime(date_value, time_value):
    if not date_value or not time_value:
        return None
    return datetime.combine(date_value, time_value).replace(tzinfo=APP_TIMEZONE).isoformat()


def _show_db_error(error):
    st.warning(f"Operations database error: {error}")


def render_operations_events(current_user=None, access_token=None):
    st.subheader("Events")
    try:
        clients = list_clients(access_token=access_token)
        venues = list_venues(access_token=access_token)
        events = list_operations_events(access_token=access_token)
    except OperationsDatabaseError as e:
        st.warning(f"Operations database is not ready yet: {e}")
        st.stop()

    with st.expander("Create Event", expanded=not bool(events)):
        client_options = _as_options(clients, "client_name")
        venue_options = _as_options(venues, "venue_name")
        with st.form("create_operations_event"):
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                event_name = st.text_input("Event name")
            with c2:
                event_date = st.date_input("Event date")
            with c3:
                status = st.selectbox("Status", EVENT_STATUSES, index=0)

            c4, c5 = st.columns(2)
            with c4:
                client_label = st.selectbox("Client", list(client_options.keys()))
            with c5:
                venue_label = st.selectbox("Venue", list(venue_options.keys()))

            c6, c7, c8, c9 = st.columns(4)
            with c6:
                setup_time = st.time_input("Setup start", value=None)
            with c7:
                event_start_time = st.time_input("Event start", value=None)
            with c8:
                event_end_time = st.time_input("Event end", value=None)
            with c9:
                takedown_time = st.time_input("Takedown start", value=None)

            solution_type = st.text_input("Solution")
            content_notes = st.text_input("Content")
            map_url = st.text_input("Map URL")
            dress_code = st.text_input("Dress code")
            staff_notes = st.text_area("Staff notes")
            internal_notes = st.text_area("Internal notes")
            submitted = st.form_submit_button("Create Event")

        if submitted:
            if not event_name.strip():
                st.error("Event name is required.")
            else:
                payload = {
                    "event_name": event_name.strip(),
                    "event_date": event_date.isoformat(),
                    "status": status,
                    "client_id": client_options[client_label],
                    "venue_id": venue_options[venue_label],
                    "setup_start_at": _combine_datetime(event_date, setup_time),
                    "event_start_at": _combine_datetime(event_date, event_start_time),
                    "event_end_at": _combine_datetime(event_date, event_end_time),
                    "takedown_start_at": _combine_datetime(event_date, takedown_time),
                    "solution_type": solution_type.strip(),
                    "content_notes": content_notes.strip(),
                    "map_url": map_url.strip(),
                    "dress_code": dress_code.strip(),
                    "staff_notes": staff_notes.strip(),
                    "internal_notes": internal_notes.strip(),
                    "created_by_email": current_user,
                }
                try:
                    create_event(payload, access_token=access_token)
                    st.success("Event created.")
                    st.rerun()
                except OperationsDatabaseError as e:
                    _show_db_error(e)

    if events:
        st.dataframe(events, hide_index=True, use_container_width=True)
    else:
        st.info("No operations events yet.")


def render_logistics(current_user=None, access_token=None):
    st.subheader("Logistics")
    try:
        events = list_operations_events(access_token=access_token)
        venues = list_venues(access_token=access_token)
        tasks = list_logistics_tasks(access_token=access_token)
    except OperationsDatabaseError as e:
        st.warning(f"Operations database is not ready yet: {e}")
        st.stop()

    with st.expander("Create Logistics Task", expanded=not bool(tasks)):
        event_options = {"None": None}
        for event in events:
            client = (event.get("clients") or {}).get("client_name") if isinstance(event.get("clients"), dict) else ""
            label = " | ".join(part for part in [event.get("event_date"), client, event.get("event_name")] if part)
            event_options[label] = event.get("id")
        venue_options = _as_options(venues, "venue_name")

        with st.form("create_logistics_task"):
            c1, c2 = st.columns([2, 1])
            with c1:
                title = st.text_input("Task / job")
            with c2:
                task_type = st.selectbox("Task type", LOGISTICS_TASK_TYPES, index=LOGISTICS_TASK_TYPES.index("Other"))

            c3, c4, c5, c6 = st.columns(4)
            with c3:
                task_date = st.date_input("Task date")
            with c4:
                start_time = st.time_input("Start", value=None)
            with c5:
                end_time = st.time_input("End", value=None)
            with c6:
                status = st.selectbox("Status", LOGISTICS_TASK_STATUSES, index=0)

            event_label = st.selectbox("Related event", list(event_options.keys()))
            venue_label = st.selectbox("Venue", list(venue_options.keys()))
            location_text = st.text_input("Location text")
            assigned_team_text = st.text_input("Team")
            assigned_vehicle_text = st.text_input("Vehicle")
            notes = st.text_area("Notes")
            submitted = st.form_submit_button("Create Logistics Task")

        if submitted:
            if not title.strip():
                st.error("Task / job is required.")
            else:
                payload = {
                    "event_id": event_options[event_label],
                    "task_type": task_type,
                    "title": title.strip(),
                    "scheduled_start_at": _combine_datetime(task_date, start_time),
                    "scheduled_end_at": _combine_datetime(task_date, end_time),
                    "venue_id": venue_options[venue_label],
                    "location_text": location_text.strip(),
                    "assigned_team_text": assigned_team_text.strip(),
                    "assigned_vehicle_text": assigned_vehicle_text.strip(),
                    "status": status,
                    "notes": notes.strip(),
                    "created_by_email": current_user,
                }
                try:
                    create_logistics_task(payload, access_token=access_token)
                    st.success("Logistics task created.")
                    st.rerun()
                except OperationsDatabaseError as e:
                    _show_db_error(e)

    if tasks:
        st.dataframe(tasks, hide_index=True, use_container_width=True)
    else:
        st.info("No logistics tasks yet.")


def render_manage_data(access_token=None):
    st.subheader("Manage Data")
    tabs = st.tabs(["Clients", "Venues", "Staff", "Vehicles", "Equipment"])

    with tabs[0]:
        render_client_form(access_token=access_token)
    with tabs[1]:
        render_venue_form(access_token=access_token)
    with tabs[2]:
        render_staff_form(access_token=access_token)
    with tabs[3]:
        render_vehicle_form(access_token=access_token)
    with tabs[4]:
        render_equipment_form(access_token=access_token)


def render_client_form(access_token=None):
    with st.form("create_client"):
        client_name = st.text_input("Client name")
        contact_name = st.text_input("Main contact name")
        contact_phone = st.text_input("Main contact phone")
        contact_email = st.text_input("Main contact email")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Client")
    if submitted:
        if not client_name.strip():
            st.error("Client name is required.")
        else:
            try:
                create_client(client_name.strip(), contact_name.strip(), contact_phone.strip(), contact_email.strip(), notes.strip(), access_token=access_token)
                st.success("Client added.")
                st.rerun()
            except OperationsDatabaseError as e:
                _show_db_error(e)
    try:
        clients = list_clients(access_token=access_token)
        if clients:
            st.dataframe(clients, hide_index=True, use_container_width=True)
    except OperationsDatabaseError as e:
        _show_db_error(e)


def render_venue_form(access_token=None):
    with st.form("create_venue"):
        venue_name = st.text_input("Venue name")
        address = st.text_input("Address")
        maps = st.text_input("Google Maps URL")
        loading = st.text_area("Loading instructions")
        parking = st.text_area("Parking instructions")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Venue")
    if submitted:
        if not venue_name.strip():
            st.error("Venue name is required.")
        else:
            try:
                create_venue(venue_name.strip(), address.strip(), maps.strip(), loading.strip(), parking.strip(), notes.strip(), access_token=access_token)
                st.success("Venue added.")
                st.rerun()
            except OperationsDatabaseError as e:
                _show_db_error(e)
    try:
        venues = list_venues(access_token=access_token)
        if venues:
            st.dataframe(venues, hide_index=True, use_container_width=True)
    except OperationsDatabaseError as e:
        _show_db_error(e)


def render_staff_form(access_token=None):
    with st.form("create_staff"):
        full_name = st.text_input("Full name")
        email = st.text_input("Email")
        phone = st.text_input("Phone")
        role_type = st.text_input("Role type")
        c1, c2 = st.columns(2)
        with c1:
            has_driving_license = st.checkbox("Driving license")
        with c2:
            has_vehicle = st.checkbox("Has vehicle")
        submitted = st.form_submit_button("Add Staff")
    if submitted:
        if not full_name.strip():
            st.error("Full name is required.")
        else:
            try:
                create_staff(full_name.strip(), email.strip(), phone.strip(), role_type.strip(), has_driving_license, has_vehicle, access_token=access_token)
                st.success("Staff added.")
                st.rerun()
            except OperationsDatabaseError as e:
                _show_db_error(e)
    try:
        staff = list_staff(access_token=access_token)
        if staff:
            st.dataframe(staff, hide_index=True, use_container_width=True)
    except OperationsDatabaseError as e:
        _show_db_error(e)


def render_vehicle_form(access_token=None):
    with st.form("create_vehicle"):
        vehicle_name = st.text_input("Vehicle name")
        plate_number = st.text_input("Plate number")
        capacity_notes = st.text_area("Capacity notes")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Vehicle")
    if submitted:
        if not vehicle_name.strip():
            st.error("Vehicle name is required.")
        else:
            try:
                create_vehicle(vehicle_name.strip(), plate_number.strip(), capacity_notes.strip(), notes.strip(), access_token=access_token)
                st.success("Vehicle added.")
                st.rerun()
            except OperationsDatabaseError as e:
                _show_db_error(e)
    try:
        vehicles = list_vehicles(access_token=access_token)
        if vehicles:
            st.dataframe(vehicles, hide_index=True, use_container_width=True)
    except OperationsDatabaseError as e:
        st.info(f"Vehicle tables are not ready yet. Run migration 001 if needed. Details: {e}")


def render_equipment_form(access_token=None):
    with st.form("create_equipment"):
        equipment_name = st.text_input("Equipment / item name")
        category = st.selectbox("Category", [""] + EQUIPMENT_CATEGORIES)
        serial_number = st.text_input("Serial number")
        asset_code = st.text_input("Asset code")
        storage_location = st.text_input("Storage location")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Equipment")
    if submitted:
        if not equipment_name.strip():
            st.error("Equipment / item name is required.")
        else:
            try:
                create_equipment(equipment_name.strip(), category, serial_number.strip(), asset_code.strip(), storage_location.strip(), notes.strip(), access_token=access_token)
                st.success("Equipment added.")
                st.rerun()
            except OperationsDatabaseError as e:
                _show_db_error(e)
    try:
        equipment = list_equipment(access_token=access_token)
        if equipment:
            st.dataframe(equipment, hide_index=True, use_container_width=True)
    except OperationsDatabaseError as e:
        st.info(f"Equipment tables are not ready yet. Run migration 001 if needed. Details: {e}")


def render_staff_jobs(current_user=None, access_token=None):
    st.subheader("My Jobs")
    if current_user:
        st.caption(f"Signed in as {current_user}")
    else:
        st.info("Sign in to see assigned jobs.")
        return

    try:
        jobs = list_staff_jobs(current_user, access_token=access_token)
    except OperationsDatabaseError as e:
        st.warning(f"Operations database is not ready yet: {e}")
        st.stop()

    if jobs:
        st.dataframe(jobs, hide_index=True, use_container_width=True)
    else:
        st.info("No assigned jobs yet.")
