"""The scam types Scam Shield knows about. One list shared by data generation,
the context reader and the UI."""

from enum import StrEnum


class ScamType(StrEnum):
    DIGITAL_ARREST = "digital_arrest"
    KYC_UPDATE = "kyc_update"
    JOB_TASK = "job_task"
    FAKE_COURIER = "fake_courier"
    INVESTMENT = "investment"
    NONE = "none"  # genuine payment context


DESCRIPTIONS: dict[ScamType, str] = {
    ScamType.DIGITAL_ARREST: (
        "Caller poses as police/CBI/ED/customs, claims the victim is linked to a crime "
        "(money laundering, drugs in a parcel), keeps them on video call, demands money "
        "moved to a 'safe' or 'RBI verification' account and secrecy."
    ),
    ScamType.KYC_UPDATE: (
        "Message claims bank KYC/PAN/Aadhaar expired and the account will be blocked; asks to "
        "click a link, share OTP, install an app, or pay/transfer to 're-verify'."
    ),
    ScamType.JOB_TASK: (
        "Part-time job offer (like/review/rate tasks) pays small rewards first, then asks for "
        "growing 'deposits' or 'tax' to unlock earnings."
    ),
    ScamType.FAKE_COURIER: (
        "Courier/customs says a parcel is held or contains illegal items; asks for a fee or "
        "fine, often escalating to a fake police call."
    ),
    ScamType.INVESTMENT: (
        "Stock/crypto/IPO 'tips' group or advisor promises guaranteed high returns; asks to "
        "transfer money to a trading app or personal account."
    ),
    ScamType.NONE: (
        "Genuine payment context: family asking for help, bills, rent, purchases with real "
        "invoices, normal bank notifications that say never share OTP."
    ),
}
