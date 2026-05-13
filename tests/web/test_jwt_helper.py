from __future__ import annotations
import time, pytest
from foedus.web.jwt_helper import mint_spa_token, verify_spa_token, ExpiredToken, InvalidToken

def test_roundtrip():
    tok = mint_spa_token(user_id=1, game_id="g-1", player_idx=2,
                         secret="s", ttl_seconds=60)
    claims = verify_spa_token(tok, secret="s")
    assert claims["user_id"] == 1
    assert claims["game_id"] == "g-1"
    assert claims["player_idx"] == 2

def test_expired_rejected():
    tok = mint_spa_token(user_id=1, game_id="g-1", player_idx=0,
                         secret="s", ttl_seconds=-1)
    with pytest.raises(ExpiredToken):
        verify_spa_token(tok, secret="s")

def test_wrong_secret_rejected():
    tok = mint_spa_token(user_id=1, game_id="g-1", player_idx=0,
                         secret="a", ttl_seconds=60)
    with pytest.raises(InvalidToken):
        verify_spa_token(tok, secret="b")
