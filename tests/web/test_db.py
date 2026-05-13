from sqlalchemy import text

def test_engine_can_execute(db):
    with db() as s:
        result = s.execute(text("SELECT 1")).scalar()
        assert result == 1
