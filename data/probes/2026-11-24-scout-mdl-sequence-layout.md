# 2026-11-24 — decoder probe: the sequence table in scout.mdl

## F:\Documents\scout.mdl

- size 910028, version 48, header {'numlocalanim': 2, 'localanimindex': 21876, 'numlocalseq': 306, 'localseqindex': 23352}
- labels: {'PRIMARY_aimmatrix_idle': 895495, 'PRIMARY_aimmatrix_run': 895518, 'AttackStand_PRIMARY': 895570, 'PRIMARY_reload_loop': 895771}
- sequence table byte size from header: 64872 (212-byte descriptor)

- ints at localseqindex (23352): [-23352, 872071, 870896, 0, -1, 0, 0, 64872, -1046861095, -1048287443]
- int at +28 (numlocalseq*212?): 64872 vs 64872

- descriptor-relative label hits: {'PRIMARY_aimmatrix_idle': [], 'PRIMARY_aimmatrix_run': [], 'AttackStand_PRIMARY': [], 'PRIMARY_reload_loop': []}
- most common (label_abs - int_value) bases: [(895516, 1122), (895494, 999), (895517, 995), (895569, 990), (895770, 988), (895493, 777)]
- best (score, stride, start) pointing into the label cluster: [(18, 212, 26752), (18, 212, 26540), (18, 212, 26328), (18, 212, 26116), (18, 212, 25904), (18, 212, 25692)]

## F:\Documents\scout_animations.mdl

- size 5017436, version 48, header {'numlocalanim': 1012, 'localanimindex': 17508, 'numlocalseq': 377, 'localseqindex': 4841760}
- labels: {'PRIMARY_aimmatrix_idle': 4977633, 'PRIMARY_aimmatrix_run': 4978018, 'AttackStand_PRIMARY': 4978853, 'PRIMARY_reload_loop': 4979080}
- sequence table byte size from header: 79924 (212-byte descriptor)

- ints at localseqindex (4841760): [-4841760, 162833, 134436, 0, -1, 0, 0, 79924, -1046722934, -1058600102]
- int at +28 (numlocalseq*212?): 79924 vs 79924

- descriptor-relative label hits: {'PRIMARY_aimmatrix_idle': [], 'PRIMARY_aimmatrix_run': [], 'AttackStand_PRIMARY': [4716708], 'PRIMARY_reload_loop': []}
- most common (label_abs - int_value) bases: [(4978852, 5439), (4977632, 5435), (4978017, 5433), (4979079, 5432), (4977629, 2928), (4978014, 2925)]
- best (score, stride, start) pointing into the label cluster: [(16, 212, 4843888), (16, 212, 4840284), (15, 212, 4847492), (15, 212, 4836680), (14, 212, 4851520), (14, 212, 4851096)]

