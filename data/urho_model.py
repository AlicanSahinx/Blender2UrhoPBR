"""Urho3D model constants and output data structures."""

# --- Element mask flags (matching Urho3D engine) ---
ELEMENT_POSITION = 0x0001   # 3 x float32
ELEMENT_NORMAL   = 0x0002   # 3 x float32
ELEMENT_COLOR    = 0x0004   # 4 x uint8 (RGBA)
ELEMENT_UV1      = 0x0008   # 2 x float32
ELEMENT_UV2      = 0x0010   # 2 x float32
ELEMENT_TANGENT  = 0x0080   # 4 x float32 (xyz + bitangent sign)
ELEMENT_BWEIGHTS = 0x0100   # 4 x float32
ELEMENT_BINDICES = 0x0200   # 4 x uint8
ELEMENT_BLEND    = ELEMENT_BWEIGHTS | ELEMENT_BINDICES

# Morph targets can only modify these elements
MORPH_ELEMENTS = ELEMENT_POSITION | ELEMENT_NORMAL | ELEMENT_TANGENT

# Bytes per element component
ELEMENT_SIZES = {
    ELEMENT_POSITION: 12,   # 3 * 4
    ELEMENT_NORMAL:   12,   # 3 * 4
    ELEMENT_COLOR:     4,   # 4 * 1
    ELEMENT_UV1:       8,   # 2 * 4
    ELEMENT_UV2:       8,   # 2 * 4
    ELEMENT_TANGENT:  16,   # 4 * 4
    ELEMENT_BWEIGHTS: 16,   # 4 * 4
    ELEMENT_BINDICES:  4,   # 4 * 1
}

# --- Animation track mask ---
TRACK_POSITION = 0x01
TRACK_ROTATION = 0x02
TRACK_SCALE    = 0x04

# --- Bone collision ---
BONE_BOUNDING_SPHERE = 0x01
BONE_BOUNDING_BOX    = 0x02

# --- Primitive types ---
PRIMITIVE_TRIANGLE_LIST = 0
PRIMITIVE_LINE_LIST     = 1

# --- Skinning limits ---
MAX_SKIN_MATRICES = 64
BONES_PER_VERTEX  = 4

# --- File magic numbers ---
MODEL_MAGIC     = "UMDL"
ANIMATION_MAGIC = "UANI"


def compute_element_mask(
    has_position: bool = True,
    has_normal: bool = False,
    has_color: bool = False,
    has_uv1: bool = False,
    has_uv2: bool = False,
    has_tangent: bool = False,
    has_weights: bool = False,
) -> int:
    """Compute element mask from feature flags."""
    mask = 0
    if has_position:
        mask |= ELEMENT_POSITION
    if has_normal:
        mask |= ELEMENT_NORMAL
    if has_color:
        mask |= ELEMENT_COLOR
    if has_uv1:
        mask |= ELEMENT_UV1
    if has_uv2:
        mask |= ELEMENT_UV2
    if has_tangent:
        mask |= ELEMENT_TANGENT
    if has_weights:
        mask |= ELEMENT_BLEND
    return mask


def vertex_size_from_mask(mask: int) -> int:
    """Calculate vertex byte size from an element mask."""
    size = 0
    for flag, byte_count in ELEMENT_SIZES.items():
        if mask & flag:
            size += byte_count
    return size
