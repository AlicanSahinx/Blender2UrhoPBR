"""Animation decomposition: extract bone keyframes from Blender actions."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    import bpy

from ..core.logging import ExportLogger
from ..core.types import ExportSettings
from ..data.intermediate import (
    IntermediateAnimation,
    IntermediateTrack,
    IntermediateTrackKeyframe,
)


def decompose_actions(
    armature_obj,
    scene,
    bones_map: Dict[str, int],
    settings: ExportSettings,
    log: ExportLogger,
) -> List[IntermediateAnimation]:
    """
    Decompose Blender animation actions into IntermediateAnimation list.

    Supports:
    - USED_ACTIONS: Actions referenced by NLA strips
    - ALL_ACTIONS: All actions in bpy.data.actions
    - NLA_TRACKS: NLA tracks baked
    - TIMELINE: Current scene timeline range
    """
    from mathutils import Matrix, Quaternion, Vector

    if not armature_obj.animation_data:
        log.warning(f"Armature '{armature_obj.name}' has no animation data")
        return []

    # Save state to restore later
    saved_action = armature_obj.animation_data.action
    saved_frame = scene.frame_current
    saved_use_nla = armature_obj.animation_data.use_nla

    rot_minus90_x = Matrix.Rotation(math.radians(-90.0), 4, 'X')

    # Collect actions to export
    actions_to_export = _collect_actions(armature_obj, scene, settings, log)

    if not actions_to_export:
        log.warning(f"No animations found for '{armature_obj.name}'")
        return []

    animations: List[IntermediateAnimation] = []

    try:
        armature_obj.animation_data.use_nla = False

        for action_name, frame_start, frame_end, action in actions_to_export:
            # Set the action
            if action is not None:
                try:
                    armature_obj.animation_data.action = action
                except Exception:
                    log.error(f"Cannot set action '{action_name}', skipping")
                    continue

            anim = _bake_action(
                armature_obj, scene, action_name,
                frame_start, frame_end,
                bones_map, rot_minus90_x,
                settings, log,
            )
            if anim and anim.tracks:
                animations.append(anim)
                log.info(f"Animation '{action_name}': {len(anim.tracks)} tracks, "
                         f"{anim.duration:.2f}s")

    finally:
        # Restore state
        armature_obj.animation_data.use_nla = saved_use_nla
        armature_obj.animation_data.action = saved_action
        scene.frame_current = saved_frame

    return animations


def _collect_actions(
    armature_obj,
    scene,
    settings: ExportSettings,
    log: ExportLogger,
) -> List[Tuple[str, int, int, Optional[object]]]:
    """
    Collect (name, start_frame, end_frame, action_or_None) tuples.
    """
    import bpy

    result = []
    source = settings.animation_source

    if source == 'USED_ACTIONS':
        seen = set()
        if armature_obj.animation_data:
            for track in armature_obj.animation_data.nla_tracks:
                if track.mute:
                    continue
                for strip in track.strips:
                    action = strip.action
                    if action and action.name not in seen:
                        seen.add(action.name)
                        start, end = int(action.frame_range[0]), int(action.frame_range[1] + 1)
                        result.append((action.name, start, end, action))
        # Also check current action
        current = armature_obj.animation_data.action
        if current and current.name not in seen:
            start, end = int(current.frame_range[0]), int(current.frame_range[1] + 1)
            result.append((current.name, start, end, current))

    elif source == 'ALL_ACTIONS':
        for action in bpy.data.actions:
            start, end = int(action.frame_range[0]), int(action.frame_range[1] + 1)
            result.append((action.name, start, end, action))

    elif source == 'NLA_TRACKS':
        if armature_obj.animation_data:
            for track in armature_obj.animation_data.nla_tracks:
                if track.mute:
                    continue
                start = int(scene.frame_start)
                end = int(scene.frame_end + 1)
                result.append((track.name, start, end, None))

    elif source == 'TIMELINE':
        start = int(scene.frame_start)
        end = int(scene.frame_end + 1)
        result.append(("Timeline", start, end, None))

    return result


def _bake_action(
    armature_obj,
    scene,
    action_name: str,
    frame_start: int,
    frame_end: int,
    bones_map: Dict[str, int],
    rot_minus90_x,
    settings: ExportSettings,
    log: ExportLogger,
) -> Optional[IntermediateAnimation]:
    """Bake an action by sampling every frame and extracting bone transforms."""
    from mathutils import Matrix

    armature = armature_obj.data
    fps = scene.render.fps
    frame_step = scene.frame_step

    tracks_data: Dict[str, List[IntermediateTrackKeyframe]] = {}

    for frame in range(frame_start, frame_end, frame_step):
        scene.frame_set(frame)
        time = (frame - frame_start) / fps

        for pose_bone in armature_obj.pose.bones:
            bone_name = pose_bone.name
            if bone_name not in bones_map:
                continue

            # Get bone matrix in parent space
            bone = pose_bone.bone  # rest bone
            if pose_bone.parent:
                parent_matrix = pose_bone.parent.matrix.copy()
                bone_matrix = parent_matrix.inverted() @ pose_bone.matrix
            else:
                bone_matrix = rot_minus90_x @ pose_bone.matrix

            if settings.scale != 1.0:
                bone_matrix.translation *= settings.scale

            t = bone_matrix.to_translation()
            q = bone_matrix.to_quaternion()
            s = bone_matrix.to_scale()

            # Convert to left-hand
            pos = (t.x, t.y, -t.z) if settings.export_anim_position else None
            rot = (q.w, -q.x, -q.y, q.z) if settings.export_anim_rotation else None
            scl = (s.x, s.y, s.z) if settings.export_anim_scale else None

            kf = IntermediateTrackKeyframe(
                time=time,
                position=pos,
                rotation=rot,
                scale=scl,
            )

            if bone_name not in tracks_data:
                tracks_data[bone_name] = []
            tracks_data[bone_name].append(kf)

    if not tracks_data:
        return None

    # Build animation
    duration = (frame_end - frame_start - 1) / fps
    tracks = []
    for bone_name, keyframes in tracks_data.items():
        tracks.append(IntermediateTrack(name=bone_name, keyframes=keyframes))

    return IntermediateAnimation(
        name=action_name,
        duration=max(0.0, duration),
        tracks=tracks,
    )
