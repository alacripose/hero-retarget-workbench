"""Hero Retarget Workbench: live-hero retargeting and CSDK13 handoff.

The forge treats a Source 2 Viewer extraction as the source of truth. It does
not parse or rebuild the hero vmdl. The Blender addon owns the custom model,
its materials, and the skin retarget; the existing vmdl is copied unchanged.
"""

__version__ = "0.1.0"
