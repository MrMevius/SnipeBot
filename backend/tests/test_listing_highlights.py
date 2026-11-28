from snipebot.domain.listing_highlights import car_highlights, description_has_tow_hitch, drive, has_tow_hitch


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
    assert has_tow_hitch("Tesla Model 3 283CV | ATTACHE REMORQUE", {})
    assert has_tow_hitch("Tesla Model 3", {"options": "Trekhaak afneembaar"})
    assert not has_tow_hitch("Tesla Model 3 Long Range", {"options": "Panoramadak"})


def test_car_highlights_combine_platforms() -> None:
    assert car_highlights([("Model 3 LR AWD", {}, None), ("Model 3 met trekhaak", {}, None)]) == [
        "AWD",
        "Tow hitch",
    ]
    # Platforms that disagree on the drive show none.
    assert car_highlights([("Model 3 AWD", {}, None), ("Model 3 RWD", {}, None)]) == []
    assert car_highlights([("Model 3", {}, "Extra's\n- Afneembare trekhaak")]) == ["Tow hitch"]


def test_tow_hitch_in_description() -> None:
    stated = [
        "Extra's\n- MMX PACK\n- Afneembare trekhaak\n",
        "Sportvelgen\n\nTrekhaak met afneembare kogel",
        "Tevens is de auto voorzien van een trekhaak en mag 1000 kg trekken .",
        "Elektrische Heckklappe\n\nAnhängerkupplung (nicht fest)\n",
        "Kilometerbundel: 15.001 tot 20.000 km\nTrekhaak: aanwezig",
        "* Attelage d’origine Tesla",
        "Furnishing\n\nTrailer hitch\n",
    ]
    denied = [
        "Airbags: Front-Airbags\nAnhängerkupplung: --\nRadio: Radio DAB",
        "Bij montage van een trekhaak, aanhangwagen geremd: Max. 1.000 kg",
        "Helaas geen trekhaak, wel panoramadak.",
        "Verkauft ohne AHK",
        "Trekhaak: nee",
        "Trekhaak optioneel leverbaar tegen meerprijs",
        "Een trekhaak kan op verzoek worden gemonteerd.",
        "Anhängerkupplung nachrüstbar",
        None,
    ]
    assert all(description_has_tow_hitch(text) for text in stated)
    assert not any(description_has_tow_hitch(text) for text in denied)
    assert has_tow_hitch("Tesla Model 3", {}, "Opties: trekhaak, navigatie")
