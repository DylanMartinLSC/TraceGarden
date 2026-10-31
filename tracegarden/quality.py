"""Versioned public quality profile, selected from the graph-seed experiments."""

HIGH_TUNING = {
    "region_merge_threshold": 256.0,
    "region_seed_colors": 128,
    "region_merge_mode": "ms",
    "region_seed_scale": 20.0,
    "region_seed_sigma": 0.5,
}
HIGH_DEFAULTS = {
    "preset": "auto",
    "layering": "auto",
    "geometry": True,
    "gradients": True,
    "speckle": 0,
    "corner": 45,
    "precision": 6,
}


def resolve_options(options):
    """Supply profile defaults while retaining explicit controls and limits."""
    if options.quality != "high" or options.preset in {"ink", "centerline", "pixel"}:
        return options
    return options.model_copy(
        update={
            key: value
            for key, value in HIGH_DEFAULTS.items()
            if key not in options.model_fields_set
        }
    )


def describe(mode, result):
    if mode == "fast":
        return {"mode": mode, "profile": "fast", "status": "applied", "message": "Fast"}
    region = result.get("analysis", {}).get("region_merging", {})
    if region.get("applied"):
        status, message = "applied", "High Quality · detail enhancement applied"
    elif "budget exceeded" in region.get("reason", ""):
        status = "fallback"
        message = "High Quality · standard color processing used because detail enhancement reached its work limit."
    else:
        status = "not_applicable"
        message = "High Quality · standard color processing used for transparency, a custom palette or this artwork style."
    return {
        "mode": mode,
        "profile": "graph-fidelity-v1",
        "status": status,
        "message": message,
    }
