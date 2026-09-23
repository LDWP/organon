from organon.core.config import GenerateOptions
from organon.core.models import Struct, TaxonInfo
from organon.modules.common import MAX_SYNONYM_HOPS, follow_synonym


def _struct() -> Struct:
    return Struct(taxon=TaxonInfo(name="Synonymus"), links={"mod": {}})


async def test_not_classification_marks_synonym_and_returns_struct():
    struct = _struct()

    async def unexpected(*_) -> str:
        raise AssertionError("must not resolve outside classification")

    handled, result = await follow_synonym(
        struct, "mod", False, GenerateOptions(), 0, unexpected, unexpected
    )

    assert (handled, result) == (True, struct)
    assert struct.links["mod"]["synonym"] is True


async def test_follow_disabled_falls_through_untouched():
    struct = _struct()

    async def unexpected(*_) -> str:
        raise AssertionError("must not follow when follow_synonyms is off")

    handled, result = await follow_synonym(
        struct, "mod", True, GenerateOptions(follow_synonyms=False), 0, unexpected, unexpected
    )

    assert (handled, result) == (False, None)
    assert struct.taxon.name == "Synonymus"
    assert "synonym" not in struct.links["mod"]


async def test_follow_replaces_taxon_and_recurses_with_next_hop():
    struct = _struct()
    seen_hops: list[int] = []

    async def resolve() -> str:
        return "Acceptus"

    async def recurse(hop: int) -> Struct:
        seen_hops.append(hop)
        return struct

    handled, result = await follow_synonym(
        struct, "mod", True, GenerateOptions(), 3, resolve, recurse
    )

    assert (handled, result) == (True, struct)
    assert struct.taxon.name == "Acceptus"
    assert seen_hops == [4]


async def test_unresolvable_accepted_name_aborts():
    async def resolve() -> None:
        return None

    async def unexpected(*_) -> Struct:
        raise AssertionError("must not recurse")

    handled, result = await follow_synonym(
        _struct(), "mod", True, GenerateOptions(), 0, resolve, unexpected
    )

    assert (handled, result) == (True, None)


async def test_synonym_loop_is_stopped_by_max_hops():
    """Two taxa pointing at each other: recursion must end with None after MAX_SYNONYM_HOPS."""
    struct = _struct()
    resolutions = 0

    async def resolve() -> str:
        nonlocal resolutions
        resolutions += 1
        return "Loopus"

    async def step(hop: int) -> Struct | None:
        handled, result = await follow_synonym(
            struct, "mod", True, GenerateOptions(), hop, resolve, step
        )
        return result if handled else struct

    assert await step(0) is None
    assert resolutions == MAX_SYNONYM_HOPS
