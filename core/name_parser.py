"""Parse Blender object name suffixes for export behavior control.

Convention: ObjectName_suffix1_suffix2
Parse rule: split by '_', scan from RIGHT to LEFT, consume known suffixes,
stop at first unknown segment. Everything left is the clean name.

Example:
    Bush_nocol_2side_alpha  -> clean="Bush", nocol=True, two_side=True, alpha=True
    Stone_Wall_nocol        -> clean="Stone_Wall", nocol=True
    Tree                    -> clean="Tree" (no suffixes)
"""

from dataclasses import dataclass

# All recognized suffixes (lowercase)
KNOWN_SUFFIXES = frozenset({
    'nocol', '2side', 'noshadow', 'alpha',
    'occluder', 'lod1', 'lod2',
    'navmesh', 'trigger', 'billboard',
})


@dataclass(frozen=True)
class ParsedName:
    """Result of parsing an object name for export suffixes."""
    clean_name: str
    original_name: str
    nocol: bool = False
    two_side: bool = False
    noshadow: bool = False
    alpha: bool = False
    occluder: bool = False
    lod_level: int = 0       # 0 = none, 1 = _lod1, 2 = _lod2
    navmesh: bool = False
    trigger: bool = False
    billboard: bool = False

    @property
    def has_any_suffix(self) -> bool:
        return self.clean_name != self.original_name


def parse_object_name(name: str) -> ParsedName:
    """Parse a Blender object name for known suffixes.

    Splits by '_', scans from RIGHT to LEFT. Known suffixes are consumed;
    first unknown segment stops scanning. Minimum one part retained as name.
    """
    parts = name.split('_')

    found: set[str] = set()
    suffix_count = 0

    # Scan from right to left, stop at index 1 (never consume entire name)
    for i in range(len(parts) - 1, 0, -1):
        lower = parts[i].lower()
        if lower in KNOWN_SUFFIXES:
            found.add(lower)
            suffix_count += 1
        else:
            break

    clean = '_'.join(parts[:len(parts) - suffix_count]) if suffix_count else name

    lod = 0
    if 'lod1' in found:
        lod = 1
    elif 'lod2' in found:
        lod = 2

    return ParsedName(
        clean_name=clean,
        original_name=name,
        nocol='nocol' in found,
        two_side='2side' in found,
        noshadow='noshadow' in found,
        alpha='alpha' in found,
        occluder='occluder' in found,
        lod_level=lod,
        navmesh='navmesh' in found,
        trigger='trigger' in found,
        billboard='billboard' in found,
    )


def material_suffix(parsed: ParsedName) -> str:
    """Return filename suffix for material-affecting flags, or empty string.

    Only _2side and _alpha affect materials (cull mode, technique).
    """
    parts: list[str] = []
    if parsed.two_side:
        parts.append("2side")
    if parsed.alpha:
        parts.append("alpha")
    return ("_" + "_".join(parts)) if parts else ""
