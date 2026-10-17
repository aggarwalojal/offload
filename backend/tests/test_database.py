from pathlib import Path


def test_migration_and_database_security(postgres):
    postgres.sql("truncate auth.users cascade")
    postgres.file(Path(__file__).with_name("database_assertions.sql"))
