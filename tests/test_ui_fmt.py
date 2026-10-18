import pytest

from ui.fmt import hour_label, inr


@pytest.mark.parametrize(("amount", "expected"), [
    (0, "₹0"), (999, "₹999"), (1_200, "₹1,200"), (40_000, "₹40,000"),
    (480_000, "₹4,80,000"), (1_95_000, "₹1,95,000"), (12_34_56_789, "₹12,34,56,789"),
    (-5_000, "-₹5,000"), (1_199.6, "₹1,200"),
])
def test_inr_uses_indian_grouping(amount, expected):
    assert inr(amount) == expected


@pytest.mark.parametrize(("hour", "expected"), [(0, "12 AM"), (9, "9 AM"), (12, "12 PM"),
                                                (21, "9 PM")])
def test_hour_label(hour, expected):
    assert hour_label(hour) == expected
