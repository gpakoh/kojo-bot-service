-- setup_app_role.sql
-- Creates the application-level database role with NOBYPASSRLS for RLS enforcement.
--
-- Usage:
--   psql -v app_user_password='<password>' -f scripts/setup_app_role.sql
--
-- The password should be passed as a psql variable (never hardcoded).
-- In CI/CD, inject via environment variable or secrets manager.
--
-- Required env: KOJO_ENABLE_FORCE_RLS=true
-- Run BEFORE: alembic upgrade head (role must exist before migrations apply grants)

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'kojo_app_user') THEN
        CREATE ROLE kojo_app_user WITH
            LOGIN NOSUPERUSER INHERIT NOCREATEDB NOCREATEROLE NOREPLICATION
            NOBYPASSRLS PASSWORD :'app_user_password';
    ELSE
        RAISE NOTICE 'Role kojo_app_user already exists, skipping creation';
    END IF;
END
$$;

-- Schema access
GRANT USAGE ON SCHEMA public TO kojo_app_user;

-- Default privileges for future tables (created by migrations as kojo_user)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO kojo_app_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE ON SEQUENCES TO kojo_app_user;

-- Grant execute on the tenant context function (SECURITY DEFINER, runs as owner)
GRANT EXECUTE ON FUNCTION set_tenant_context(text) TO kojo_app_user;

-- Verify
SELECT rolname, rolsuper, rolbypassrls
FROM pg_roles WHERE rolname IN ('kojo_user', 'kojo_app_user');
