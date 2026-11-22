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
root=Path(r'<home>\AppData\Roaming\Blender Foundation\Blender\5.4\datafiles\hero_retarget_workbench\artifacts\extractions')
for hero, rel in [('werewolf','werewolf/models/heroes_wip/werewolf/werewolf_werewolf_model.dmx'),('shiv','shiv/models/heroes_staging/shiv/shiv_body.dmx')]:
    before={o.name for o in bpy.context.scene.objects}
    s2.import_dmx(root/rel, append='NEW_ARMATURE')
    new=[o for o in bpy.context.scene.objects if o.name not in before]
    arms=[o for o in new if o.type=='ARMATURE']
    rig=max(arms,key=lambda o:len(o.data.bones))
    meshes=[o for o in new if o.type=='MESH']
    print('HERO',hero,'rig',rig.name,'bones',len(rig.data.bones),'meshes',[(o.name,len(o.data.vertices),len(o.material_slots)) for o in meshes])
    for b in ['pelvis','spine_0','tail_0','tail_1','tail_end']:
        bb=rig.data.bones.get(b)
        print('BONE',hero,b, tuple(round(v,2) for v in bb.head_local) if bb else None)
    for o in meshes:
        groups=[g.name for g in o.vertex_groups if 'tail' in g.name.lower()]
        print('MESH',hero,o.name,'tailgroups',groups,'attrs',[(a.name,a.domain,a.data_type) for a in o.data.attributes])
        if groups:
            ids={o.vertex_groups[n].index for n in groups}
            verts=[]
            for v in o.data.vertices:
                if any(g.group in ids and g.weight>0 for g in v.groups): verts.append(v.index)
            print('TAILVERTS',hero,len(verts))
            if verts:
                co=[o.matrix_world@o.data.vertices[i].co for i in verts]
                print('TAILBOUNDS', tuple(round(min(c[k] for c in co),2) for k in range(3)), tuple(round(max(c[k] for c in co),2) for k in range(3)))
                print('TAILMATS', sorted({o.data.polygons[p].material_index for p in range(len(o.data.polygons)) if any(v in set(verts) for v in o.data.polygons[p].vertices)}))
if True:
    bpy.ops.wm.quit_blender()
