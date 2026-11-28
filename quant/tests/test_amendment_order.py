"""Amendments are applied in numeric order (A10 follows A9)."""

from quantlab import protocol


def test_amendments_load_in_numeric_order():
    ids = [a["id"] for a in protocol.load_amendments()]
    nums = [int(i[1:]) for i in ids]
    assert nums == sorted(nums) and ids[-1] == f"A{max(nums)}" and len(set(ids)) == len(ids)
    assert ids.index("A10") > ids.index("A9") > ids.index("A2")
