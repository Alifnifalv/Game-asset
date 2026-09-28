"""Clip family modules, auto-discovered by tools/calf_animations.py: every tools/clips/*.py whose name does not start
with "_", imported in sorted filename order after the imported clips (Eating, Idle) and the gaits. Each exposes
build(calf) -> list[str] (the action names it created; imported_fix repairs Idle/Eating in place and returns []) and has a
standalone __main__ that builds on build/stage_b.blend, prints its QA and takes an output location and a no-render flag.
Primitives: tools/anim_lib.py (Pose, keyed_pose_fn, ground_stance, Calf.make_clip). See CLAUDE.md "Extending"."""
