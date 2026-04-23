"""Future integration: design → Maestro — scaffold only."""


def generate_tests_from_figma(figma_json: dict) -> str:
    """
    Future: Convert Figma design JSON to Maestro YAML / flow specs.

    This repository currently drives tests from hand-authored YAML under flows/.
    When implemented, map frames + components to Maestro `tapOn` / `assertVisible` plans.
    """
    raise NotImplementedError(
        "Figma → Maestro generation is not enabled in this build. "
        f"Payload keys sample: {list((figma_json or {}).keys())[:5]}"
    )
