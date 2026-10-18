import pytest

from scam_shield import tokens

SECRET = "test-secret"
NOW = 1_800_000_000.0


def test_round_trip():
    token = tokens.issue({"money_score": 0.6}, SECRET, ttl_seconds=60, now=NOW)
    payload = tokens.verify(token, SECRET, now=NOW + 10)
    assert payload["money_score"] == 0.6


def test_expired_token_rejected():
    token = tokens.issue({"a": 1}, SECRET, ttl_seconds=60, now=NOW)
    with pytest.raises(tokens.InvalidToken, match="expired"):
        tokens.verify(token, SECRET, now=NOW + 61)


def test_wrong_secret_rejected():
    token = tokens.issue({"a": 1}, SECRET, ttl_seconds=60, now=NOW)
    with pytest.raises(tokens.InvalidToken, match="signature"):
        tokens.verify(token, "other-secret", now=NOW)


def test_tampered_payload_rejected():
    honest = tokens.issue({"money_score": 0.9}, SECRET, ttl_seconds=60, now=NOW)
    forged_body = tokens.issue({"money_score": 0.0}, SECRET, ttl_seconds=60, now=NOW)
    tampered = forged_body.split(".")[0] + "." + honest.split(".")[1]
    with pytest.raises(tokens.InvalidToken):
        tokens.verify(tampered, SECRET, now=NOW)


@pytest.mark.parametrize("junk", ["", "no-dot", "a.b.c", "!!!.???"])
def test_malformed_token_rejected(junk):
    with pytest.raises(tokens.InvalidToken):
        tokens.verify(junk, SECRET, now=NOW)
