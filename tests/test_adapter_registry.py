from scrapers.registry import ADAPTERS, ADAPTER_CHOICES, get_adapter


def test_all_registered_adapter_choices_are_preserved():
    assert {name for name, _label in ADAPTER_CHOICES} == {
        "ultipro",
        "workday",
        "bamboohr",
        "oracle_hcm",
        "jobbank",
        "erecruit",
        "greenhouse",
        "successfactors",
        "phenom",
        "workable",
        "lever",
        "html",
        "browser",
        "linkedin",
    }


def test_implemented_adapters_load_and_reserved_adapters_remain_unimplemented():
    for name, (_label, module_path) in ADAPTERS.items():
        adapter = get_adapter(name)
        if module_path:
            assert adapter is not None
            assert callable(adapter.fetch_list)
            assert callable(adapter.fetch_detail)
        else:
            assert adapter is None


def test_unknown_adapter_name_returns_none():
    assert get_adapter("unknown") is None
