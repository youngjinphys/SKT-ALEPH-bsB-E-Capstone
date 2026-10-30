"""Non-privileged score input mapping (adapted from the team's v0.8 ZIP)."""
from copy import deepcopy


def adapt_data(raw, field_map=None):
    """Extract only an analysis object; never promote trusted admin lists."""
    if type(raw) is not dict:
        raise ValueError("source data must be an object")
    if field_map is not None and (type(field_map) is not dict or set(field_map) != {"analysis"}):
        raise ValueError("only analysis field mapping is permitted")
    result = {}
    if field_map is None and "analysis" in raw:
        result["analysis"] = deepcopy(raw["analysis"])
    for canonical, path in (field_map or {}).items():
        if not isinstance(path, str) or not path or len(path) > 256 or any(
            not segment or segment.startswith("_") for segment in path.split(".")
        ):
            raise ValueError("invalid field mapping path")
        value = raw
        for segment in path.split("."):
            if type(value) is not dict or segment not in value:
                raise ValueError("mapped analysis path is missing or not an object")
            value = value[segment]
        result[canonical] = deepcopy(value)
    return result
