from jarvis.core.rules import apply_rules


def test_water_query_maps_named_property():
    result = apply_rules("conta de agua kitnet 01")
    assert result["intent"] == "saneago_bills"
    assert result["params"]["property"] == "kitnet_01"


def test_energy_query_maps_commercial_room():
    result = apply_rules("conta de luz sala comercial")
    assert result["intent"] == "equatorial_bills"
    assert result["params"]["property"] == "sala_comercial"


def test_energy_query_defaults_to_house():
    result = apply_rules("fatura equatorial")
    assert result["intent"] == "equatorial_bills"
    assert result["params"]["property"] == "casa"


def test_unrelated_bill_sentence_does_not_trigger_provider_action():
    result = apply_rules("a conta da padaria ficou cara")
    assert result is None or result.get("intent") not in {"saneago_bills", "equatorial_bills"}
