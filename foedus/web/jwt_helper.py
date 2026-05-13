"""Short-lived JWTs for the Godot SPA bearer auth.

The SPA receives a token in the URL query string at load time and uses
it as `Authorization: Bearer <token>` on every API call. Tokens encode
(user_id, game_id, player_idx) and expire quickly.
"""
from __future__ import annotations
import time
import jwt

class InvalidToken(Exception): pass
class ExpiredToken(InvalidToken): pass

def mint_spa_token(user_id: int, game_id: str, player_idx: int,
                   secret: str, ttl_seconds: int) -> str:
    now = int(time.time())
    payload = {"user_id": user_id, "game_id": game_id,
               "player_idx": player_idx,
               "iat": now, "exp": now + ttl_seconds}
    return jwt.encode(payload, secret, algorithm="HS256")

def verify_spa_token(token: str, secret: str) -> dict:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise ExpiredToken(str(e)) from e
    except jwt.InvalidTokenError as e:
        raise InvalidToken(str(e)) from e
