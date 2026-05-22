import streamlit as st

from operations_db import (
    OperationsDatabaseError,
    check_connection,
    list_clients,
    list_logistics_tasks,
    list_operations_events,
    list_staff,
    list_staff_jobs,
    list_venues,
)


def render_operations_app(current_user=None, current_role=None, access_token=None):
    """Render the Operations Portal shell.

    This module is intentionally separate from the existing Fleet Management
    views. It should not read or write the Dropbox JSON event system.
    """
    st.header("Operations Portal")
    st.caption("Weekly planning, staff assignments, logistics, equipment, and vehicles.")

    selected_view = st.radio(
        "Operations view",
        ["Dashboard", "Weekly Plan", "Events", "Staff Jobs"],
        horizontal=True,
        label_visibility="collapsed",
        key="operations_view",
    )

    if selected_view == "Dashboard":
        render_operations_dashboard(access_token=access_token)
    elif selected_view == "Weekly Plan":
        render_weekly_plan(access_token=access_token)
    elif selected_view == "Events":
        render_operations_events(access_token=access_token)
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


def render_operations_events(access_token=None):
    st.subheader("Events")
    try:
        events = list_operations_events(access_token=access_token)
    except OperationsDatabaseError as e:
        st.warning(f"Operations database is not ready yet: {e}")
        st.stop()

    if events:
        st.dataframe(events, hide_index=True, use_container_width=True)
    else:
        st.info("No operations events yet.")


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
