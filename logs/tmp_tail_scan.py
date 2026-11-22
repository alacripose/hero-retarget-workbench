import os
import importlib.util, sys, bpy
from pathlib import Path
ROOT=Path(ros.path.expanduser("~\Documents\deadlock-model-forge"))
P=ROOT/'blender'/'hero_retarget_workbench'
spec=importlib.util.spec_from_file_location('dmf_tmp',P/'__init__.py',submodule_search_locations=[str(P)])
m=importlib.util.module_from_spec(spec); sys.modules['dmf_tmp']=m; spec.loader.exec_module(m)
import addon_utils
addon_utils.enable('bl_ext.user_default.pulse_src_ops', default_set=False)
m.register()
s2=sys.modules['dmf_tmp.source2']
root=Path(ros.path.expanduser("~\AppData\Roaming\Blender Foundation\Blender\5.4\datafiles\hero_retarget_workbench\artifacts\extractions\werewolf\models\heroes_wip\werewolf"))
body=root/'werewolf_werewolf_model.dmx'
before={o.name for o in bpy.context.scene.objects}
s2.import_dmx(body, append='NEW_ARMATURE')
rig=max([o for o in bpy.context.scene.objects if o.name not in before and o.type=='ARMATURE'], key=lambda x:len(x.data.bones))
bpy.context.view_layer.objects.active=rig; rig.select_set(True)
for o in bpy.context.selected_objects:
    if o!=rig: o.select_set(False)
paths=sorted(list((root/'clips').glob('*.dmx'))+list((root/'dmx'/'animation').glob('*.dmx')))
found=[]
for path in paths:
    before_actions={a.name for a in bpy.data.actions}
    rig.animation_data_create().action=None
    try:
        s2.import_dmx(path, append='APPEND')
    except Exception as e:
        print('ERR',path.name,e); continue
    created=[a for a in bpy.data.actions if a.name not in before_actions]
    if not created:
        print('NOACT',path.name); continue
    act=created[0]; moved=0
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for c in bag.fcurves:
                    if 'tail_' not in c.data_path or not c.keyframe_points: continue
                    vals=[k.co[1] for k in c.keyframe_points]
                    if max(vals)-min(vals)>1e-5: moved+=1
    print('CHECK',path.name,moved)
    if moved: found.append((path.name,moved))
    bpy.data.actions.remove(act)
    rig.animation_data.action=None
print('FOUND',found[:20])
