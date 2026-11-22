import importlib.util, sys, bpy
from pathlib import Path
ROOT=Path(r'<home>\Documents\deadlock-model-forge')
P=ROOT/'blender'/'hero_retarget_workbench'
spec=importlib.util.spec_from_file_location('dmf_tmp',P/'__init__.py',submodule_search_locations=[str(P)])
m=importlib.util.module_from_spec(spec); sys.modules['dmf_tmp']=m; spec.loader.exec_module(m)
import addon_utils
addon_utils.enable('bl_ext.user_default.pulse_src_ops', default_set=False)
m.register()
s2=sys.modules['dmf_tmp.source2']
body=Path(r'<home>\AppData\Roaming\Blender Foundation\Blender\5.4\datafiles\hero_retarget_workbench\artifacts\extractions\werewolf\models\heroes_wip\werewolf\werewolf_werewolf_model.dmx')
clip=Path(r'<home>\AppData\Roaming\Blender Foundation\Blender\5.4\datafiles\hero_retarget_workbench\artifacts\extractions\werewolf\models\heroes_wip\werewolf\clips\aim_weapon_idle.dmx')
before={o.name for o in bpy.context.scene.objects}
s2.import_dmx(body, append='NEW_ARMATURE')
rig=max([o for o in bpy.context.scene.objects if o.name not in before and o.type=='ARMATURE'], key=lambda x:len(x.data.bones))
bpy.context.view_layer.objects.active=rig
rig.select_set(True)
for o in bpy.context.selected_objects:
    if o!=rig: o.select_set(False)
before_actions={a.name for a in bpy.data.actions}
rig.animation_data_create().action=None
s2.import_dmx(clip, append='APPEND')
created=[a for a in bpy.data.actions if a.name not in before_actions]
print('RIG', rig.name, 'ACTIONS', [(a.name, len(a.slots), len(a.layers)) for a in created])
act=created[0]
print('SLOTS', [(getattr(s,'identifier',''), getattr(s,'target_id_type','')) for s in act.slots])
for layer in act.layers:
    for strip in layer.strips:
        for bag in strip.channelbags:
            curves=list(bag.fcurves)
            print('BAG', bag.slot_handle, len(curves))
            for c in curves:
                if 'tail_0' in c.data_path:
                    print('CURVE', c.data_path, c.array_index, len(c.keyframe_points), [(round(k.co[0],1),round(k.co[1],4)) for k in list(c.keyframe_points)[:4]])
rig.animation_data.action=act
rig.animation_data.action_slot=act.slots[0]
for f in (0,30,60):
    bpy.context.scene.frame_set(f)
    bpy.context.view_layer.update()
    for name in ('tail_0','tail_1','tail_2','tail_3','tail_4','tail_5','tail_end'):
        pb=rig.pose.bones.get(name)
        print('POSE',f,name, [round(v,4) for row in pb.matrix_basis for v in row] if pb else None)
