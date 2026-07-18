from app.models import Event, EventMode
from app.services import event_supports


def test_event_modes_are_explicit() -> None:
    money = Event(code="money", name="Money", mode=EventMode.money)
    coupons = Event(code="coupons", name="Coupons", mode=EventMode.coupons)
    both = Event(code="both", name="Both", mode=EventMode.both)
    assert event_supports(money, "money") and not event_supports(money, "coupons")
    assert event_supports(coupons, "coupons") and not event_supports(coupons, "money")
    assert event_supports(both, "money") and event_supports(both, "coupons")
