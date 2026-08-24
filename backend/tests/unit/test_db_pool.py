from lesspaper_ngl.db.session import DB_MAX_OVERFLOW, DB_POOL_SIZE, DB_POOL_TIMEOUT_SECONDS


def test_db_pool_defaults_fail_fast_instead_of_stacking() -> None:
    assert DB_POOL_SIZE == 10
    assert DB_MAX_OVERFLOW == 20
    assert DB_POOL_TIMEOUT_SECONDS == 10
