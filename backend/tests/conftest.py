"""Disposable PostgreSQL for migration and full component integration tests."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

import pytest


@pytest.fixture(scope="session")
def postgres():
    bin_dir = os.environ.get("TEST_POSTGRES_BIN", "/opt/homebrew/opt/postgresql@15/bin")
    initdb = str(Path(bin_dir)/"initdb") if "TEST_POSTGRES_BIN" in os.environ else (
        shutil.which("initdb") or str(Path(bin_dir)/"initdb"))
    if not Path(initdb).is_file():
        pytest.skip("Local PostgreSQL binaries unavailable; set TEST_POSTGRES_BIN")
    pg_ctl, psql = (str(Path(initdb).parent/name) for name in ("pg_ctl", "psql"))

    def run(*args):
        result = subprocess.run(args, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout+result.stderr
        return result.stdout.strip()

    with tempfile.TemporaryDirectory(prefix="timeslice-pg-", dir="/private/tmp" if Path("/private/tmp").exists() else None) as temp:
        cluster, socket_dir = str(Path(temp)/"data"), str(Path(temp)/"socket")
        Path(socket_dir).mkdir()
        run(initdb, "-D", cluster, "-A", "trust", "--no-locale", "--encoding=UTF8", "-U", "postgres")
        run(pg_ctl, "-D", cluster, "-l", str(Path(temp)/"server.log"), "-o",
            f"-F -k {socket_dir} -h '' -p 55439", "-w", "start")
        try:
            base = (psql, "-X", "-qAt", "-h", socket_dir, "-p", "55439", "-U", "postgres", "-d", "postgres", "-v", "ON_ERROR_STOP=1")
            sql = lambda query: run(*base, "-c", query)
            file = lambda path: run(*base, "-f", str(path))
            sql("""
              create role anon; create role authenticated; create role service_role bypassrls;
              create schema auth; create table auth.users(id uuid primary key);
              create function auth.uid() returns uuid language sql stable as
                $$ select nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$;
              grant usage on schema auth to authenticated,service_role;
              create publication supabase_realtime;
            """)
            for migration in sorted((Path(__file__).parents[1]/"db/migrations").glob("*.sql")):
                file(migration)
            yield SimpleNamespace(sql=sql, file=file, json=lambda query: json.loads(sql(query)))
        finally:
            run(pg_ctl, "-D", cluster, "-m", "fast", "-w", "stop")
