\set ON_ERROR_STOP on

SELECT format('CREATE ROLE execution_plane_migrator LOGIN PASSWORD %L', :'ep_migrator_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'execution_plane_migrator')
\gexec
ALTER ROLE execution_plane_migrator PASSWORD :'ep_migrator_password';

SELECT format('CREATE ROLE execution_plane_runtime LOGIN PASSWORD %L', :'ep_runtime_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'execution_plane_runtime')
\gexec
ALTER ROLE execution_plane_runtime PASSWORD :'ep_runtime_password';

SELECT 'CREATE DATABASE execution_plane OWNER execution_plane_migrator'
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = 'execution_plane')
\gexec
ALTER DATABASE execution_plane OWNER TO execution_plane_migrator;
REVOKE CONNECT ON DATABASE execution_plane FROM PUBLIC;
GRANT CONNECT ON DATABASE execution_plane TO execution_plane_runtime;

SELECT format('REVOKE CONNECT ON DATABASE %I FROM PUBLIC', :'ao_database')
\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'ao_database', :'ao_runtime_role')
\gexec
