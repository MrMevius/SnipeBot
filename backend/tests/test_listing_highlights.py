from snipebot.domain.listing_highlights import car_highlights, drive, has_tow_hitch


def test_drive_from_title_field_or_variant() -> None:
    assert drive("Tesla Model 3 Long Range Dual Motor", {}) == "AWD"
    assert drive("Tesla Model 3 Highland", {"driveTrain": "Achterwielaandrijving"}) == "RWD"
    assert drive("Tesla Model 3", {"variant": "lr_awd"}) == "AWD"
    assert drive("Tesla Model 3", {"variant": "lr_rwd,sr"}) == "RWD"
    # The title wins over a wrongly filled field.
    assert drive("Model 3 AWD", {"driveTrain": "Achterwielaandrijving"}) == "AWD"
    assert drive("Tesla Model 3", {"variant": "lr_rwd,lr_awd"}) is None
    assert drive("Tesla Model 3 Premium", {}) is None


def test_tow_hitch_in_title_or_options() -> None:
    assert has_tow_hitch("Model 3 RWD + HW4 + Trekhaak + IAP", {})
    assert has_tow_hitch("Tesla Model 3 LR AHK Pano", {})
    assert has_tow_hitch("Tesla Model 3", {"options": "Trekhaak afneembaar"})
    assert not has_tow_hitch("Tesla Model 3 Long Range", {"options": "Panoramadak"})


def test_car_highlights_combine_platforms() -> None:
    assert car_highlights([("Model 3 LR AWD", {}), ("Model 3 met trekhaak", {})]) == ["AWD", "Tow hitch"]
    # Platforms that disagree on the drive show none.
    assert car_highlights([("Model 3 AWD", {}), ("Model 3 RWD", {})]) == []
