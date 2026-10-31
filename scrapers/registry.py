from importlib import import_module
from types import ModuleType


# A None module path marks a reserved adapter choice that is not implemented yet.
ADAPTERS = {
    "altis": ("Altis", "scrapers.altis"),
    "ashby": ("Ashby", "scrapers.ashby"),
    "avature": ("Avature", "scrapers.avature"),
    "ultipro": ("UltiPro / UKG", "scrapers.ultipro"),
    "workday": ("Workday", "scrapers.workday"),
    "bamboohr": ("BambooHR", "scrapers.bamboohr"),
    "oracle_hcm": ("Oracle Recruiting Cloud", "scrapers.oracle_hcm"),
    "jobbank": ("Job Bank (Atom feed)", "scrapers.jobbank"),
    "erecruit": ("Virtuo HR eRecruit (RSS feed)", "scrapers.erecruit"),
    "greenhouse": ("Greenhouse", "scrapers.greenhouse"),
    "jsearch": ("JSearch (OpenWeb Ninja)", "scrapers.jsearch"),
    "successfactors": ("SuccessFactors", "scrapers.successfactors"),
    "phenom": ("Phenom", "scrapers.phenom"),
    "workable": ("Workable", "scrapers.workable"),
    "tigeranalytics": ("Tiger Analytics", "scrapers.tigeranalytics"),
    "jazzhr": ("JazzHR", "scrapers.jazzhr"),
    "rippling": ("Rippling", "scrapers.rippling"),
    "risepeople": ("Rise People", "scrapers.risepeople"),
    "lever": ("Lever", None),
    "html": ("Plain HTML page", None),
    "browser": ("Browser-rendered page", None),
    "linkedin": ("LinkedIn search", None),
}

ADAPTER_CHOICES = tuple(
    (name, label) for name, (label, _module_path) in ADAPTERS.items()
)


def get_adapter(name: str) -> ModuleType | None:
    """Load an implemented adapter module; return None for reserved or unknown names."""
    definition = ADAPTERS.get(name)
    if definition is None:
        return None
    _label, module_path = definition
    return import_module(module_path) if module_path else None
