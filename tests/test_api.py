"""API tests with BigQuery and Gemini mocked. No cloud calls."""

import base64
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from scam_shield import api, service
from scam_shield.context import ContextVerdict
from scam_shield.money import PaymentFacts
from scam_shield.money_repo import CustomerNotFound, MoneyInputs
from scam_shield.scam_types import ScamType
from scam_shield.settings import Settings

KEY = "test-key"
HEADERS = {"X-API-Key": KEY}
MEERA = {"balance_inr": 600_000, "p95_amount_inr": 8_396,
         "usual_from_hour": 9, "usual_to_hour": 19}


def make_settings() -> Settings:
    return Settings(gcp_project="test-project", api_key=SecretStr(KEY),
                    token_secret=SecretStr("test-secret"))


def money_inputs(amount: float, hour: int, new_payee: bool, age: int) -> MoneyInputs:
    facts = PaymentFacts(amount_inr=amount, hour_ist=hour, is_new_payee=new_payee,
                         payee_account_age_days=age, **MEERA)
    return MoneyInputs(facts=facts, model_probability=0.03, language="mr")


@pytest.fixture
def gemini() -> MagicMock:
    return MagicMock()


@pytest.fixture
def bq() -> MagicMock:
    client = MagicMock()
    client.insert_rows_json.return_value = []
    return client


@pytest.fixture
def client(bq, gemini, monkeypatch):
    deps = service.Deps(settings=make_settings(), bq=bq, gemini=gemini)
    api.app.dependency_overrides[api.get_deps] = lambda: deps
    with TestClient(api.app) as c:
        yield c
    api.app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def no_real_lifespan(monkeypatch):
    """Skip creating real cloud clients at startup."""
    @asynccontextmanager
    async def noop_lifespan(app):
        yield
    monkeypatch.setattr(api.app.router, "lifespan_context", noop_lifespan)


def stub_money(monkeypatch, inputs: MoneyInputs | Exception) -> None:
    def fake(*args, **kwargs):
        if isinstance(inputs, Exception):
            raise inputs
        return inputs
    monkeypatch.setattr(service, "fetch_money_inputs", fake)


def pay(client, amount=480_000, hour=21):
    return client.post("/v1/check-payment", headers=HEADERS, json={
        "customer_id": "c_meera", "payee_id": "p_new", "amount_inr": amount, "hour_ist": hour})


