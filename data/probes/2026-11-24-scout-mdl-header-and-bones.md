# 2026-11-24 — decoder probe: scout.mdl header, bones, and the bytes at localseqindex

- size 910028, version 48, name player/hwm/scout.mdl
- numbones 78 @ 664, numlocalseq 306 @ 23352

## bone table

- bone 0 @ 664: sznameindex 893612, desc-relative 'bip_pelvis', absolute '', parent -1
- bone 1 @ 880: sznameindex 893407, desc-relative 'bip_spine_0', absolute '', parent 0
- bone 2 @ 1096: sznameindex 893203, desc-relative 'bip_spine_1', absolute '', parent 1
- bone 3 @ 1312: sznameindex 892999, desc-relative 'bip_spine_2', absolute '7', parent 2
- bone 4 @ 1528: sznameindex 892795, desc-relative 'bip_spine_3', absolute '7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7', parent 3
- bone 5 @ 1744: sznameindex 892591, desc-relative 'bip_neck', absolute '7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7m\x11I7', parent 4

## bytes at localseqindex

- ints at 23352: [-23352, 872071, 870896, 0, -1, 0, 0, 64872, -1046861095, -1048287443, -1067421310, 1087583545, 1099196208, 1118178766, 1, 65184]
- floats at 23352: [nan, 0.0, 0.0, 0.0, nan, 0.0, 0.0, 0.0, -19.2709, -16.5504, -3.5069, 6.6002, 16.5504, 83.027, 0.0, 0.0]
- int at +28: 64872 (numlocalseq*212 = 64872)

## descriptor candidate at localseqindex, field by field

- +0   szlabelindex         -23352
- +4   szactivitynameindex  872071
- +8   flags                870896
- +12  activity             0
- +16  actweight            -1
- +20  numevents            0
- +24  eventindex           0
- +52  numblends            1118178766
- +56  animindexindex       1
- +60  movementindex        65184
- +92  fadeintime           0
- +96  fadeouttime          0
- +120 lastframe            0
- +124 nextseq              0
- +128 pose                 0

## same fields 4 bytes earlier (if the block starts before the descriptor)

- +0   szlabelindex         0
- +4   szactivitynameindex  -23352
- +8   flags                872071
- +12  activity             870896
- +16  actweight            0
- +20  numevents            -1
- +24  eventindex           0
- +52  numblends            1099196208
- +56  animindexindex       1118178766
- +60  movementindex        1
- +92  fadeintime           0
- +96  fadeouttime          0
- +120 lastframe            0
- +124 nextseq              0
- +128 pose                 0
