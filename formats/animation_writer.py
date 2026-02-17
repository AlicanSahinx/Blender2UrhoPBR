"""Write Urho3D .ani (UANI) binary animation files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..core.logging import ExportLogger
from ..data.urho_animation import TRACK_POSITION, TRACK_ROTATION, TRACK_SCALE
from ..data.urho_model import ANIMATION_MAGIC
from .binary_writer import binary_file

if TYPE_CHECKING:
    from ..data.intermediate import IntermediateAnimation


def write_animation(anim: IntermediateAnimation, filepath: str, log: ExportLogger) -> bool:
    """
    Write an IntermediateAnimation to Urho3D .ani binary format.

    Format:
      "UANI"
      cstring: animation_name
      float: duration
      uint: track_count
      per track:
        cstring: bone_name
        ubyte: element_mask
        uint: keyframe_count
        per keyframe:
          float: time
          [vector3: position]  if mask & TRACK_POSITION
          [quaternion: rotation]  if mask & TRACK_ROTATION
          [vector3: scale]  if mask & TRACK_SCALE
    """
    if not anim.tracks:
        log.warning(f"Animation '{anim.name}' has no tracks")
        return False

    try:
        with binary_file(filepath) as w:
            # Magic
            w.write_ascii(ANIMATION_MAGIC)

            # Animation name
            w.write_cstring(anim.name)

            # Duration
            w.write_float(anim.duration)

            # Track count
            w.write_uint(len(anim.tracks))

            for track in anim.tracks:
                # Track name (bone name)
                w.write_cstring(track.name)

                # Determine element mask from keyframe data
                mask = 0
                if track.keyframes:
                    kf0 = track.keyframes[0]
                    if kf0.position is not None:
                        mask |= TRACK_POSITION
                    if kf0.rotation is not None:
                        mask |= TRACK_ROTATION
                    if kf0.scale is not None:
                        mask |= TRACK_SCALE

                w.write_ubyte(mask)

                # Keyframe count
                w.write_uint(len(track.keyframes))

                for kf in track.keyframes:
                    # Time
                    w.write_float(kf.time)

                    # Position
                    if mask & TRACK_POSITION:
                        pos = kf.position or (0.0, 0.0, 0.0)
                        w.write_vector3(pos)

                    # Rotation (quaternion wxyz)
                    if mask & TRACK_ROTATION:
                        rot = kf.rotation or (1.0, 0.0, 0.0, 0.0)
                        w.write_quaternion(rot[0], rot[1], rot[2], rot[3])

                    # Scale
                    if mask & TRACK_SCALE:
                        scl = kf.scale or (1.0, 1.0, 1.0)
                        w.write_vector3(scl)

    except Exception as e:
        log.error(f"Failed to write animation '{filepath}': {e}")
        return False

    log.info(f"Written animation: {filepath}")
    return True