def test_health_needs_no_key(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_docs_are_off_by_default(client, path):
    assert client.get(path).status_code == 404


def test_missing_api_key_rejected(client, monkeypatch):
    stub_money(monkeypatch, money_inputs(1_200, 11, False, 3_000))
    r = client.post("/v1/check-payment", json={
        "customer_id": "c_x", "payee_id": "p_x", "amount_inr": 100, "hour_ist": 11})
    assert r.status_code == 401


def test_wrong_api_key_rejected(client):
    r = client.post("/v1/check-payment", headers={"X-API-Key": "nope"}, json={})
    assert r.status_code == 401


def test_normal_payment_passes_without_screen(client, bq, monkeypatch):
    stub_money(monkeypatch, money_inputs(1_200, 11, False, 3_000))
    r = pay(client, amount=1_200, hour=11)
    body = r.json()
    assert r.status_code == 200
    assert body["decision"] == "pass"
    assert body["screen"] is None and body["token"] is None
    bq.insert_rows_json.assert_called_once()  # decision logged


def test_risky_payment_asks_with_safety_check(client, monkeypatch):
    stub_money(monkeypatch, money_inputs(480_000, 21, True, 2))
    body = pay(client).json()
    assert body["decision"] == "ask"
    assert body["screen"]["kind"] == "safety_check"
    assert [q["id"] for q in body["screen"]["questions"]] == [
        "purpose", "on_call", "told_to_keep_secret", "message"]
    assert body["token"]


def test_unknown_customer_is_404(client, monkeypatch):
    stub_money(monkeypatch, CustomerNotFound("c_x"))
    assert pay(client).status_code == 404


@pytest.mark.parametrize("bad", [
    {"amount_inr": 0}, {"amount_inr": -1}, {"hour_ist": 24}, {"customer_id": ""}])
def test_invalid_payment_input_is_422(client, bad):
    payload = {"customer_id": "c_meera", "payee_id": "p_new", "amount_inr": 100, "hour_ist": 1}
    r = client.post("/v1/check-payment", headers=HEADERS, json={**payload, **bad})
    assert r.status_code == 422


def test_scam_story_is_held_with_warning(client, gemini, monkeypatch):
    stub_money(monkeypatch, money_inputs(480_000, 21, True, 2))
    token = pay(client).json()["token"]
    gemini.models.generate_content.return_value = MagicMock(parsed=ContextVerdict(
        scam_type=ScamType.DIGITAL_ARREST, score=0.95,
        red_flags=["Threat of arrest", "'Safe account'"], explanation="Police never ask..."))

    r = client.post("/v1/context", headers=HEADERS, json={
        "token": token, "purpose": "govt_police_kyc", "on_call": True,
        "told_to_keep_secret": True, "message_text": "CBI notice: transfer to RBI safe account"})
    body = r.json()
    assert r.status_code == 200
    assert body["decision"] == "hold"
    assert body["scam_name"] == "Digital arrest scam"
    assert body["screen"]["kind"] == "warning"
    assert body["screen"]["bullets"] == ["Threat of arrest", "'Safe account'"]
    # Explanation requested in the customer's language (Marathi), taken from the token.
    system = gemini.models.generate_content.call_args.kwargs["config"].system_instruction
    assert "Marathi" in system


def test_genuine_story_passes(client, gemini, monkeypatch):
    stub_money(monkeypatch, money_inputs(480_000, 12, True, 2_900))
    token = pay(client, hour=12).json()["token"]
    gemini.models.generate_content.return_value = MagicMock(parsed=ContextVerdict(
        scam_type=ScamType.NONE, score=0.05, red_flags=[], explanation="Looks fine."))
    body = client.post("/v1/context", headers=HEADERS, json={
        "token": token, "purpose": "shopping_bill", "on_call": False,
        "told_to_keep_secret": False}).json()
    assert body["decision"] == "pass"
    assert body["screen"] is None


def test_gemini_down_still_decides_from_taps(client, gemini, monkeypatch):
    stub_money(monkeypatch, money_inputs(480_000, 21, True, 2))
    token = pay(client).json()["token"]
    gemini.models.generate_content.side_effect = TimeoutError()
    body = client.post("/v1/context", headers=HEADERS, json={
        "token": token, "purpose": "govt_police_kyc", "on_call": True,
        "told_to_keep_secret": True}).json()
    assert body["decision"] == "hold"
    assert body["context_source"] == "fallback"


def test_forged_token_rejected(client):
    r = client.post("/v1/context", headers=HEADERS, json={"token": "forged.token-value"})
    assert r.status_code == 400


def test_bad_image_rejected(client, monkeypatch):
    stub_money(monkeypatch, money_inputs(480_000, 21, True, 2))
    token = pay(client).json()["token"]
    r = client.post("/v1/context", headers=HEADERS,
                    json={"token": token, "image_base64": "not base64!!"})
    assert r.status_code == 422


def test_image_is_passed_to_gemini(client, gemini, monkeypatch):
    stub_money(monkeypatch, money_inputs(480_000, 21, True, 2))
    token = pay(client).json()["token"]
    gemini.models.generate_content.return_value = MagicMock(parsed=ContextVerdict(
        scam_type=ScamType.KYC_UPDATE, score=0.9, red_flags=["Fake link"], explanation="..."))
    png = base64.b64encode(b"\x89PNG fake image bytes").decode()
    client.post("/v1/context", headers=HEADERS, json={"token": token, "image_base64": png})
    contents = gemini.models.generate_content.call_args.kwargs["contents"]
    assert len(contents) == 2  # prompt + image part


def test_log_failure_does_not_break_the_response(client, bq, monkeypatch):
    stub_money(monkeypatch, money_inputs(1_200, 11, False, 3_000))
    bq.insert_rows_json.side_effect = RuntimeError("BigQuery down")
    assert pay(client, amount=1_200, hour=11).status_code == 200
