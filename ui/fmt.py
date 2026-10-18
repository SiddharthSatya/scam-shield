"""Small formatting helpers."""


def inr(amount: float) -> str:
    """Indian grouping: 480000 -> '₹4,80,000'."""
    whole = f"{abs(round(amount)):d}"
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups) + "," + tail
    return f"{'-' if amount < 0 else ''}₹{whole}"


def hour_label(hour: int) -> str:
    return f"{(hour % 12) or 12} {'AM' if hour < 12 else 'PM'}"
