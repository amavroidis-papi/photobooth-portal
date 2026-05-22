# Operations Portal setup notes

## Supabase

1. Open the Supabase SQL editor.
2. Run `operations_schema.sql`.
3. In Supabase API settings, expose the `operations` schema through PostgREST.
4. Confirm the Heroku app has these config vars:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - optional: `OPERATIONS_SCHEMA=operations`
   - `PORTAL_ADMIN_EMAILS`
   - `PORTAL_FLEET_EMAILS`
   - optional: `PORTAL_OPERATIONS_EMAILS`

## Portal access

Admins always see both portals.

Fleet Management is restricted to:

- emails in `PORTAL_ADMIN_EMAILS`
- emails in `PORTAL_FLEET_EMAILS`

Operations is available to all authenticated staff by default. If you want to
restrict Operations too, set `PORTAL_OPERATIONS_EMAILS`; once that variable has
at least one email, only admins and listed Operations users will see it.

Example Heroku values:

```text
PORTAL_ADMIN_EMAILS=owner@thephotobooth.gr,manager@thephotobooth.gr
PORTAL_FLEET_EMAILS=tech1@thephotobooth.gr,tech2@thephotobooth.gr
PORTAL_OPERATIONS_EMAILS=ops1@thephotobooth.gr,ops2@thephotobooth.gr,sales1@thephotobooth.gr
```

## Security

The schema enables row level security and allows access only to authenticated
Supabase users. When the Operations Portal is wired into `app.py`, it should
pass `st.session_state.auth_access_token` into `render_operations_app(...)`.

This first policy is intentionally broad for the internal MVP. Later, we should
split access by role so staff can only see their own jobs while operations
managers can manage all records.

## Current app integration status

The Operations files exist, but `app.py` is not wired yet. That is intentional:
apply the schema and confirm the database connection first, then add the
Operations option to the existing portal selector.
