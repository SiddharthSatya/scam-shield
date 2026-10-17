from unittest.mock import MagicMock

from scam_shield.context import (
    ContextInput,
    ContextVerdict,
    Purpose,
    fallback_result,
    read_context,
    tap_risk,
)
from scam_shield.scam_types import ScamType

SCARED = ContextInput(purpose=Purpose.GOVT_POLICE_KYC, on_call=True, told_to_keep_secret=True)
CALM = ContextInput(purpose=Purpose.SHOPPING_BILL, on_call=False, told_to_keep_secret=False)


def fake_client(verdict=None, error: Exception | None = None) -> MagicMock:
    client = MagicMock()
    if error:
        client.models.generate_content.side_effect = error
    else:
        client.models.generate_content.return_value = MagicMock(parsed=verdict)
    return client


def test_tap_risk_scam_story_is_capped_at_one():
    assert tap_risk(SCARED) == 1.0


def test_tap_risk_genuine_story_is_low():
    assert tap_risk(CALM) == 0.1


def test_tap_risk_no_answers_is_zero():
    assert tap_risk(ContextInput()) == 0.0


def test_fallback_names_scam_from_purpose():
    result = fallback_result(SCARED)
    assert result.scam_type == ScamType.DIGITAL_ARREST
    assert result.source == "fallback"
    assert len(result.red_flags) == 2


def test_fallback_genuine_is_none():
    assert fallback_result(CALM).scam_type == ScamType.NONE


def test_gemini_error_falls_back_instead_of_raising():
    result = read_context(SCARED, fake_client(error=TimeoutError()), "m")
    assert result.source == "fallback"
    assert result.score == 1.0


def test_unparsable_response_falls_back():
    result = read_context(CALM, fake_client(verdict=None), "m")
    assert result.source == "fallback"


def test_strong_taps_floor_a_lenient_model():
    lenient = ContextVerdict(scam_type=ScamType.NONE, score=0.2, red_flags=[], explanation="ok")
    result = read_context(SCARED, fake_client(verdict=lenient), "m")
    assert result.score == 1.0
    assert result.source == "gemini"


def test_model_score_used_when_higher_than_taps():
    verdict = ContextVerdict(scam_type=ScamType.KYC_UPDATE, score=0.9,
                             red_flags=["Fake link"], explanation="KYC scam")
    result = read_context(ContextInput(message_text="KYC expired, click bit.ly/x"),
                          fake_client(verdict=verdict), "m")
    assert result.score == 0.9
    assert result.scam_type == ScamType.KYC_UPDATE
