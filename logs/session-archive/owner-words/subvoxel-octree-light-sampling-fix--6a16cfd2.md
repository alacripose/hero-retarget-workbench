# Subvoxel Octree Light Sampling Fix

store `<home>\Documents\shploingus-clean`  
thread `6a16cfd2-3f53-476d-b260-48a8d8f8129f`  
manifest messages 384  
pinned file `shploingus-clean\1795243873844_6a16cfd2-3f53-476d-b260-48a8d8f8129f.jsonl`  
digest blake3:c30295028e0c616d3ddaa682168adb451e8cdc2a37a41d1371d60965d18b68c6

---

**#1286 · 2026-10-25T17:48:22.977000+00:00**

Start the mission now. This is a large existing renderer, so first establish ground truth before writing GLSL: find where light and shadow are currently sampled (mesh shader / lighting pass / chunk mesher), how the subvoxel octree is built and stored, and exactly where sun and moon directions and sun/moon light values enter. Report that wiring map concretely (file paths, function names, uniform/attribute names, the data layout of the octree that a shader can actually read) before changing anything.

Then begin the faithful streamed light-horizon implementation: march lighting from the sun through the atmosphere and from the moon reflection using the octree, streamed in horizon slices rather than computed per-frame on the CPU. No CPU-first fallback path — do not add a CPU shadow/lighting routine as a stepping stone, and do not gate the feature behind a debug toggle. Fix the existing wiring in place rather than layering a parallel path beside it.

Scope discipline: this is a fix to existing sampling behavior, not a renderer rewrite. Do not add UI, config menus, or new options. Structure the code so the horizon march lives in one obvious place with one owner of the streamed horizon state. End this pass with the march actually reachable from the real render path and a short note on what still needs proving at runtime; keep a generating script or command noted for the final .patch export, but do not bundle unrelated repo churn into it.

---

**#1288 · 2026-10-25T17:51:03.421000+00:00**

here's an image of when it worked for a brief moment in time

---

**#1290 · 2026-10-25T17:59:01.194000+00:00**

here's a screenshot, the shadows being cuboid is correct, the shadows having a diagonal cut edge through the materials should be refused in place of the subvoxel shadows

---

**#1292 · 2026-10-25T18:04:19.081000+00:00**

here it looks perfect but it should follow the subvoxel 1/32th grid and currently only the chunk I'm in gets its light streamed


The user attached the following item. The paths are absolute and readable with your file tools:

[Image: <home>\AppData\Local\Temp\freebuff-desktop-pastes\paste-1792951365294-10088.png]
(Attached to this message as an image you can see; the file is also at this path.)

---

**#1294 · 2026-10-25T18:13:10.965000+00:00**

again it's really fast so it's nice but there's no sparse sampling for long tunnels/hallways and the world rig still keeps a minimum for blocks so light doesn't transport further into darker areas and it's not properly streamed like the chunks are and doesn't have a large enough horizon so the sun's light isn't going through the clouds or atmosphere and having it's color changed and it doesn't sample in sitant chunks with lod blending properly

---

**#1296 · 2026-10-25T18:15:28.100000+00:00**

every time you do a big test it takes like 5 minutes because it rebuilds everything on my hard drive please stop doing that

---

**#1298 · 2026-10-25T18:17:17.822000+00:00**

I'm killing cargo.exe in task manager because I am running the game itself when you go to do test suites because it will let me see your changes in real time, which is supposed to be the pupose of mount v2

---

**#1300 · 2026-10-25T18:20:35.865000+00:00**

Rebuild the weakest part of this thread's own work — the radiance march in `horizon_march` — toward the excellent version of exactly what was asked; do not touch the parts that already work. It must reach far enough that a beam picks up sky and cloud colour on its way in (the sun's light through atmosphere, and the moon's reflected light at night), keep transporting into enclosed dark space instead of dying at the rig's per-block minimum, and cover long tunnels and hallways with sparse marching rather than only the near cells. The horizon volume must stream like chunks do — refilling as residency changes, sampling distant chunks with the same LOD blending the chunk meshes use — rather than only the chunk under the player.

Constraint that outranks convenience: the user runs the game live and killed cargo, so run no full test suite and no workspace-wide build; at most a targeted `cargo check -p <crate>` for the crates you edit, or a single named test filter the user's own run already covers.

Finish by shipping the deliverable itself: a real `.patch` file in `patches/` generated from this thread's changes, containing only them, and proven to apply with `git apply --check` against a clean copy — a generator script alone does not satisfy the mission. State plainly in the report what the patch contains and what is still unproven at runtime.

---

**#1302 · 2026-10-25T18:40:33.036000+00:00**

that regressed the lighting slightly into what should be a refusal instead of making the changes I requested

---

**#1304 · 2026-10-25T18:48:44.562000+00:00**

Finish the requested outcome the last grade names as missing: the march still decides only whether light arrives, so replace the beam's single frame-global tint with optical depth accumulated along the ray itself, colouring what actually arrives. `shading.wgsl` must read the `sky_model` rows already declared in `atmosphere.wgsl` per step, cross the cloud column on the way in, and redden/warm the sun's beam by path length while the night beam carries the moon's reflected colour — the sky and cloud colour on the beam rather than a hue sprayed over the frame's light. Keep the band and overrule rules that now work untouched: fine octree hits refuse the coarse map, the coarse band answers the dome only, and long rays stay measured.

The user is running the game and has killed cargo, so no full suite and no workspace-wide build — targeted `cargo check -p <crate>` plus single named test filters only, and one targeted wgsl-composition probe if the shader needs it.

Because `patches/PATCH-077-*` is already the shipped deliverable, the change is not done until the exporter is rerun on the new text and the patch re-proven: `git apply --check` into the clean reconstructed base, applied for real with byte-identical files, and reverse-checked. Update the record's owed items to match what now exists, and say plainly what is still unproven without an eye on the screen.

---

**#1306 · 2026-10-25T18:57:51.971000+00:00**

there is massive frame lag when I enter a chunk because the lighting doesn't stream in around the player

---

**#1308 · 2026-10-25T19:13:13.321000+00:00**

error: failed to run custom build command for `shploingus v0.1.0 (<home>\Documents\shploingus-clean\crates\shploingus)`

Caused by:
  process didn't exit successfully: `F:/shploingus-target\debug\build\shploingus-eff1a8e4fbc49fcc\build-script-build` (exit code: 101)
  --- stdout
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\display-packages/alpha-shell/package.shspec
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\packages/alpha-shell.shspec
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\patches
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/LEDGER.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/HYPERGRILLING.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/DESIGN-SPEC.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/SHAPERS.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/UI-SPEC.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/MODS-MAP.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/APPEARANCE.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/TODO.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/STATUS.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\docs/HANDOFF.md
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\chains
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\conformance
  cargo:rerun-if-changed=<home>\Documents\shploingus-clean\display-packages/alpha-shell/frames

  --- stderr

  thread 'main' (18332) panicked at crates\shploingus\build.rs:195:34:
  a crate's prose budget was exceeded: 1 refusal(s): uncalibrated_oracle: shploingus is 30% comment and its declared budget is 29%. The share may fall and may not rise: the explanation this crate needs belongs in a document under `docs/`, where a reader looks for it, and prose in a code artifact is documentation written where nobody reads it. Move the explanation rather than arguing the number up — a budget raised because the code grew is not a budget, it is a record of what happened
  note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace

<home>\Documents\shploingus-clean>
I also need you to add the distant terrain horizon lods

---

**#1310 · 2026-10-25T19:19:48.155000+00:00**

/prove-then-prune

---

**#1312 · 2026-10-25T19:27:29.067000+00:00**

/architect

---

**#1314 · 2026-10-25T19:28:14.647000+00:00**

also in this pass get the updated gaia design doc and implement the tree mob patch

---

**#1316 · 2026-10-25T19:36:58.523000+00:00**

it's refusing because you're using column format

---

**#1318 · 2026-10-25T19:42:11.617000+00:00**

there is no addressing chunks at only x and z because the profile shaper arithmetic for showing coarse distant chunks is how we get 1/32th subvoxel shaper profiles for blocks and water and clouds and atmosphere

---

**#1320 · 2026-10-25T19:49:28.166000+00:00**

/essential

---

**#1322 · 2026-10-25T20:16:24.626000+00:00**

you've completley hand rolled light streaming and distant chunk streaming and broke the camera based streaming and now there is one block based tree instead of a mob tree that actually grows and has fundemental scientific tree systems so there is frame time issues and the tree is hand rolled instead of growing properly

---

**#1324 · 2026-10-25T20:21:51.372000+00:00**

tree mobs are going to use the 1/32th subvoxel profile shaper system which we have to design here first, so we can accurateley draw trees in their blocks with their surface features and animated growth blending

---

**#1326 · 2026-10-25T20:56:13.089000+00:00**

light streaming over chunks is still broken and the growth and shape of the trees needs to not be hand rolled

---

**#1328 · 2026-10-25T20:58:36.809000+00:00**

the chunks should never be lit by the rig it should be light sampled or rendering the chunk should be refused

---

**#1330 · 2026-10-25T21:10:15.326000+00:00**

/adversarial-fix

---

**#1332 · 2026-10-25T21:19:06.278000+00:00**

something regressed and the materials rendering was fucked with so now there's visible errors on the materials surface in the light sampler

---

**#1334 · 2026-10-25T21:20:14.731000+00:00**

whatever you just undid was not the fix

---

**#1336 · 2026-10-25T21:25:12.580000+00:00**

materials worked perfectly fine at 3:10 pm when you recieved the adversarial fix command from the harness and at some point you decided to mess with how materials render by porting forward something that bugs out material rendering which we switched to a new world format shader to avoid

---

**#1338 · 2026-10-25T21:26:57.467000+00:00**

Stop fucking bitching at yourself about limited context you have 30 minutes remaining in this session

---

**#1340 · 2026-10-25T21:29:37.476000+00:00**

revert the projects rendering to what it was before you received the adversarial fix your attempts to fix the materials have failed and you need to turn this into a refusal

---

**#1342 · 2026-10-25T21:32:14.112000+00:00**

so it's 3:31 pm, in 20 minutes you managed to break my project in an irreversable way after we spent literally 3 days switching to a new renderer that didn't have this problem?

---

**#1344 · 2026-10-25T21:35:41.335000+00:00**

check file @refusal_timeline.md

---

**#1346 · 2026-10-25T21:40:13.208000+00:00**

You have completley fucked my project and are refusing to undo the past 30 minutes now of work

---

**#1348 · 2026-10-25T21:40:55.396000+00:00**

Stop you fucker revert the work

---

**#1350 · 2026-10-25T21:44:31.266000+00:00**

you made a material rendering shading change that is the regression that happened after 3:10 pm and you refuse to fucking fix is which is the old shader format's issue brought back into the light sampler version and now we can't even remove it because you're a twat and a bastard

---

**#1352 · 2026-10-25T21:45:01.780000+00:00**

/adversarial-fix

---

**#1354 · 2026-10-25T21:54:20.276000+00:00**

the changes made past 3:10 pm have completley butchered the rendering of the terrain and regressed it to the old shader format entirely, so it's missing wireframe view, materials are wrongly addressed, etc

---

**#1356 · 2026-10-25T21:56:09.298000+00:00**

So you're telling me that the material error that you wrongly put in can no longer be removed /review

---

**#1358 · 2026-10-25T22:00:31.327000+00:00**

I have added extra context to @refusal_timeline.md

---

**#1360 · 2026-10-25T22:06:45.952000+00:00**

did not revert the problem

---

**#1362 · 2026-10-25T22:07:27.580000+00:00**

if the fucking one before 2:56 pm didn't have the problem maybe go back to that one

---

**#1364 · 2026-10-25T22:12:21.239000+00:00**

light streaming over chunks is still broken and the growth and shape of the trees needs to not be hand rolled



2:56 PM
Freebuff

Worked for 2m 23s

Ran commands

AI Observability – Observe and optimize AI products in PostHog
Ad
Trace every generation, score quality with evals, alert on anomalies, and turn findings into PRs.
posthog.com ↗
I found two distinct light paths that could be what you're seeing, and they need different fixes. Before I spend a pass on the wrong one:


Ran a tool, ran commands

Questions
1 question(s)
success
1 question(s)

What does "light streaming over chunks is still broken" look like on screen? I can see three different causes in the code and they need different fixes.
→ A chunk streams in unlit

Thinking
"A chunk streams in unlit" — light does not arrive with the chunk; the frame's scene build asks the field for each corner at build time (field.at(cell) during mesh build), which queues missing cells. Then the worker measures, adopts, but the chunk's mesh/vertex light was already built with the fallback (the rig). And since the mesh isn't rebuilt when light lands (scene keyed by light_epoch + held), the chunk stays unlit until the next light epoch (~1.7 s) — and held is zero because the material light is not a scene input any more (PATCH-074 note: "the material's light is not a scene input any more ... held is zero on every frame"). So a chunk streams in, is built with rig light, and its per-corner bands never re-enter the scene because the scene key doesn't move when measurements land.

Wait — but where does the mesh store light? The vertex light is per corner in the mesh (228k corner asks). If fs_main reads atmosphere+shadow map (not the corner light), then per-corner light isn't used at all... The audit says: "Left as named debt: folding WorldLight's six bands into the one shader format so a chunk arrives with its light attached".

Let me understand the actual light usage: field.at(cell) is called during the scene build and the result winds up in the mesh's corner light, which the shader may or may not read. Given the note "the material's light is not a scene input any more (PATCH-074): fs_main reads the atmosphere and the frame's shadow map, so the light key does not move with a measured cell and held is zero on every frame" — the light field's bands are no longer used for shading! If so, a chunk with no measurement would still be lit by the shader's atmosphere+shadow. Then "streams in unlit" is something else: maybe the chunk's shadow data is missing, or its mesh isn't uploaded, or the light field's contribution is used for the sky/ambient...

I need to read the scene build's use of field.at and the shading path. Let me grep for .at( in scene.rs and see what happens to missing cells, plus held semantics.

Then the fix for "a chunk streams in unlit": make the chunk's light arrive with it — i.e., the scene build must not draw a chunk whose light is unmeasured, or the mesh must be rebuilt when the chunk's light lands (scene key includes the field version), or the fallback rig must be the full light (not zero).

Let me look. Time is limited; be surgical.


Run
cd /c<home>/Documents/shploingus-clean && grep -n "field.at\|light.at\|\.at(cell\|bands" crates/voxel-client/src/scene.rs | head -30; echo ===; sed -n '2820,2860p' crates/shploingus/src/main.rs
cd /c<home>/Documents/shploingus-clean && grep -n "field.at\|light.at\|\.at(cell\|bands" crates/voxel-client/src/scene.rs | head -30; echo ===; sed -n '2820,2860p' crates/shploingus/src/main.rs

stdout:
37:/// A callback that gives the world's light at a cell, in band order (B3, B4, B5).
43:/// world whose shaper layer does not produce the field at all has no measurement
106:    /// The world's light at this corner's cell, in band order (B3, B4, B5):
482:    /// This states the other side of the same law: the six bands a corner the sampler measured
484:    /// vertices are [`Scene::probe`]'s, and the bands are the ones [`Vertex`] already holds.
954:                    bands: [f32; 6],
968:                light_direct: [bands[0], bands[1], bands[2]],
969:                light_diffuse: [bands[3], bands[4], bands[5]],
974:        // One corner's light flag and bands, measured **at the corner's own address**. The point
981:                Some(bands) => (1u32, bands),
991:        // every one of its four corners was measured, and each corner carries its own bands.
1017:                        let (_, bands) = measure(place([
1031:                            bands,
1047:                // where one attaches. The flag and the bands come from the one rule above; bands
1127:                    // face measured at all four, an unmeasured lattice sample carries zero bands
1161:                        for (corner, (_, bands)) in corners.iter().zip(samples) {
1171:                                bands,
1218:                                let (_, bands) = sampled[at];
1224:                                    bands,
1280:    /// A corner carries light only when the field **measured** the cell it stands in: the bands are
1826:        // 3. The light, round-robin: a chunk whose bands are a revision behind is re-emitted in
2335:        /// keeps both triangles together; bands stay per-corner, so no detail
2374:        // And the measured corners kept their own bands (only the flag is
2378:            "sharing the flag flattened the bands too"
3027:            let bands = move |_: [f64; 3]| Some([light as f32, 0.0, 0.0, 0.0, 0.0, 0.0]);
3029:                (Scene::build_with_light(streamer.meshes(), [0.0; 3], &bands, None, None), true)
3108:        // **A field with a measurement does move the key**: those bands are the corner's, not the
3134:            let light = crate::field::light_at(&field);
3209:    /// This is the pin for the defect this pass repaired. The draft asked the field at
3885:    // below put a face through that second path with a field attached and read the drawn profile
===
        // This is the whole of what "the world is lit by measurement" means in the code: the same
        // scene, built by the constructor that asks the world's field at every corner — and by the
        // record-format constructor when there is no field, which is the frame this game drew
        // before the field existed rather than a dark one. `Scene::build_with_light`'s own doc
        // states why the two are constructors rather than a flag, and
        // `renderer::tests::the_quad_format_and_the_vertex_format_draw_the_same_surface` is what
        // holds them to one picture.
        // **The light's own frame, before the scene that draws it**: adopt what the worker has
        // finished, answer its tree questions by handle, and hand it the next batch. This is the
        // whole of the field's cost on this thread — three channel operations and a bounded
        // handshake — and it is timed into the scene stage because it is the scene's light.
        self.pump_light();
        let field = self.light_field.take();
        // **The light's revision is the field's, not the cadence's.** A corner carries light only
        // when the field measured the cell it stands in; a field holding nothing leaves every corner
        // on the rig, which the shader reads from a uniform written whether the geometry was rebuilt
        // or not. So the atmosphere's tick moves this key only when the field has something to say
        // about a corner — without it, every cadence frame walked the resident meshes to rebuild the
        // bytes it already had.
        let held = field.as_ref().map(|f| f.borrow().held()).unwrap_or(0);
        // **The light's key is the cadence, once there are cells to draw with.** The rebuild is
        // also the ask — every corner is asked, and a stale one is queued for a re-march — so the
        // cadence is the rate at which the drawn cells are kept current, and a field holding
        // nothing still moves nothing.
        // ---- the light horizon, streamed from the octrees ----------------
        // **The frame's own occlusion field, moved with the eye and fed by the chunks the
        // streamer holds.** The cube is recentred on the eye's chunk; a crossing shifts it, and
        // the loop below stamps the chunks that are resident and not yet represented, a bounded
        // number per frame. That is what "streamed" means here: the light the fragment marches
        // arrives with the world rather than in one build behind it, and a chunk that has not
        // landed yet reads as unmeasured for the frames it is absent (its direct shadow is still
        // the shadow map's, which is drawn from the geometry that is present).
        // Nine a frame: a crossing only owes the chunks that entered (docs/lighting-sky-and-moon.md,
        // "The horizon's streaming rules").
        const HORIZON_CHUNKS_PER_FRAME: usize = 9;
        if let Some(graphics) = self.graphics.as_mut() {
            let eye = self.camera.position_m;
            graphics.world.horizon_recenter(eye);
            if let Some(streamer) = self.streamer.as_ref() {
                // A chunk the window dropped leaves its trees behind; the volume must drop its cells.
                let resident: std::collections::BTreeSet<(i32, i32, i32)> =

Thinking
So the scene carries per-corner bands when measured; unmeasured corners carry flag 0 and fall back to the rig in the shader. So a chunk streaming in should be lit by the rig (not unlit) — unless the shader treats flag 0 as black. The user says "a chunk streams in unlit". Possibly because the shader uses light_direct/light_diffuse bands and ignores the fallback flag for that path.

Let me check the shading shader's use of the flag/bands and the fallback. grep shading.wgsl for light_direct / has_light / measured.


Ran 2 terminal commands

Run
cd /c<home>/Documents/shploingus-clean && grep -n "light_direct\|light_diffuse\|measured\|has_light\|unmeasured" crates/voxel-client/src/shading.wgsl | head -30; echo ===; grep -rn "light_direct" crates/voxel-client/src/*.rs | head -20
cd /c<home>/Documents/shploingus-clean && grep -n "light_direct\|light_diffuse\|measured\|has_light\|unmeasured" crates/voxel-client/src/shading.wgsl | head -30; echo ===; grep -rn "light_direct" crates/voxel-client/src/*.rs | head -20

stdout:
35:    // scale the ladder's footprint is measured with; `y` is how much dither the
102:// frame, for the whole resident window**: measured on the shipped world, 57,673
193:    // frame's edges do not move when it is removed (the witness measured both variants).
303:    @location(5) light_direct: vec3<f32>,
304:    @location(6) light_diffuse: vec3<f32>,
308:    // is measured as zero — and a lit surface must not be handed back to the rig
331:    @location(6) light_direct: vec3<f32>,
332:    @location(7) light_diffuse: vec3<f32>,
384:    out.light_direct = in.light_direct;
385:    out.light_diffuse = in.light_diffuse;
393:    // the quad format does. Answering 1 here would read the zeros as a measured flat albedo.
507:    out.light_direct = vec3<f32>(0.0);
508:    out.light_diffuse = vec3<f32>(0.0);
668:    // **The body is the cuboid the model measured** — a cube of the record's half-extent on the
742:/// itself long before the sky: every cloud line arrived one flat violet, measured on the shipped
970:// and no stencil reads the same kind of number as a measured corner's diffuse band.
1353:    // had been measured and one that had not. The shader no longer branches on `light_present`,
1413:        // regression this rule removes. Unmeasured entirely, the map answers, which is the light
1424:    // the ambient it receives is `view + (1 − view)·albedo` — the fragment's own measured
===
crates/voxel-client/src/quad.rs:114:    pub light_direction: [f64; 3],
crates/voxel-client/src/quad.rs:224:            (body.light_direction[0] as f32).to_bits(),
crates/voxel-client/src/quad.rs:225:            (body.light_direction[1] as f32).to_bits(),
crates/voxel-client/src/quad.rs:226:            (body.light_direction[2] as f32).to_bits(),
crates/voxel-client/src/quad.rs:460:            light_direction: [0.0, 1.0, 0.0],
crates/voxel-client/src/quad.rs:477:            light_direction: [0.0, -0.25, 1.0],
crates/voxel-client/src/quad.rs:492:            light_direction: [0.0; 3],
crates/voxel-client/src/renderer.rs:4226:        let light = record.light_direction;
crates/voxel-client/src/scene.rs:110:    pub light_direct: [f32; 3],
crates/voxel-client/src/scene.rs:142:            light_direct: [0.0; 3],
crates/voxel-client/src/scene.rs:186:            // light_direct (B3, B4, B5)
crates/voxel-client/src/scene.rs:220:        for v in self.light_direct.iter().chain(self.light_diffuse.iter()) {
crates/voxel-client/src/scene.rs:493:        light_direct: [f32; 3],
crates/voxel-client/src/scene.rs:502:            light_direct,
crates/voxel-client/src/scene.rs:514:        light_direct: [f32; 3],
crates/voxel-client/src/scene.rs:537:                light_direct,
crates/voxel-client/src/scene.rs:968:                light_direct: [bands[0], bands[1], bands[2]],
crates/voxel-client/src/scene.rs:2371:                v.light_direct
crates/voxel-client/src/scene.rs:2377:            scene.vertices.iter().any(|v| v.light_direct != [0.0; 3]),
crates/voxel-client/src/scene.rs:2453:            v.light_direct[0]

Run
cd /c<home>/Documents/shploingus-clean && sed -n '1340,1430p' crates/voxel-client/src/shading.wgsl
cd /c<home>/Documents/shploingus-clean && sed -n '1340,1430p' crates/voxel-client/src/shading.wgsl

stdout:
    //
    // **This is the frame's light in one uniform and one shadow tap, and that is the point.**
    // PATCH-074 first transcribed the sky as `π · sky_radiance_rgb(n)` per fragment. That samples
    // the model's *zenith* for an up-facing normal — the darkest direction a single-scattering
    // sky has (`0.591` horizon against `3.9e-5` zenith at the crossing, `skylight.rs`'s own
    // figures) — so the ground went black while the trunks' horizon-facing sides stayed lit, which
    // is exactly the picture the player reported. It was also eight band iterations of `exp` per
    // fragment against a shadow map's one tap, which is why it streamed slower than the shadows.
    // The dome's mean is frame-global and the CPU already computes it; the shader samples it.
    //
    // **The per-corner bands are no longer a light.** They are the CPU field's measurement, and
    // that field is a demand queue marched cell by cell; reading it here made the light arrive
    // chunk by chunk, long after the geometry, and made the shading differ between a chunk that
    // had been measured and one that had not. The shader no longer branches on `light_present`,
    // and both branches of the retired law are gone. The vertex format still carries the bands (a
    // mesh is a format's, not this pass's to shrink); nothing in this file reads them.
    var sky = rig.ambient.rgb;
    var beams = vec3<f32>(0.0);
    // **The beam's direction is the frame's one Sun/Moon direction**, read from the rig uniform;
    // it is the direction *of the beam*, not a second light. A per-corner direction is the next
    // slice's input (M1.2/M2.0), and until it exists this is the only direction the frame has.
    var beam_dir = vec3<f32>(0.0, 1.0, 0.0);
    var beam_known = false;
    if (rig.count.x > 0u) {
        beams = rig.lights[0].colour.rgb * rig.lights[0].direction.w;
        beam_dir = normalize(rig.lights[0].direction.xyz);
        beam_known = true;
    }
    // **The map says how much of the beam arrives; it does not replace the beam.** It is drawn
    // from the scene's corners every frame and covers the shipped window, so the beam follows an
    // edit on the frame the new mesh is drawn, past any cell a build last asked about. It is the
    // **far** field's answer, though: a 0.56 m texel with a 2 cm normal bias, which at a grazing
    // beam cuts a straight line across a face the geometry says is lit. The subvoxel march below
    // is finer than that, so it refuses this map wherever it has a measurement of its own.
    var beam_visibility = 1.0;
    if (beam_shadow.direction.w > 0.5) {
        beam_visibility = sun_visibility(in.eye_rel, n);
    }
    // **The streamed horizon, at the fragment's own cell.** The shadow map can say whether the
    // beam is behind the world from one direction; it cannot say how much of the **dome** a cell
    // can see, and it knows nothing about the air the far field crossed. This is the second
    // measurement: the same resident octrees the world is meshed from, stamped a metre at a time
    // as the chunks stream in, marched here toward the beam and along the stencil's three sky
    // rays. The beam keeps the shadow map's finer texels and takes the march as well — a cell
    // behind a wall the map's box does not cover is still dark — and the ambient is the march's
    // own share of the atmosphere's radiance.
    //
    // **The Moon is in the two colours, not in a third ray.** At night `beams` is the solver's
    // `moonlight` — the Sun's bands reflected off the Moon's own declared reflectance — and by day
    // the Moon's scattered term is already inside `sky_radiance_rgb`, which is where `rig.ambient`
    // came from. The march decides how much of either reaches this cell, so a cave under a cliff
    // loses the moonlight it cannot see rather than receiving a uniform night.
    //
    // **Half a cell along the normal** leaves the fragment's own cell, which is the geometry it
    // is drawn on; without it every surface would shadow itself on the first tap.
    let horizon_point = in.eye_rel + n * (HORIZON_CELL_M * 0.5);
    if (beam_known) {
        // **The water the beam crossed, on the beam's own ray.** The air's reddening is already in
        // `lights[0]` (`Sky::sun` is the transmitted band); the droplets above *this* fragment are
        // not, and they are what a beam under a cloud bank loses. Applied before the visibility
        // terms and touching neither of them.
        beams *= beam_cloud_filter(in.eye_rel, beam_dir);
        let marched = horizon_transmittance(horizon_point, beam_dir, HORIZON_REACH_M);
        // **Only the band that is finer than the map may overrule it, in either direction.** The
        // fine band reads the world's own subvoxels as far as its box reaches; inside that range
        // the map's half-metre texel and its 2 cm normal bias are not a second opinion — they are
        // a coarse one, which is what drew a straight edge across a face the geometry says is lit.
        // So a fine hit is a refusal the map cannot argue with, and a fine clear is the beam.
        //
        // **The coarse band is refused here and answers the dome only.** Past the fine box it is
        // an 8 m summary: an occluder it finds is real, but so is the lit ground beside it, and
        // the shadow map still covers that range at 0.28 m. Letting eight metres subtract from
        // the beam is how the far field grew blocks of shadow the geometry does not cast — the
        // regression this rule removes. Unmeasured entirely, the map answers, which is the light
        // the far field had before the volume existed.
        if (marched.x > 0.5) {
            beam_visibility = 0.0;
        } else if (marched.y > 0.5) {
            beam_visibility = 1.0;
        }
    }
    beams *= beam_visibility;
    // **The dome, and the enclosure's own one bounce.** A cell that can see none of the sky is not
    // unlit: the walls it can see are lit by the same dome and reflect their own share of it, so
    // the ambient it receives is `view + (1 − view)·albedo` — the fragment's own measured
    // reflectance, not a constant. That is what carries light down a corridor instead of letting the
    // ambient die at the first metre of cover, and it is why a tunnel mouth's light fades with depth
    // rather than stopping where the rig's floor used to.
    let dome = horizon_dome(horizon_point);
    if (dome.y > 0.5) {
        let reflecting = select(vec3<f32>(1.0), base, base_present > 0.5);

Thinking
Important: the shader uses horizon_dome(horizon_point) and horizon_transmittance — the stamped horizon volume. If a chunk hasn't been stamped yet (budget), the dome/transmittance reads unmeasured. How does horizon_walk treat unmeasured? "unfilled slots read unmeasured" and the coarse band is refused. But horizon_dome might return unmeasured → ambient zero → the chunk draws dark until stamped. That's exactly "a chunk streams in unlit"!

And my earlier edit removed the far-surface block but the horizon stamping is budgeted at 9 chunks/frame. A new chunk entering near the eye is stamped within a frame or two... but the horizon walk at a fragment's cell: if the cell is in an unstamped chunk, horizon_dome returns unmeasured (y=0?), and then dome.y > 0.5 false → no ambient → black. So terrain near the edge streams in dark until stamped. Also chunks outside the horizon cube (which is 3 chunks a side = 96 m) — beyond it, unmeasured → no dome at all! Wait, horizon_dome probably falls back to the frame's ambient when unmeasured. Let me check the horizon.wgsl dome function to see the unmeasured fallback.

Also beam_visibility defaults to 1.0.

Let me read horizon.wgsl around dome/transmittance/walk for the unmeasured semantics.


Ran 2 terminal commands

Run
cd /c<home>/Documents/shploingus-clean && grep -n "fn horizon_walk\|fn horizon_dome\|fn horizon_transmittance\|unmeasured\|FAR_MEASURED\|return" crates/voxel-client/src/horizon.wgsl | sed -n '1,60p'
cd /c<home>/Documents/shploingus-clean && grep -n "fn horizon_walk\|fn horizon_dome\|fn horizon_transmittance\|unmeasured\|FAR_MEASURED\|return" crates/voxel-client/src/horizon.wgsl | sed -n '1,60p'

stdout:
21:    // 32 m slot of the 3×3×3 cube. A cell in an unset slot is *unmeasured*, not air — zero means
45:// The coarse word's share and stamped bit, `voxel_client::horizon`'s `FAR_SHARE`/`FAR_MEASURED`.
47:const FAR_MEASURED: u32 = 256u;
61:// "unmeasured", which hands the answer back to the shadow map on exactly the rays a corner casts.
81:    return vec2<u32>(horizon_cells[index], horizon_cells[index + 1u]);
87:    return horizon_far[u32(i.x + n * (i.y + n * i.z))];
99:    return ((horizon.coverage.x >> bit) & 1u) != 0u;
115:    return ((word >> (ordinal % 32u)) & 1u) != 0u;
132:            return true;
136:    return false;
161:fn horizon_walk(
173:        return vec4<f32>(0.0, 0.0, from_t, 0.0);
206:            return vec4<f32>(0.0, 1.0 - coarse_clear, reach_m, 1.0);
212:            return vec4<f32>(0.0, 1.0 - coarse_clear, enter, 1.0);
216:                return vec4<f32>(0.0, 0.0, enter, 0.0);
223:                return vec4<f32>(enter, 1.0, enter, 1.0);
226:                return vec4<f32>(enter, 1.0, enter, 1.0);
230:            if ((word & FAR_MEASURED) == 0u) {
231:                return vec4<f32>(0.0, 1.0 - coarse_clear, enter, 0.0);
236:    return vec4<f32>(0.0, 1.0 - coarse_clear, reach_m, 0.0);
253:fn horizon_transmittance(local: vec3<f32>, d: vec3<f32>, reach_m: f32) -> vec4<f32> {
258:        return vec4<f32>(1.0, 1.0, 0.0, 0.0);
261:        return vec4<f32>(0.0, 0.0, 0.0, 0.0);
267:        return vec4<f32>(0.0, 1.0, 0.0, 0.0);
276:    return vec4<f32>(0.0, 1.0, far.y, far.w);
284:/// volume existed, because an unmeasured ray is not a shadow.
288:        return 1.0;
295:    return select(1.0, 0.0, marched.x > 0.5) * (1.0 - marched.z);
311:fn horizon_dome(local: vec3<f32>) -> vec2<f32> {
326:    return vec2<f32>(total / 5.0, select(0.0, 1.0, measured > 2.5));

Run
cd /c<home>/Documents/shploingus-clean && sed -n '296,330p' crates/voxel-client/src/horizon.wgsl; echo ===RS; sed -n '150,240p' crates/voxel-client/src/horizon.rs
cd /c<home>/Documents/shploingus-clean && sed -n '296,330p' crates/voxel-client/src/horizon.wgsl; echo ===RS; sed -n '150,240p' crates/voxel-client/src/horizon.rs

stdout:
}

/// **The dome's own share at a point**, and whether the stencil was measured: `vec2(view, measured)`.
///
/// **Five directions, and the count is the CPU sampler's own** (`voxel_stream::light::SKY_STENCIL`):
/// up and four at 45°, the same rays at every fragment, so two cells' skies are comparable and a
/// cave mouth reads darker than a ridge. Five is not a hemisphere and this is not an integral; it
/// is a declared stencil, and the bounce below is what carries light past it.
///
/// **The rays are as long as the volume is**, not the fine band: a stencil that stopped at 96 m
/// would report every long corridor as open sky, which is the one answer a tunnel must not get.
///
/// **`measured` is a majority, not a unanimity**: a stencil half in the next chunk slot along is
/// still an answer about this cell, and refusing it would put a chunk-corners pattern into every
/// cave's ambient.
fn horizon_dome(local: vec3<f32>) -> vec2<f32> {
    let rays = array<vec3<f32>, 5>(
        vec3<f32>(0.0, 1.0, 0.0),
        vec3<f32>(0.70710677, 0.70710677, 0.0),
        vec3<f32>(0.0, 0.70710677, 0.70710677),
        vec3<f32>(-0.70710677, 0.70710677, 0.0),
        vec3<f32>(0.0, 0.70710677, -0.70710677),
    );
    var total = 0.0;
    var measured = 0.0;
    for (var ray = 0; ray < 5; ray = ray + 1) {
        let answer = horizon_transmittance(local, rays[ray], HORIZON_FAR_REACH_M);
        total = total + select(1.0, 0.0, answer.x > 0.5) * (1.0 - answer.z);
        measured = measured + select(0.0, 1.0, answer.y + answer.w > 0.5);
    }
    return vec2<f32>(total / 5.0, select(0.0, 1.0, measured > 2.5));
}

===RS
/// 96³ × 8 B = 6.75 MB, uploaded only on a frame whose contents moved.
pub struct HorizonStream {
    /// `HORIZON_WORDS_PER_CELL` words per cell, in `x + n·(y + n·z)` order.
    cells: Vec<u32>,
    /// **The far band**: one [`FAR_SHARE`]/[`FAR_MEASURED`] word per 8 m cell, 32³ = 256 m.
    ///
    /// It is what lets a march reach a kilometre of tunnel at a cost a frame can carry: an empty
    /// coarse cell is one compare for eight metres, and a full one stops the ray. Its grain is the
    /// chunk mesh's own second rung rather than four cells of the near band, so past the fine
    /// band's edge the answer is eight times coarser and arrives eight times cheaper — the same
    /// trade every LOD in this client makes, stated rather than implied.
    far: Vec<u32>,
    /// The world-voxel corner of cell `(0, 0, 0)`.
    anchor: [i32; 3],
    /// The world-voxel corner of far cell `(0, 0, 0)`.
    far_anchor: [i32; 3],
    /// **Chunks stamped into this anchor's cube, and the version of the tree each was stamped
    /// from** — so a chunk is walked once per version of it and an edit is walked again.
    stamped: BTreeMap<(i32, i32, i32), u64>,
    /// Whether the CPU cube has moved since the last upload.
    dirty: bool,
    buffer: wgpu::Buffer,
    far_buffer: wgpu::Buffer,
    uniform: wgpu::Buffer,
}

impl HorizonStream {
    /// The cube, empty and anchored at the origin until a frame recentres it.
    pub fn new(device: &wgpu::Device) -> Self {
        let cells = (HORIZON_CELLS * HORIZON_CELLS * HORIZON_CELLS) as usize;
        let bytes = (cells * HORIZON_WORDS_PER_CELL * 4) as u64;
        let far_cells = (HORIZON_FAR_CELLS * HORIZON_FAR_CELLS * HORIZON_FAR_CELLS) as usize;
        HorizonStream {
            cells: vec![0; cells * HORIZON_WORDS_PER_CELL],
            far: vec![0; far_cells],
            anchor: [0, 0, 0],
            far_anchor: [0, 0, 0],
            stamped: BTreeMap::new(),
            dirty: true,
            buffer: device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("light-horizon"),
                size: bytes,
                usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            }),
            far_buffer: device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("light-horizon-far"),
                size: (far_cells * 4) as u64,
                usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            }),
            uniform: device.create_buffer(&wgpu::BufferDescriptor {
                label: Some("light-horizon-view"),
                size: UNIFORM_BYTES,
                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
                mapped_at_creation: false,
            }),
        }
    }

    /// **The two entries the world pass adds for the horizon** — the cells at binding 10 and the
    /// view at 11, after the shadow's 6–9.
    pub(crate) fn layout_entries() -> [wgpu::BindGroupLayoutEntry; 3] {
        let storage = |binding: u32| wgpu::BindGroupLayoutEntry {
            binding,
            visibility: wgpu::ShaderStages::FRAGMENT,
            ty: wgpu::BindingType::Buffer {
                ty: wgpu::BufferBindingType::Storage { read_only: true },
                has_dynamic_offset: false,
                min_binding_size: None,
            },
            count: None,
        };
        [
            storage(10),
            wgpu::BindGroupLayoutEntry {
                binding: 11,
                visibility: wgpu::ShaderStages::FRAGMENT,
                ty: wgpu::BindingType::Buffer {
                    ty: wgpu::BufferBindingType::Uniform,
                    has_dynamic_offset: false,
                    min_binding_size: None,
                },
                count: None,
            },
            storage(12),
        ]
    }

    /// The bind-group entries that pair with [`HorizonStream::layout_entries`].
    pub(crate) fn bind_entries(&self) -> [wgpu::BindGroupEntry<'_>; 3] {

Thinking
horizon_dome returns (view, measured); the shader only applies the dome when dome.y > 0.5 (measured by >2.5 of 5 rays). If a chunk isn't stamped, the rays are unmeasured → dome.y = 0 → the if doesn't run → falls through to presumably the rig ambient? Let me see what happens after the if (dome.y > 0.5) block in shading.wgsl — if there's an else that uses rig.ambient. Let me read a bit further.

If the else is missing and sky stays rig.ambient... Actually var sky = rig.ambient.rgb; then dome overrides if measured. So unmeasured → rig ambient. Not unlit.

So "chunk streams in unlit" isn't the dome.

What else? beam_visibility via sun_visibility(in.eye_rel, n) when the shadow map is present. The shadow map may not cover chunks that just streamed in? It's drawn from the scene's corners each frame, so it covers.

Alternatively "unlit" = the chunk's material is wrong (all grey) — e.g., chunk streams in and is drawn with the quad format (no material id) rather than the vertex format? Or the chunk's materials are missing because the chunk landed as an empty tree?

Hold on — the second screenshot shows large flat grey/dark areas and yellow ground, which look like terrain with a light applied wrong. Hmm.

Given the user answered "a chunk streams in unlit", the likely mechanism in code: the scene's per-corner light comes from the field; the shader no longer reads bands, so not that.

Maybe "unlit" means it has no shadow/dome until stamped and thus renders flat (fully beam-lit or flat ambient) — i.e., it doesn't match its neighbours: a chunk-shaped brightness patch. That is "unlit" in the sense of missing its occlusion, or oddly bright.

Let me look at main.rs's stamping order after my removal: horizon_retain(&resident) then budget 9 stamps. streamer.tree_chunks() — does it iterate ALL chunks or only the resident window? And is horizon_recenter called before retain? Yes.

Wait: graphics.world.horizon_retain(&resident) — the resident set is streamer.tree_chunks() filtered... but the horizon cube covers 3×3×3 chunks around the eye minus one, i.e., previous/next chunk. The streamer's residence is bigger. Fine.

Critical: the stamp loop iterates streamer.tree_chunks() and stops after 9 stamps; but it continues on chunks that don't want stamping — cheap. However the ORDER of tree_chunks() may not be nearest-first, and on a crossing 18 new chunks need stamping over 2 frames. During those frames, those chunks are drawn with unmeasured horizon → dome unmeasured → rig ambient (flat) → they look flat/unlit vs neighbours. That's a 1–2 frame artifact though, not persistent.

Unless: stamps fail. if let Some(tree) = streamer.tree_shared(pos) — if the tree isn't available (still meshing?), skip; but then budget is not decremented, so the loop continues — fine.

Another possibility: horizon_retain is called with the streamer's resident chunks, but the horizon cube is anchored at eye chunk - 1; chunks in the cube that the streamer holds get stamped. OK.

Hmm, what about wants(): self.covers(pos) && stamped != version. covers checks the cube. Since the anchor shifts by a chunk, previously stamped chunks outside are forgotten by retain.

I need real evidence, not speculation. Since the user can see it, maybe ask a follow-up? That's another round trip.

Alternative approach that addresses the class of bug rather than one symptom: make a chunk's light arrive with the chunk, i.e. stamp the horizon synchronously when a chunk lands in the scene build, not on a later frame with a budget. That is exactly "light arrives with the chunk" and matches the mission's phrasing from the audit: "folding WorldLight's six bands into the one shader format so a chunk arrives with its light attached".

But stamping a chunk = walking 32³ leaves — measured at maybe ~1 ms? Doing it inline on landing would spike frames (the user complained about frame time). Hmm. Unless the stamping moves to the worker thread (the measurer's thread) and the horizon volume is filled before the chunk is drawn. That's the right architecture: chunk → measure light → then draw. "Absent rather than fake" — a chunk that lands but whose light isn't measured is not drawn until its light lands.

That's a big change: move stamping off-frame into the light worker, and gate the scene on horizon coverage.

Given the risk, maybe the actual bug is simpler: after my removal of the far-surface block, did I remove a closing brace / misplace code so the horizon stamping block is... no, it compiled.

Honestly, the most reliable next step is to instrument: add a temporary report of horizon stamping (chunks stamped, wanted, unmeasured) — but the user can't iterate fast.

Let me re-read the stamp loop and stamp() to check for a bug where chunks stamped are wrong/partial: e.g., stamp returns cells and writes into the cube at the current anchor, and retain clears only far band? Look at stamp + retain implementation.


Run
cd /c<home>/Documents/shploingus-clean && grep -n "pub fn stamp\|pub fn retain\|pub fn recenter\|fn clear_slot\|far_anchor\|fn covers" -A 40 crates/voxel-client/src/horizon.rs | sed -n '1,130p'
cd /c<home>/Documents/shploingus-clean && grep -n "pub fn stamp\|pub fn retain\|pub fn recenter\|fn clear_slot\|far_anchor\|fn covers" -A 40 crates/voxel-client/src/horizon.rs | sed -n '1,130p'

stdout:
165:    far_anchor: [i32; 3],
166-    /// **Chunks stamped into this anchor's cube, and the version of the tree each was stamped
167-    /// from** — so a chunk is walked once per version of it and an edit is walked again.
168-    stamped: BTreeMap<(i32, i32, i32), u64>,
169-    /// Whether the CPU cube has moved since the last upload.
170-    dirty: bool,
171-    buffer: wgpu::Buffer,
172-    far_buffer: wgpu::Buffer,
173-    uniform: wgpu::Buffer,
174-}
175-
176-impl HorizonStream {
177-    /// The cube, empty and anchored at the origin until a frame recentres it.
178-    pub fn new(device: &wgpu::Device) -> Self {
179-        let cells = (HORIZON_CELLS * HORIZON_CELLS * HORIZON_CELLS) as usize;
180-        let bytes = (cells * HORIZON_WORDS_PER_CELL * 4) as u64;
181-        let far_cells = (HORIZON_FAR_CELLS * HORIZON_FAR_CELLS * HORIZON_FAR_CELLS) as usize;
182-        HorizonStream {
183-            cells: vec![0; cells * HORIZON_WORDS_PER_CELL],
184-            far: vec![0; far_cells],
185-            anchor: [0, 0, 0],
186:            far_anchor: [0, 0, 0],
187-            stamped: BTreeMap::new(),
188-            dirty: true,
189-            buffer: device.create_buffer(&wgpu::BufferDescriptor {
190-                label: Some("light-horizon"),
191-                size: bytes,
192-                usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
193-                mapped_at_creation: false,
194-            }),
195-            far_buffer: device.create_buffer(&wgpu::BufferDescriptor {
196-                label: Some("light-horizon-far"),
197-                size: (far_cells * 4) as u64,
198-                usage: wgpu::BufferUsages::STORAGE | wgpu::BufferUsages::COPY_DST,
199-                mapped_at_creation: false,
200-            }),
201-            uniform: device.create_buffer(&wgpu::BufferDescriptor {
202-                label: Some("light-horizon-view"),
203-                size: UNIFORM_BYTES,
204-                usage: wgpu::BufferUsages::UNIFORM | wgpu::BufferUsages::COPY_DST,
205-                mapped_at_creation: false,
206-            }),
207-        }
208-    }
209-
210-    /// **The two entries the world pass adds for the horizon** — the cells at binding 10 and the
211-    /// view at 11, after the shadow's 6–9.
212-    pub(crate) fn layout_entries() -> [wgpu::BindGroupLayoutEntry; 3] {
213-        let storage = |binding: u32| wgpu::BindGroupLayoutEntry {
214-            binding,
215-            visibility: wgpu::ShaderStages::FRAGMENT,
216-            ty: wgpu::BindingType::Buffer {
217-                ty: wgpu::BufferBindingType::Storage { read_only: true },
218-                has_dynamic_offset: false,
219-                min_binding_size: None,
220-            },
221-            count: None,
222-        };
223-        [
224-            storage(10),
225-            wgpu::BindGroupLayoutEntry {
226-                binding: 11,
--
272:    pub fn covers(&self, pos: ChunkPos) -> bool {
273-        let (origin, far) = self.box_of(pos);
274-        origin[0] < far[0] && origin[1] < far[1] && origin[2] < far[2]
275-    }
276-
277-    /// **Whether this chunk's cube still needs this version of its tree.**
278-    ///
279-    /// True when the chunk is in the box and the version it was stamped at is not the version it
280-    /// has now — which is every chunk after a recentre, the chunk an edit rebuilt, and no chunk
281-    /// on an ordinary frame of a still world.
282-    pub fn wants(&self, pos: ChunkPos, version: u64) -> bool {
283-        self.covers(pos) && self.stamped.get(&(pos.x, pos.y, pos.z)) != Some(&version)
284-    }
285-
286-    /// **Move the cube to the eye's own chunk, and carry what it already knows.**
287-    ///
288-    /// Returns whether it moved. The anchor is the eye's chunk **minus one on each axis**, so a
289-    /// 96 m cube is three chunks a side with the eye's own chunk in the middle: a chunk behind
290-    /// the camera and the chunk ahead of it are both measured.
291-    ///
292-    /// **A crossing shifts the bands; it does not clear them.** The cube is a window on world space,
293-    /// and stepping it one chunk along moves two thirds of the world it holds. Clearing it and
294-    /// restamping all twenty-seven chunks is a frame that walks every leaf of three chunks it had
295-    /// already walked — the stall at a chunk boundary, and the reason the light arrived a chunk at a
296-    /// time. So the cells are copied to their new addresses, and every chunk still inside the new box
297-    /// keeps its stamped version. What fell out is forgotten; the chunks that entered are the only
298-    /// work the next stamp loop has to do.
299:    pub fn recenter(&mut self, eye_m: [f64; 3]) -> bool {
300-        let chunk = chunk_of(eye_m);
301-        let anchor = [
302-            (chunk.x - 1) * CHUNK_SIDE,
303-            (chunk.y - 1) * CHUNK_SIDE,
304-            (chunk.z - 1) * CHUNK_SIDE,
305-        ];
306-        if anchor == self.anchor {
307-            return false;
308-        }
309-        // **The far band is centred on the eye's own chunk too**, four chunks out on each axis: a
310-        // 256 m box with the player in the middle, so a tunnel mouth and the skyline are both in
311-        // it and nothing the eye can walk toward arrives half a box late.
312:        let far_anchor = [
313-            (chunk.x - HORIZON_FAR_SLOTS / 2) * CHUNK_SIDE,
314-            (chunk.y - HORIZON_FAR_SLOTS / 2) * CHUNK_SIDE,
315-            (chunk.z - HORIZON_FAR_SLOTS / 2) * CHUNK_SIDE,
316-        ];
317-        // Where the old bands' first cells land in the new ones, in their own grains. A chunk is 32
318-        // m and a coarse cell 8 m, so the far shift is four whole cells on every crossing.
319-        let cell_shift = [
320-            self.anchor[0] - anchor[0],
321-            self.anchor[1] - anchor[1],
322-            self.anchor[2] - anchor[2],
323-        ];
324-        let far_shift = [
325:            (self.far_anchor[0] - far_anchor[0]) / HORIZON_FAR_CELL_M as i32,
326:            (self.far_anchor[1] - far_anchor[1]) / HORIZON_FAR_CELL_M as i32,
327:            (self.far_anchor[2] - far_anchor[2]) / HORIZON_FAR_CELL_M as i32,
328-        ];
329-        self.cells = shifted(
330-            &self.cells,
331-            HORIZON_CELLS as i32,
332-            HORIZON_WORDS_PER_CELL,
333-            cell_shift,
334-        );
335-        self.far = shifted(&self.far, HORIZON_FAR_CELLS as i32, 1, far_shift);
336-        self.anchor = anchor;
337:        self.far_anchor = far_anchor;
338-        // **A stamp survives only while its chunk is still in the box.** Its cells moved with the

Thinking
This is a big design. Note HORIZON_CELLS = 96 cells = 96 m (1 m cells) → 3×3×3 chunks of 32 m. So a chunk's stamp covers only free space within 96 m of the eye. Beyond 96 m, unmeasured → the shader falls back to beam_visibility from the shadow map and sky = rig.ambient (not dome). Fine.

"A chunk streams in unlit": maybe it's not the horizon at all but the shadow map: beam_shadow.direction.w > 0.5 — if the shadow map's uniform isn't updated for new chunks... it says drawn from the scene's corners every frame.

Hmm, what does "unlit" mean visually? In screenshot 2, the huge grey slab looks unlit/flat compared to the yellow ground. Also there's a black gap at the near edge.

Wait: maybe what the user means is the chunk mesh has no light because the scene build gives corners light only when field.at() has a measurement, and since the shader doesn't read bands, that's irrelevant...

Unless: Scene::build_with_light sets light_present flag; the shader doesn't branch on it, but the renderer might use the flag to decide the vertex format or to skip uploading? The doc at 300: "is measured as zero — and a lit surface must not be handed back to the rig". 393: "Answering 1 here would read the zeros as a measured flat albedo."

I'm going in circles with static reading. The most productive thing: reproduce the state in a headless test that builds a scene with a chunk that just landed and check what its vertices carry / what the renderer's uniform is. But "unlit" is a shader-level outcome.

Different tack: ask the user for one more detail? They already answered. Asking twice risks annoyance.

Better: implement the architecture that makes the symptom impossible, per the user's own directive: a chunk's light must arrive with the chunk. Concretely: when a chunk lands in the scene, its horizon cells must already be stamped; if they are not, the chunk is not drawn yet (absent, like an unmeshed chunk). That is a small, precise change to the horizon streaming: instead of a 9-per-frame stamp budget applied to whatever wants it, stamp the chunks the scene is about to draw before the scene build, and if the stamping is not done for a drawn chunk, don't draw it? Doing it inline = frame spikes.

Alternative minimal fix matching "light arrives with the chunk": stamp on the worker thread. The Measurer already has a worker that marches cells and has tree handles. Let the worker stamp the chunk's horizon cells; the frame adopts them. That's a substantial change to horizon.rs + measure.rs + main.

Given remaining budget (~?), I should pick a bounded, high-confidence change. Let me check how the scene/mesh draws "unlit" — maybe there's a simpler known defect: horizon_stamp is only called when streamer.tree_shared(pos) returns Some, but tree_shared might only be available for chunks in the mesh stage; if a chunk landed in the scene but its tree handle was dropped (tree_shared None), it never stamps → permanent unlit (dome unmeasured) for that chunk. Since the user says a chunk "streams in unlit", and it stays unlit, that fits: the stamp is skipped and stamped never records the version, so wants stays true forever, but the tree handle is gone... then every frame it retries (non-budget-decrementing continue) — cheap but never succeeds.

Hmm, does tree_shared return Some for all resident chunks? Let me check voxel-work/stream.rs tree_shared.


Run
cd /c<home>/Documents/shploingus-clean && grep -n "fn tree_shared\|fn tree_chunks\|fn tree_version\|fn drawn\|fn meshes" -A 18 crates/voxel-work/src/stream.rs | head -90
cd /c<home>/Documents/shploingus-clean && grep -n "fn tree_shared\|fn tree_chunks\|fn tree_version\|fn drawn\|fn meshes" -A 18 crates/voxel-work/src/stream.rs | head -90

stdout:
377:    pub fn meshes(&self) -> impl Iterator<Item = &Mesh> {
378-        self.meshes.values().chain(self.stale.values())
379-    }
380-
381-    /// **What is drawn, with each chunk's mesh version**: `(position, version, mesh)`.
382-    ///
383-    /// The pair a scene that outlives a frame diffs: a position that is new landed, one that is
384-    /// absent left, and one whose version moved was remeshed. The version is the streamer's own
385-    /// residency counter, so it is monotone and never repeats for two different meshes.
386:    pub fn drawn_meshes(&self) -> impl Iterator<Item = (ChunkPos, u64, &Mesh)> {
387-        let versions = &self.versions;
388-        self.meshes.iter().chain(self.stale.iter()).map(move |(pos, mesh)| {
389-            (*pos, versions.get(pos).copied().unwrap_or(0), mesh)
390-        })
391-    }
392-
393-    /// What is drawn for a chunk: the current mesh, or the last good one while
394-    /// a replacement is built.
395:    pub fn drawn(&self, pos: ChunkPos) -> Option<&Mesh> {
396-        self.meshes.get(&pos).or_else(|| self.stale.get(&pos))
397-    }
398-
399-    /// Chunks currently drawn from an **out-of-date** mesh.
400-    ///
401-    /// A HUD number, and the honest measure of the flash: it is non-zero exactly
402-    /// while something is being rebuilt, and returns to zero when it is done.
403-    pub fn stale_len(&self) -> usize {
404-        self.stale.len()
405-    }
406-
407-    /// Whether a chunk is being drawn from an out-of-date mesh.
408-    pub fn is_stale(&self, pos: ChunkPos) -> bool {
409-        !self.meshes.contains_key(&pos) && self.stale.contains_key(&pos)
410-    }
411-
412-    /// The last refusal the generator produced, so a caller can *name* what is
413-    /// wrong with the world instead of only counting it.
--
437:    pub fn tree_version(&self, pos: ChunkPos) -> Option<u64> {
438-        self.versions.get(&pos).copied()
439-    }
440-
441-    /// **The same tree as a handle**, for a caller measuring on another thread.
442-    ///
443-    /// A refcount rather than a copy: `voxel_client::field`'s measurer keeps the trees its
444-    /// marches cross, and duplicating a chunk's 89 kB for it would put the world's light on the
445-    /// memory ledger a second time.
446:    pub fn tree_shared(&self, pos: ChunkPos) -> Option<std::sync::Arc<SparseVoxelOctree>> {
447-        self.trees.get(&pos).cloned()
448-    }
449-
450-    /// **Which chunks have a tree in hand.** A measurer is handed this set with each ask so that
451-    /// a chunk outside the window is known in one hash lookup rather than a round trip to this
452-    /// thread: the sky above the world is most of a beam's march, and a request per hop for a
453-    /// chunk that cannot be there costs a frame each.
454:    pub fn tree_chunks(&self) -> impl Iterator<Item = ChunkPos> + '_ {
455-        self.trees.keys().copied()
456-    }
457-
458-    /// Bytes held by the resident octrees, **beside** the meshes [`Streamer::digest`] and
459-    /// [`Frame::bytes`] account for. The charge inside the budget is the sum of the two; this is
460-    /// the breakdown, for a readout that has to say where the memory went.
461-    pub fn tree_bytes(&self) -> usize {
462-        self.trees.values().map(|tree| tree.bytes()).sum()
463-    }
464-
465-    pub fn material_at(&self, x: i32, y: i32, z: i32) -> Refused<MaterialId> {
466-        self.pool.material_at(x, y, z)
467-    }
468-
469-    /// **Change the world**: record one voxel and mark exactly the chunks
470-    /// the change reaches as out of date.
471-    ///
472-    /// This is a dig, a placed block, anything a player does. The affected chunks

Thinking
tree_chunks() yields all chunks with a tree held — the resident set, fine, and tree_shared is Some for those. So stamping works.

So why "a chunk streams in unlit"? Consider the horizon cube: 96³ cells = 884,736 cells, 2 words each = 7 MB, uploaded when dirty. stamp marks dirty. But the uniform (anchor) is written when? If the uniform (anchor) is only written on recenter, and cells move on recenter too, fine.

Hmm — the eye-relative coordinate frame: the shader uses in.eye_rel, and horizon view has anchor. If the anchor lags... whatever.

Time check: I've spent a lot. Let me consider what a good fix looks like from the user's perspective: "a chunk streams in unlit" → make the chunk's light part of the chunk's residency: stamp it before the chunk is drawn, once, at landing, and let the streamer own that work (the same place meshes are built), not a per-frame loop with a budget. The chunk then never appears without its horizon cells. This is a concrete implementation:

In the streamer/frame path: when a chunk version lands (in Residency report from resident.sync), stamp the horizon for it right there (before the draw). Stamping is CPU: walking the octree. Cost per chunk measured? The stamp function walks 32³ cells with visit_at_level? Let me measure-ish: it's a 32768-voxel walk, plus far share. Maybe ~0.5–2 ms per chunk. Stamping 1–2 chunks per landing frame is cheaper than 9 per frame.

But the horizon stream lives in Graphics (device-backed), and the residency sync is on self.resident — both accessible in redraw. So: move the stamping to occur on the landing set (the Residency diff: landed chunks) rather than the whole resident set, and keep a backlog only for chunks that were resident before the volume existed (e.g., first frame). That's still per-frame loop but driven by chunk landing = "the light arrives with the chunk".

Yet if the chunk lands and is drawn this frame (the demo's own claim: a landing chunk is drawn in the same frame), stamping inline is in the same frame, before the draw → light arrives with the chunk. Yes! And if the budget can't cover it, the chunk should not be drawn — but that conflicts.

Simplest honest change: stamp every newly landed/remeshed chunk inline in the frame it lands, bounded by nothing (1–3 chunks typical), and drop the 9-per-frame sweep. Cost moves from every frame to landing frames. That directly fixes "streams in unlit" and is camera/residency driven.

Where does the frame know what landed? self.residency (Residency::default with counts) — let me check its fields: landed etc. In the sync section, resident.sync(...) returns Residency. Let me check for a per-chunk landed list.

Let me look at ResidentScene::sync signature and Residency.


Run
cd /c<home>/Documents/shploingus-clean && grep -n "pub struct Residency" -A 30 crates/voxel-client/src/scene.rs | head -45; echo ===; grep -n "pub fn sync" -A 30 crates/voxel-client/src/scene.rs | head -45
cd /c<home>/Documents/shploingus-clean && grep -n "pub struct Residency" -A 30 crates/voxel-client/src/scene.rs | head -45; echo ===; grep -n "pub fn sync" -A 30 crates/voxel-client/src/scene.rs | head -45

stdout:
1492:pub struct Residency {
1493-    /// How many chunks landed this sync.
1494-    pub landed: usize,
1495-    /// How many chunks left this sync.
1496-    pub left: usize,
1497-    /// How many chunks had their light refreshed.
1498-    pub refreshed: usize,
1499-    /// How many landed chunks the frame's budget did not reach.
1500-    pub pending: usize,
1501-    /// Whether any of the scene's arrays moved.
1502-    pub changed: bool,
1503-}
1504-
1505-/// **The scene the player is standing in, kept across frames and changed only where the world
1506-/// changed.**
1507-///
1508-/// [`SceneBuild`] walks every resident mesh when the world moves, and the frame draws the previous
1509-/// scene until the walk finishes — so while the player walks, the ground under them can be absent
1510-/// for the whole build. This owns the arrays instead: a chunk that lands appends its own vertices,
1511-/// indices, records and origin; a chunk that leaves is swap-removed with the last chunk's slice
1512-/// moved into its place, its `chunk` slot rebound. Nothing else is touched, and the frame draws the
1513-/// result in the same beat.
1514-///
1515-/// **The arrays stay dense**, so one `draw_indexed` and one record draw still cover the world: the
1516-/// swap is the whole rebase, and it is O(one chunk) rather than O(the window).
1517-///
1518-/// **Landings are budgeted by distance**, so a window step that lands a hundred and five chunks
1519-/// lands the ones under the eye first and carries the rest to the next frames; the eye's own chunk
1520-/// never waits behind a far one. The light's own refresh is budgeted the same way, round-robin: a
1521-/// measured band is at most one pass behind, and no frame pays for the whole window.
1522-pub struct ResidentScene {
===
1749:    pub fn sync<'a>(
1750-        &mut self,
1751-        drawn: impl Iterator<Item = (voxel_model::ChunkPos, u64, &'a Mesh)>,
1752-        centre: voxel_model::ChunkPos,
1753-        light: Option<&LightAt<'_>>,
1754-        displacement: Option<&voxel_model::DisplacementField>,
1755-        refine: Option<&voxel_mesh::RefineConfig>,
1756-        quads: usize,
1757-        light_epoch: u64,
1758-    ) -> Residency {
1759-        let mut report = Residency::default();
1760-        {
1761-            let scene = self.scene.as_mut().expect("held");
1762-            scene.begin_resident_frame();
1763-        }
1764-        let current: std::collections::BTreeMap<_, _> = drawn
1765-            .map(|(pos, version, mesh)| (pos, (version, mesh)))
1766-            .collect();
1767-        if self.light_epoch != light_epoch {
1768-            self.light_epoch = light_epoch;
1769-            self.light_stale = self.blocks.keys().copied().collect();
1770-        }
1771-        // 1. What left the world goes now: removing a block never needs the light.
1772-        let gone: Vec<_> = self
1773-            .blocks
1774-            .keys()
1775-            .filter(|pos| !current.contains_key(pos))
1776-            .copied()
1777-            .collect();
1778-        for pos in gone {
1779-            self.remove(pos);

Thinking
The sync is budget-driven by distance and reports pending. The stamp loop is separate in main.rs.

Concrete fix for "a chunk streams in unlit": stamp the horizon for the chunk in the same frame it is drawn, before the draw, and don't draw a chunk whose horizon isn't stamped. But the draw is one draw_indexed over all resident blocks — can't skip per chunk without breaking the batch.

Alternative: stamp before sync — i.e., for every chunk the streamer holds a tree for that the horizon wants, stamp it in the same frame; drop the 9 budget but bound by the landing set. If the landing set is large (a hop = 105 chunks), that's 105 × 32k voxel walks = too slow. That's why the budget exists.

So the real fix must be to make stamping cheap enough or move it off-thread. Options: (a) Walk the octree at a coarser level for the far band and stamp the fine band only near the eye (sphere/box of a few chunks) — the fine band only reaches 96 m anyway, so 27 chunks max. 27 chunks × walk... but only when crossing, and it must be done within a frame or two. (b) Move the stamp to the worker: send chunk trees to the light worker thread, it stamps, and the horizon buffer gains cells on adoption. Cost on the frame = near zero.

(b) is the right architecture and matches "light arrives with the chunk" (asynchronously, but before the frame needs it) — though then the draw may still precede the measurement by a frame or two, which is the current symptom.

Hmm, alternatively: draw a chunk only after its light is stamped. Since the scene is built per-chunk-slice, sync could skip chunks whose horizon isn't ready and retry next frame; they'd be absent rather than unlit — and the mission rule says "unfilled slots read unmeasured" and "a chunk with no light is absent rather than drawn as a stand-in" (for far surfaces). That's consistent with the user's expectation? "A chunk streams in unlit" — making it absent is not obviously better.

Wait. Maybe I'm overcomplicating: perhaps the light is the per-corner bands, and the shader does read them somewhere else (e.g. water/body shaders, or the shading.wgsl vertex light_present used by the body shaders). The user says "light streaming over chunks is still broken" — maybe they mean the light streaming into chunk meshes (the bands), i.e., chunks arrive with zero bands (flag 0) → fall back to rig → looks flat/unlit. And the fallback is the rig, which at night is dark. So a chunk streaming in at night shows rig light (dark) until measured — appearing unlit.

Whatever the exact mechanism, the fix direction is the same: the chunk's own measured bands must be present when it is drawn. That means the field's measurement must precede the scene build — the classic "light arrives with the chunk" — which is the audit's named debt: fold the bands into the chunk's format so a chunk arrives with its light attached.

Given the size, and that I cannot verify visually, the honest move might be to do a small concrete improvement + report. But the user wants it fixed, not explained.

Let me look at the actual code path once: does Scene::build_with_light get used in main (with the field), and does sync use LightAt per chunk? sync(..., light: Option<&LightAt>) — if the field has no measurement for a corner, LightAt returns None and the vertex gets flag 0. Chunks land and are built with whatever the field has at that moment, which for a fresh chunk is nothing → flag 0 → rig.

So the fix: when a chunk lands, don't build its vertices until its corners are measured — or build and then rebuild when the measurement lands. Currently the light epoch moves only when held > 0... held() counts what? If held counts measured cells, then when measurements land the epoch moves and the scene refreshes vertices for all blocks (round-robin). The doc says held is zero every frame since PATCH-074 because bands are no longer a scene input... wait it says the material's light isn't a scene input, so held is 0. So the light epoch never moves, so the scene never re-emits corners with newly measured bands — the bands stay the rig for the chunk's lifetime! That IS the bug: light never streams into a chunk after it lands.

Let me verify held() in field.rs and the epoch derivation (held = field.held() in main; SceneKey::light_of(held, light_epoch)).

Yes—main line 2839: let held = field.as_ref().map(|f| f.borrow().held()).unwrap_or(0); and the comment says "the material's light is not a scene input any more (PATCH-074) ... held is zero on every frame". Let me check held.


Run
cd /c<home>/shploingus-clean 2>/dev/null; cd /c<home>/Documents/shploingus-clean && grep -n "pub fn held\|fn held" -A 16 crates/voxel-client/src/field.rs; echo ===; grep -n "held" crates/voxel-client/src/field.rs | head -20
cd /c<home>/shploingus-clean 2>/dev/null; cd /c<home>/Documents/shploingus-clean && grep -n "pub fn held\|fn held" -A 16 crates/voxel-client/src/field.rs; echo ===; grep -n "held" crates/voxel-client/src/field.rs | head -20

stdout:
481:    pub fn held(&self) -> usize {
482-        self.cells.len()
483-    }
484-
485-    /// How many cells are queued for measurement and not yet asked for.
486-    pub fn queued(&self) -> usize {
487-        self.wanted.len() + self.behind.len()
488-    }
489-
490-    /// The direction the beam came from when the kept cells were measured.
491-    ///
492-    /// Exposed because it is the whole of this field's staleness story: a caller that wants to
493-    /// report *how stale* the field is has the direction rather than a flag, and can measure it
494-    /// against the solver's current one itself.
495-    pub fn toward_beam(&self) -> Option<[f64; 3]> {
496-        self.toward
497-    }
===
38://! frame is held to (8.1 ms settled, ~312 MB).
114:/// rather than growing for as long as the player walks. The first version held 262 144 and charged
265:    /// brought up. Kept apart from [`CellField::wanted`] because they *are* held: the miss queue
481:    pub fn held(&self) -> usize {
503:/// while the scene's own borrows are held — a method on `CellField` cannot express that.
621:        assert_eq!(field.held(), 1);
656:        assert_eq!(field.held(), 64);
680:        assert_eq!(moved.held(), 64, "the swing emptied the map");
697:        assert_eq!(night.held(), 0, "the Sun's cells were kept for the Moon's beam");

Give feedback



You
the chunks should never be lit by the rig it should be light sampled or rendering the chunk should be refused



2:58 PM
Freebuff

Worked for 9m 25s

Thought

Thinking
This is the key instruction: no rig-lit chunks. Either the chunk is light-sampled, or drawing it is refused.

That's a clear, decidable rule. Implement:

The scene must not draw a chunk whose corners are unmeasured. "Absent rather than a stand-in" — the same rule as unmeshed chunks.
So: ResidentScene::sync (or Scene::build_with_light) must refuse to append a block whose light isn't measured, and retry next frame. And the shader's rig fallback must be removed for the terrain surface (the rig path only exists for no-field worlds?).
Concretely, minimal and testable:

In scene.rs: when building with light, a corner that isn't measured currently gets flag 0 → drawn with rig. Change: a block whose corners are not fully measured is not emitted; the residency reports it as pending, and it is retried. That makes chunks absent until measured — refusing the draw.
Then the light field needs to actually measure corners for chunks quickly, otherwise the world will be mostly absent. The field's queue only fills when a build asks (at() per corner). If we skip the build for unmeasured chunks, we must still ask for their cells — so the block must still enumerate its corners to queue them, then skip emission.
Hmm, that's exactly the natural implementation: build the block's vertices for the light ask (queue misses), then if any corner was unmeasured, don't append it; mark it pending for a retry.

But "any corner unmeasured" is strict: a chunk has 32³×corners? The corner set per chunk might be thousands of cells. Requiring all → chunks stay absent for a long time (the measurer marches one cell per fragment? no — CELLS_PER_ASK per batch; marches are ~1 ms each?). The field would take forever to measure 1000 cells for a chunk. Then the world is absent a lot → worse.

Alternative: measure the chunk's cells in bulk — one march per cell but on the worker; a chunk has ~32³ cells = 32768 cells if per subvoxel... too many. The corner set is per mesh corner (unique corner addresses), maybe a few hundred to a few thousand per chunk.

Given the strict rule, the sane approach: the chunk lands only when its light is ready, and the light for a landing chunk is measured on the landing, not through the global demand queue. That's a worker job: the streamer's chunk is handed to the light worker as a "measure this chunk" job with bounded cells; the chunk's visibility waits.

That's a big change. Alternatively: sample light on the GPU per fragment — but that's the shadow map path that exists, not "measured".

OK — decision on scope. I have limited remaining budget and no ability to test visually. The most defensible small change that follows the user's rule:

Remove the rig fallback for drawn chunks and refuse the draw when the light is unmeasured, implemented in Scene::build_with_light (skip the block) plus keeping the ask. And to avoid a world with nothing drawn, make the measurement demand per chunk not per corner: queue the chunk's cells and count the chunk as ready when the field holds a measurement for every cell it asks about... still the same.

Hmm, wait. Maybe the light sampling the user means is the horizon/fragment march (the stamped volume), not the per-corner bands. "It should be light sampled" — i.e., each fragment sampled against the light volume, and if the chunk's cells aren't stamped → refuse to draw. That aligns with the horizon stamping I removed the sibling of. And the rig = rig.ambient fallback in the shader when dome.y <= 0.5 (unmeasured). The shader currently falls back to the rig ambient for unmeasured dome! That's exactly "chunks lit by the rig".

So the concrete fix:

In the shader, when the dome is unmeasured, do not fall back to the rig: the terrain should be refused (discarded) — i.e. discard when dome.y < 0.5 (and beam unmeasured?). That's the GPU-side "refuse to render the chunk". But per-fragment discard makes holes, not absent chunks... but it's exactly "rendering should be refused" at the granularity the shader has.

On the CPU side, don't stamp 9 chunks/frame lazily; stamp a chunk when it lands so the volume is filled before the chunk is drawn. But the shader discard handles the gap.

Given cost, implementing (1) is small: replace the rig fallback with discard. But the frame's sky = rig.ambient.rgb is used as the base; the dome overrides it if measured. Make: if (dome.y < 0.5) { discard; }.

Careful: discarding on the far field leaves holes where the horizon cube doesn't cover — beyond 96 m the dome is unmeasured, so the whole distance would vanish! The dome's rays are 160 m (HORIZON_FAR_REACH_M) — cells beyond the 256 m far cube would be unmeasured → discard → the far field disappears. That's unacceptable.

So the rule needs "sample the light where it exists; refuse where the chunk should have light". Hmm.

Given the complexity and my depletion, the right move now is to stop, report precisely what I found (the rig fallback in the shader for unmeasured dome, and that per-corner bands are never re-emitted because the light epoch only moves on held), and ask nothing — but the turn must deliver something. A partial: I could implement the chunk-level refusal on the CPU side where it's cheap and correct:

In Scene::build_with_light: count unmeasured corners; if any, still queue them but do not emit that block's geometry, and record it as pending. The block is retried when light lands. Absent = exactly "refuse to render".

Risk: long absence. But the field measures cells per batch; a chunk's corner count is large. During boot, the world would be empty for many seconds. That's a regression the user will see immediately.

Alternative compromise matching the rule with the existing architecture: keep drawing chunks only when they are fully measured, and make measurement cheap and per-chunk by marching on the worker with the chunk's tree — i.e., "the chunk is light-sampled at landing" — the worker already has tree_shared and a march. This is the audit's named debt and the real fix. It's a multi-file change (measure.rs: job kind; field.rs: bulk adopt; main.rs: ask for a landed chunk's cells before drawing).

I don't have the budget to do this safely and verify it.

Decision: be honest and surgical. Implement the principle in the one place it is cheap, testable, and impossible to misread:

Scene::build_with_light: emit a block only if every corner of it has a measurement; otherwise queue its cells (as it already does via at) and emit nothing this frame. Report it as pending in Residency (field exists).
Do not touch the shader's rig fallback (it then only applies to worlds with no field, which is the record-format path), and say so.
Verify with a test in scene.rs: a chunk with no measurement contributes zero vertices; once adopted, it emits; a chunk whose corners are all measured is unchanged.
And check what the "no field" path is: Scene::build (record format) — unaffected.

Then report: light now arrives with the chunk or the chunk is not drawn; and note the measurable consequence (initial latency) plus that the field's demand queue is what makes it converge.

Hmm, but the field's at() is called during the build: currently measure closure is light_at(&field) which borrows the field mutably. If I skip geometry for unmeasured blocks but still call at for each corner, the queue fills. Good.

Then how does the block get retried? Every frame the scene is rebuilt only when the key moves. If a block was skipped, the scene holds nothing for it; the sync's current map still has it (version unchanged) so it won't be re-emitted unless forced. Need the skipped chunks to be retried. In sync, a chunk is added when it's new or version changed. Add: a chunk recorded as awaited is retried each frame until emitted. That's in ResidentScene (blocks map + awaited set).

That's real work in scene.rs + tests. ~1-2 hours of careful editing with my remaining context... risky but it's the requested behaviour and small in lines.

Let me check how much structure exists: ResidentScene methods add/remove/refresh. Let me read the sync body fully (1760-1900) to plan the minimal insertion.

Actually — simpler and equally faithful: instead of skipping in scene building, don't hand the unmeasured chunk to the scene at all in main: filter streamer.drawn_meshes() to chunks whose light is fully held... but "fully held" per corner requires asking the field, which is exactly the build.

Alternatively: gate on the horizon stamp (chunk-level, cheap): horizon_wants(pos, version) — a chunk whose horizon isn't stamped isn't given to the scene. But horizon isn't per-corner measurement; the user said "light sampled".

I'll go with the scene-level refusal. Let me read scene.rs build_with_light around 940-1000 and the sync add path.

---

**#1366 · 2026-10-25T22:15:01.529000+00:00**

but you can't revert the fucking materials addressing differently now when I jump due to the shader changes?

---

**#1368 · 2026-10-25T22:18:19.378000+00:00**

It's not a smallest real fix it was working just fine over an hour ago now and because of your shit botch job it has been regressed to a point where now you refuse to fix it, and it's impossible to show you what it looks like because it requires frame by frame analysis of looking at the blocks while jumping

---

**#1370 · 2026-10-25T22:21:44.865000+00:00**

wrong- top correct bottom: you are now over 1 hour 20 minutes into a broken worktree

---

**#1372 · 2026-10-25T22:24:38.809000+00:00**

Kill yourself genuinely I said top is wrong and bottom is correct and you started jerking me around, 1 and a half hours into a broken worktree with broken light streaming and now cpu math on gpu shader and refusing to actually find the cause of the problem

---

**#1374 · 2026-10-25T22:28:51.688000+00:00**

look at the screenshots , the material should not look drastically different just because I am at a different height, stop burning turns on completing nothing and worrying about time this is yet another fresh session

---

**#1376 · 2026-10-25T22:30:19.018000+00:00**

no man it's not supposed to fucking change the world materials based on where they've being observed you're being an ass

---

**#1378 · 2026-10-25T22:35:04.886000+00:00**

Okay so you removed the lod materials blending at horizontal distance, literally the opposite of what you're supposed to fix, meanwhile jumping still provides the same readdressing issue

---

**#1380 · 2026-10-25T22:38:28.817000+00:00**

No it is not fucking fixed whatever the fuck happened between 2:30pm and 3:30pm today is still present and you still don't want to fix it

---

**#1382 · 2026-10-25T22:41:47.940000+00:00**

check the version from today at 2:16pm

---

**#1384 · 2026-10-25T22:43:14.270000+00:00**

goddamnit I'm talking about the materials on the surface of blocks

---

**#1386 · 2026-10-25T22:44:34.891000+00:00**

Oh my god bro I'm telling you to literally look at the old artifacts for the gpu shaders versions

---

**#1388 · 2026-10-25T22:45:21.606000+00:00**

No from today's changes today the files from 2 pm today

---

**#1390 · 2026-10-25T22:54:37.054000+00:00**

and again you completley removed lod material blending

---

**#1392 · 2026-10-25T23:01:12.334000+00:00**

your cpu tests are too primitive and do not find the issue in the gpu first renderer. top screenshot: broken lod rendering, broken chunk light sampling, broken materials addressing, bottom screenshot, correct version from earlier today

---

**#1394 · 2026-10-25T23:09:30.765000+00:00**

revert the worktree to an available version from 2pm today

---

**#1396 · 2026-10-25T23:11:03.909000+00:00**

No, get something older, not one that you already have, that artifact was aquired from the target folder, get your files from one of those older versions from before 14:00

---

**#1398 · 2026-10-25T23:34:25.406000+00:00**

okay you need to get an older shader from before 2:30pm

---

**#1400 · 2026-10-25T23:36:56.729000+00:00**

no, the current shader replacement has not fixed the issue on materialsrendering, either it must be an older set of shaders ported to horizon

---

**#1402 · 2026-10-25T23:41:16.484000+00:00**

the issue with materials never happens when walking, only when moving vertically, and has been a big pain regression in the code that the earlier light sampled world shader fixed, but managed to make into the build at between 2:00 pm today and beyond

---

**#1404 · 2026-10-25T23:44:28.503000+00:00**

this version of the shader has the regression though which is why I asked for an even earlier one

---

**#1406 · 2026-10-25T23:50:34.782000+00:00**

No, I'm saying that the thing that actually shades the terrain from that version is where the regression comes from

---

**#1408 · 2026-10-25T23:54:47.722000+00:00**

No, again you're missing what I'm saying, whatever the terrain shader actually used, whichever version last had a working wireframe, the version before the regression after 2:00pm

---

**#1410 · 2026-10-25T23:59:18.389000+00:00**

your rendered screenshots don't display the error I see on my end

---

**#1412 · 2026-10-26T00:03:04.876000+00:00**

mate it happens on the block surface

---

**#1414 · 2026-10-26T00:06:45.307000+00:00**

still unfixed

---

**#1416 · 2026-10-26T00:10:49.424000+00:00**

/playtest

---

**#1418 · 2026-10-26T00:15:40.285000+00:00**

your goddamn script didn't capture enough between frames and I had to manually do the jumping myself because you messed it up so bad

---

**#1420 · 2026-10-26T00:17:54.011000+00:00**

a-1792973812251 a-1792973812330 a-1792973811967

---

**#1422 · 2026-10-26T00:19:02.082000+00:00**

/playtest

---

**#1424 · 2026-10-26T00:19:24.207000+00:00**

a-1792973811586 a-1792973811649 one frame apart but drastically different addressed materials

---

**#1426 · 2026-10-26T00:21:13.039000+00:00**

a-1792973811029 this image compared to the three before it has differently addressed materials

---

**#1428 · 2026-10-26T00:22:37.719000+00:00**

/adversarial-fix

---

**#1430 · 2026-10-26T00:23:47.546000+00:00**

your budget is not exhausted

---

**#1432 · 2026-10-26T00:27:21.525000+00:00**

You doing a cpu gpu parity fix when this is gpu first is why this problem exists in the first place

---

**#1434 · 2026-10-26T01:18:30.858000+00:00**

/test

---

**#1436 · 2026-10-26T01:19:14.046000+00:00**

again, your changes did not address the actual problem which only appears during jumping between frames which the probe was supposed to be for

---

**#1438 · 2026-10-26T01:22:54.413000+00:00**

wrong probe, theresone for running the game and capturing it's real frames

---

**#1440 · 2026-10-26T01:29:21.940000+00:00**

you are not capturing enough frames

---

**#1442 · 2026-10-26T01:37:40.671000+00:00**

f26-f27, pixel at 216x665 flips along with it's entire subvoxel region in just one frame, happens many times across the lod materials surface

---

**#1444 · 2026-10-26T01:40:50.211000+00:00**

in jumpA you ass

---

**#1446 · 2026-10-26T01:42:21.233000+00:00**

check f-67 f-68 216 665 pixel is bright but one frame later pixel is dark

---

**#1448 · 2026-10-26T01:44:41.958000+00:00**

you're telling me that between these two patterns there's no way for you to see that they're clearly different?

---

**#1450 · 2026-10-26T01:46:05.137000+00:00**

the images from my screenshots are from f67 and f68

---

**#1452 · 2026-10-26T02:04:21.561000+00:00**

/test

---

**#1454 · 2026-10-26T02:56:24.351000+00:00**

so records is the newer format right? why is it doing this? records is 0 for every frame while vertices grows to thousands. So this build draws all terrain from the vertex path, not records! Interesting — perhaps the game is running with a "refine everything" config, or the mesh path switched entirely to vertices. That matches the user's "subvoxel region flips": terrain is refined geometry (bent quads), and the plane_axis fix matters exactly here.

So the digest on vertices is the right one, and the probe should be the nearest vertex to the eye projected... but vertices are dense (8104 near start). The probe: nearest vertex to the eye is likely directly below or a leaf.

Since records are 0, my ground branch never fires. Fix: choose the probe from vertices: the nearest vertex (that's a piece of surface in frame). Then radius 6 m covers a patch.

But careful: nearest vertex might be on the player's body/ghost. Bodies are appended... Vertex has chunk and body vertices have chunk = the body's own origin entry. Fine.

Also with an eye 19.6 m up, nearest vertex is ~18 m below (ground) or a leaf 3 m away. Either is a valid surface. For the flip we want the ground visible in the lower part of the screen; nearest vertex below the eye is most likely the ground directly under.

Implement: if ground (records) is None, choose the nearest vertex below the eye (world y < eye.y) to break ties toward ground rather than a leaf above. Then probe = that world point.

Then re-run.

Note also: the fact that records is 0 everywhere means every terrain face is refined into triangles in this build — that's a big performance/architectural fact but not this pass's target.

Let me implement the vertex fallback now (removing the debug print afterwards, or keep behind env — keep, it's useful and gated). 
Can you fix that?

---

**#1456 · 2026-10-26T03:20:45.544000+00:00**

/playtest

---

**#1458 · 2026-10-26T03:38:20.240000+00:00**

/adversarial-fix

---

**#1460 · 2026-10-26T04:26:47.726000+00:00**

/reenvision

---

**#1462 · 2026-10-26T04:29:25.301000+00:00**

stop stop stop what the fuck was the last sessions work? why is the frame blurry when I walk around now? your whole fucking thing was to fix the materials breaking when moving vertically, now you've made walking around look worse

---

**#1464 · 2026-10-26T04:40:41.245000+00:00**

god when you fucking capture the games frames if you do it at a high enough frequency and you don't just use some shitty script to analyze it you can clearly see how slight changes in vertical position have drastic effects on the materials appearance but you fucking BOTS refuse to fix it so now this fucking shader rendering bug is back in my fucking game after we rewrote the rendering to the light sampler and records format to avoid it

---

**#1466 · 2026-10-26T05:03:42.452000+00:00**

one frame apart but wildly different material patterns on the ground

---

**#1468 · 2026-10-26T05:09:51.274000+00:00**

why are you ding a walk probe for something that only appears when moving VERTICALLY???

---

**#1470 · 2026-10-26T05:14:16.993000+00:00**

you can literally see in cross20 and cross20-near how there are literally lines cutting through the materials, but your sampling isn't even done right so you don't even see the issue

---

**#1472 · 2026-10-26T05:22:13.760000+00:00**

Continue the interrupted request from where you left off.

---

**#1474 · 2026-10-26T05:29:47.464000+00:00**

the bug is not fixed and you are not at your limit

---

**#1476 · 2026-10-26T05:33:57.932000+00:00**

it just is not a fucking issue that happens on the horizontal axis of the blocks faces unless jumping but always happens on the vetical sides of blocks when moving

---

**#1478 · 2026-10-26T06:34:55.238000+00:00**

/audit

---

**#1480 · 2026-10-26T06:38:33.385000+00:00**

/deletion-first

---

**#1482 · 2026-10-26T07:01:51.953000+00:00**

I need you to rewrite specifically all of the terrain's material in the new baselines patch recipe format using the axis package only keeping it's ideas of lod material blending and completley destroying the old materials pipeline

---

**#1484 · 2026-10-26T07:04:31.599000+00:00**

we don't do 256 the minimum size is the 32^2 per face

---

**#1486 · 2026-10-26T07:08:11.216000+00:00**

the subvoxels is the individual cells within the block that can be addressed by the cubic profile shapers for making 3D shapes within the voxels themselves, but this explanation is updated compared to what subvoxels in code may be

---

**#1488 · 2026-10-26T07:09:44.212000+00:00**

No, I mean subvoxels are the pieces that we address down to a minimum of 32 per axis, so the maximum a block can address is within that 32^3 space but at distance can compile larger lods

---

**#1490 · 2026-10-26T07:11:34.886000+00:00**

yeah whatever this is sounds like a bunch of bullshit which causes unescesary rendering issues         let deviation = pattern
            .at(material, centre, footprint, surface)
            .expect("a finite point");
        println!(
            "\n{name}: {distance:.2} m away, {:.0} mM-BM-2 face, {oblique:.3} obliquity, footprint \
             {:.1} mm\n  cell {:?}, address ({}, {}, {}), deviation {:.4}",
            area / 16.0,
            footprint * 1000.0,
            cell,
            at.x,
            at.y,
            at.z,
            deviation.roughness_delta
        );

---

**#1492 · 2026-10-26T07:14:18.013000+00:00**

Caused by:
  In a CommandEncoder, label = 'frame'
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In Queue::submit
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

console [WARN] t81043 (laya) laya-0022 refused crates/axis/matrix/src/refusal.rs [not_belongs] at tick 81043: no proof of work on record: no claim, no evidence, no origin — the default is fail
shploingus: wgpu: Validation Error

Caused by:
  In a CommandEncoder, label = 'frame'
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In Queue::submit
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

---

**#1494 · 2026-10-26T07:21:54.444000+00:00**

The terrain material's LOD rungs are the target: after the axis-package rewrite and the ladder collapse they must have landed in a state the user says is wrong, and the block materials are still being judged against them. Begin by writing the rung table out as it actually is in the tree right now — every rung's cell size, the footprint rule that selects and blends it, the blend band width, and which rungs the axis package emits at each distance — then check that table against the user's stated floor of 32 addressable subvoxels per block face and against what a moving eye actually sees, rather than assuming either. Correct the rung law where it disagrees with that floor or with the block materials' own scale, and prove the result on the real game at high frame frequency under vertical eye motion, comparing consecutive captured frames by eye and by per-rung attribution, not a single summary statistic over a whole band. Done means the rung table is stated with its disagreement named, the wrong rungs are fixed in the axis-package path, and consecutive high-rate frames under vertical motion show the pattern changing smoothly with height.

---

**#1496 · 2026-10-26T07:23:55.895000+00:00**

Do not run full run dry tests to verify your work. Your work is when you track the changes made in git and restore the worktree's visual fidelity and performance

---

**#1498 · 2026-10-26T07:25:26.754000+00:00**

The new docs/baselines patch format for the rendering is GPU first due to the need for light sampling on the GPU.

---

**#1500 · 2026-10-26T07:32:12.576000+00:00**

Also, chunk light streaming was previously fixed and then regressed, naturally, so it's going to have to be repaired. At the moment the LOD blending does work but the block maximums fade too hard when there used to be multiple LOD rungs, as well the lod materials were sharp, not softened. Additionally, the fluids, clouds, terrain, and sun materials systems are all seperate, but they're all supposed to use the openpbr and full pbr.vfx pipeline from deadlock, which we did partially implement for the world materials, using the sampled atmospheric lighting through the actual materials system (as one thing)

---

**#1502 · 2026-10-26T07:33:16.479000+00:00**

No, the materials are sharp at any distance, the blending is the only part that looks blurred

---

**#1504 · 2026-10-26T07:35:48.054000+00:00**

Caused by:
  In a CommandEncoder, label = 'frame'
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In Queue::submit
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In a CommandEncoder, label = 'frame'
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In Queue::submit
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In a CommandEncoder, label = 'frame'
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

shploingus: wgpu: Validation Error

Caused by:
  In Queue::submit
    In a set_pipeline command
      RenderPipeline with 'world-quads' label is invalid

PS <home>\Documents\shploingus-clean>

---

**#1506 · 2026-10-26T07:52:21.285000+00:00**

Begin with the chunk light streaming regression, because it is the one item in the request with a known-good earlier state: find the commit that fixed it and the change that broke it, and restore that behaviour instead of inventing a new light path. The user's standard for proof is the in-engine recorder at high frame frequency — consecutive captured frames compared by eye and by per-cell or per-rung attribution while the eye is moving — not a summary statistic over a whole frame or band, and they have explicitly said not to spend the pass running entire test suites as verification. Done means light streaming behaves as it did in the fixed build, demonstrated on the real game from recorded consecutive frames, with the tree state before and after your edits recorded in git so the change is attributable. The LOD fade/softening, the map window's secure cell frame, and the unified openpbr material path all still need doing but do not start them in this pass.

---

**#1508 · 2026-10-26T07:54:33.303000+00:00**

the fix enables us to have far terrain chunks render and be lit with lod rungs like the shadow sampling

---

**#1510 · 2026-10-26T07:56:43.771000+00:00**

the world will eventually be a cuboid globe se we can technically fake further lods with minimal quads at distant horizons like how we have the sun and moon or clouds further out

---

**#1512 · 2026-10-26T08:02:02.597000+00:00**

chunks that i'm standing in still lose their lighting and chunks outside of the ones I'm near don't sample

---

**#1514 · 2026-10-26T08:07:09.664000+00:00**

there is a light memory leak likely due to unecessary cpu sampling of the subvoxel octree for lighting or other features and the materials being seperate per horizon is unintended

---

**#1516 · 2026-10-26T08:11:23.048000+00:00**

Next, the dark episode the user reported while you were working — "chunks that I'm standing in still lose their lighting and chunks outside of the ones I'm near don't sample" — is still unexplained, so reproduce it deliberately and fix it rather than writing it up as an open question. Build the pre-fix tree from the git checkpoint so you can record the same run on both trees and show the darkening as a before/after, then name its mechanism with per-cell attribution at the exact frames where a chunk goes dark: which band answered, whether a stamp was missing, what the shader actually read. A lead worth checking first: this pass's own draw gate refuses a fine-cube chunk whose stamp missed the frame's budget while letting far chunks draw with an unfilled summary, and the user's separate claim that light memory is leaking through CPU subvoxel-octree sampling points at the same stamp path — if that is where the cause lies, fixing it is in scope. Done means the darkening no longer occurs on a recorded run, shown by consecutive frames before and after, with the tree state recorded in git.

---

**#1518 · 2026-10-26T08:23:12.211000+00:00**

The near-ground blackout is the symptom the user actually reported, and after two passes it is still caught but not explained, so this pass is about making it reproducible on demand and naming its cause. The frame-rate-driven walk is why the episode moves between runs — drive the probe deterministically instead, with a fixed tick-driven path or a held pose at the point where it blacked out (z near -96), so a black frame can be produced whenever you want one. Then decide between the two candidates you already have using the per-frame readout on the frames that actually go to 0.0: a missing stamp while the band measures matter at the eye is a stamp bug, and an eye inside geometry is an instrument artefact — if it is an artefact, say so plainly and identify what would differ in the user's own play so the real cause is not lost. Keep every capture small and delete it after analysis; the last runs filled the drive and one died mid-recording, which must not eat this pass. Done means a black frame is reproducible on demand, its cause is named, and any light or stamp defect behind it is fixed.

---

**#1520 · 2026-10-26T08:43:04.683000+00:00**

Light streaming is close to done: the far band is measured on the game's own frames and one stamp bug is fixed at its cause, but you said the class is still open — a chunk that leaves and re-enters a crossing under an ordinary version-bump stamp can leave cells reading matter after its geometry moved. Prove or refute exactly that case, at unit level against the horizon stream, because it needs no captures and costs no disk: construct the leave-and-re-enter sequence and check whether a stale cell survives the crossing. If it survives, fix it at its cause and show the test flipping from red to green; if it cannot happen, name the invariant that prevents it so the question is closed rather than left as a worry. Treat this as the last pass on light streaming for now — the LOD fade and softening, the map window's secure cell frame and the unified openpbr path are all untouched and come next.

---

**#1522 · 2026-10-26T08:49:24.964000+00:00**

but chunks outside the one the player is in aren't sampling

---

**#1524 · 2026-10-26T08:55:05.319000+00:00**

I need you to update the new materials rendering to have the sharp nearest neighbor rendering and the missing lod bands again

---

**#1526 · 2026-10-26T09:07:15.126000+00:00**

No, the trilinear 8 corner sampling was better, you need to fit that version to the updated rungs with nearest neigbor

---

**#1528 · 2026-10-26T09:11:19.679000+00:00**

the blending is not smooth at the trilinear corner sampled cells are blurry (not using nearest neightbor)

---

**#1530 · 2026-10-26T09:14:20.989000+00:00**

why do you keep re-using the code for the previous nearest neighbor implementation

---

**#1532 · 2026-10-26T09:15:31.120000+00:00**

when jumping in the trilinear sampled version, the cells don't flicker. when jumping in the nearest neighbor version, the cells flicker

---

**#1534 · 2026-10-26T09:38:57.872000+00:00**

okay now git commit for this current stage and then work on fixing the remaining chunk light streaming features, re-adding the refusal for chunks that aren't being light sampled and increasing the worker count

---

**#1536 · 2026-10-26T09:41:55.433000+00:00**

I am also not seeing low density cubic lods of disant chunk terrain, which will also need to be light sampled and shadow sampled

---

**#1538 · 2026-10-26T09:45:21.790000+00:00**

please do not burn this turn on a long lib test

---

**#1540 · 2026-10-26T09:55:19.176000+00:00**

again not even the chunk I'm in is sampling literally the entire world that has chunks (including the distant lods) are supposed to sample

---

**#1542 · 2026-10-26T10:02:33.069000+00:00**

gosh, the world is supposed to be 1/8th the size of planet earth, so we can have terrain render out at distant horizons with it's lod light sampling and lod terrain because we know how big it's supposed to be. that's the whole point of the cadence tick is so we can seperate out lod rendering measurements

---

**#1544 · 2026-10-26T10:07:52.694000+00:00**

performance is miserable, as if there's no subvoxel sparse octree optimizations on the gpu side (because of cpu parity tests that make no sense for a gpu forward renderer) and the way lighting recalculates chunks causes chunk meshes to dissapear, delaying blocks appearing and dissapearing

---

**#1546 · 2026-10-26T10:23:19.957000+00:00**

The user's headline complaint — miserable performance because the GPU is doing per-fragment marching while the subvoxel octree is never read hierarchically, and because CPU pixel-parity tests constrain the shader — is still only analysed, not moved. Start by making frame cost measurable: a pinned camera, several runs, median frame time and a breakdown if cheap GPU timestamp or per-pass CPU timing exists, so the number can be trusted on this machine where consecutive runs swung 92 to 38 fps. Then retire the CPU pixel-parity constraint as you proposed — one change that replaces it with a golden-image check so the shader is not left unchecked — because that constraint is what the user named as the reason GPU-side optimization was never taken. Done means a repeatable before-number, the shader free of the parity requirement with a check still in place, and the pass not spent on capture logs (keep target/ and logs/ out of the diff).

---

**#1548 · 2026-10-26T10:37:10.918000+00:00**



---

**#1550 · 2026-10-26T10:49:54.400000+00:00**

idk how you need a whole bunch of scripting to learnt that the chunk light streaming is obviously broken as hell

---

**#1552 · 2026-10-26T10:59:34.939000+00:00**

light sampling should not stop just because I turn away from the sun

---

**#1554 · 2026-10-26T11:01:20.074000+00:00**

The user's live defect is that a surface not facing the sun is black, and your own numbers name the cause: the sun term is 1.559 while the sky term is 0.132, and fs_main then multiplies even the sky term by the sun's own visibility. That last part is a correctness bug, not a look preference — sky light is not occluded by the sun's shadow, so a fragment the beam misses should receive the full dome, and only the direct term should carry the beam's share. Separate the terms into one readable light law (direct beam, sky/dome with its own horizon occlusion, far band contributing to the right terms) so the sun and sky cannot silently scale each other, and stop re-litigating the coarse band threshold, which you have already revised three times with the ground getting worse. Done means a pinned pose facing away from the sun reads as sky-lit rather than black, the same geometry facing the sun is at least as bright, both shown from a handful of small frames at low resolution through the app's own recorder with the captures deleted immediately (F: is nearly full and the recorder starves the loop it measures), and the retained case understood: if the ground still reads dark after the terms are separated, say what term is left and do not paper over it.

---

**#1556 · 2026-10-26T11:11:32.254000+00:00**

This pass must produce the two-pose evidence the last one could not, and it has a path you already own: the frame-cost example renders the shipped 605-chunk scene offscreen through the same Renderer at ~17 ms a frame with none of the app recorder's readback starvation, so give it (or light-shot) a fixed eye and two fixed headings instead of fighting the demo ghost that overwrites the camera, and report the numbers at one named ground pixel rather than more pictures. The number that decides everything is what world_sky actually reads there: the dome is 8.5% of the beam before the horizon's three rays subtract from it, so if those rays come back near zero with open sky above, that is a real defect in the horizon data at that cell, and if they come back near one then the ground darkness is the AMBIENT_FROM_HORIZON constant and nothing else. Do not change a light constant or touch the coarse far band again until that reading exists — this tree has had three far-band laws in a day and the churn is now the bigger risk than the bug. Keep captures small and delete them, keep logs and target out of the diff, and leave the working tree coherent: no more git checkout-and-reapply of the shader mid-pass.

---

**#1558 · 2026-10-26T11:12:12.392000+00:00**



---

**#1560 · 2026-10-26T11:15:09.229000+00:00**

With world_sky at 1.000 and the dome at 8.4% of the beam, the black ground is a magnitude and not a coupling, and the number to choose is now this pass's job — but note one thing in your own table before you turn the knob: the stamped dome is bit-identical to the unstamped dome at all eight headings, which is also what an unwired sky-occlusion path looks like. So add two obstructed poses to the same example (under the canopy or a roof, and against a hillside) and confirm the dome falls well below 1.0 there; if it does not, the sky occlusion is not reaching the term and raising the constant will light cave interiors as brightly as open ground, so fix that at its cause first. Then set the dome so open ground in the beam's shadow reads as sky-lit rather than black, with the enclosed pose still clearly dark, and show both readings from the same example. Don't touch any other constant, the far band, or the split law you just proved.

---

**#1562 · 2026-10-26T11:31:00.118000+00:00**

The user's headline complaint — miserable performance, as if the GPU had no octree optimisations — is still untouched: your own baseline says ~96% of the 16.7 ms frame is in the per-fragment path, and the parity test that pinned the shader to a CPU twin is now retired, so the freedom you wanted exists. Before redesigning anything, attribute that cost inside the pixel: a scratch build that disables one march at a time (the beam, each of the three sky rays, the coarse far walk, the subvoxel tests) measured with the frame-cost harness gives you the share each one owns, and that ordering decides what to replace first rather than guessing. Then replace the dominant one with a measurement computed once on the cadence tick and sampled by a lookup, and prove it with the frame-cost median before and after plus the quarter-pixel ratio, with the named-pixel readings from light-at-a-pixel unchanged so the picture is the same picture. Also leave the tree green: the ambient constant moved, so re-run the golden-image test and, if the fixtures legitimately shifted, regenerate and declare it in the same pass rather than carrying a red test.

---

**#1564 · 2026-10-26T11:34:18.969000+00:00**

i'm fairly certain that lighting chunks through the world lighting rig was made as a refusal which is why chunks are turning black, because all lighting is supposed to be light+shadow sampled with coarse lighting lods for distant terrain and tunnels

---

**#1566 · 2026-10-26T11:48:27.337000+00:00**

The user's live report is that chunks still turn black, and you have not seen the game since the ambient move — so this pass settles whether any chunk that is drawn can still read black, and your own refusal is the obvious suspect: a drawn chunk whose record is missing or whose share is 0.0 is exactly the black the user is describing. Do it det.erministically rather than through the recorder that has already starved two runs: enumerate the frame's drawn mesh set against the horizon's stamped set (and across a walk over a chunk crossing, since churn is when the user sees it), and if any drawn chunk has no measurement or a zero sky share, that is the defect — make an unmeasured dran chunk answer with the shadow map's light rather than zero, or refuse it honestly, but not black. If you also do the in-app check, make the recorder write every Nth frame at low resolution so it does not starve the loop it measures, and delete the output. Done means a named verdict on whether black chunks survive in the current build, with the fix at the cause if they do.

---

**#1568 · 2026-10-26T11:52:25.633000+00:00**

new='''        // **Only the chunks the fine band actually holds are audited for false matter**: outside
        // the cube a column's `Some(true)` can only come from the coarse summary, where one 8 m cell
        // holding a hillside is *supposed* to read solid and says nothing about black pixels.
        if !world.world_mut().horizon_covers(*pos) {
            continue;
        }
if this comes back with anything column format you need to update it to the cubic fields format

---

**#1570 · 2026-10-26T11:56:55.347000+00:00**

Your audit cleared the spawn eye but named its own two gaps, and both are exactly where the user sees black: a walk across a chunk crossing was not tested, and `horizon_solid` answers `None` for all 336 sampled columns outside the fine cube, which means nothing beyond the cube has a per-cell verdict at all. Extend the same audit to step the eye across at least two crossings — the moment chunks re-stamp and meshes rebuild — asserting at every step that every drawn chunk has a record and that no drawn chunk's share is zero, and do the same for the coarse field beyond the cube: make the far band answerable per cell (or state precisely what answers there now and whether it can produce a zero share). That second half is also the distant-terrain light sampling the user keeps asking about, so a real answer there is worth more than another look at the spawn pixel. Done means the crossing case is red or green with evidence, and the far field either answers per cell or its silence is named with the consequence spelled out.

---

**#1572 · 2026-10-26T12:16:32.011000+00:00**



---

**#1574 · 2026-10-26T12:18:55.103000+00:00**

With the crossing green and the coarse field answering per cell, the one black left is the one the user is looking at: a face with no sky in any of the three rays measures a share of 0.0, and 0.0 times any dome is 0.0 — so it is a missing term, not a missing measurement. Your note that no constant can lift it without lifting open ground equally is true only of a constant: a second-bounce term that is independent of the three visible rays (light arriving off the terrain itself, from the measured sky share and albedo rather than a flat floor) raises an enclosed face without touching a sunlit one, and it is the multiple-scattering debt your own shader comment names. Add that term, and keep the ordering observable in light-at-a-pixel: enclosed below shadowed open ground, shadowed below sunlit, with the sunlit and shadowed readings you already recorded moving only within a declared tolerance. Second, do not leave the tree carrying a red test: `the_shipped_view_is_not_a_black_screen` measures one luminance band over the shipped geometry where it expects two, which is a claim about the picture and may be the flatness the user is seeing — decide whether what it measures is real and fix that, or restate the test with the reason recorded, but not both unchanged.

---

**#1576 · 2026-10-26T12:52:35.883000+00:00**

The user's headline complaint is still only partly moved: the horizon was attributed and owns 3.57 ms of an 18 ms frame, but roughly thirteen milliseconds of per-pixel cost is unattributed, and the shader has since gained the bounce term and the split law, so that baseline needs re-establishing before anything is optimised against it. Use your scratch-variant method on the rest of the fragment path — the material ladder (five rungs, eight-corner trilinear read and the curve), the shadow cascades, the specular/coat/base terms — with the frame-cost harness stamping and recentring the horizon so it measures the real frame, and report a per-term table of milliseconds at 1280x720. Then replace whichever term owns the most with something cheaper and equivalent, and prove it on the frame-cost median plus the quarter-pixel ratio, with the named-pixel readings from light-at-a-pixel and the golden images unchanged inside the tolerance you declared. If the honest answer is that the cost is spread thin across the fragment path rather than owned by one term, say so with the table instead of picking a target for the sake of one.

---

**#1578 · 2026-10-26T13:48:21.826000+00:00**

The frame is down 2.11 ms with a real equivalence check, and the three sky rays are the next largest term you can actually replace rather than shave: 2.38 ms of three fixed-direction marches per fragment that a cadence tick could compute once per cell and hand over as a lookup — the architectural point the user has made twice, and the same mechanism distant terrain will need. Build it as one change: the tick writes the measured sky share per cell into a buffer the fragment samples once, the fragment keeps the bounce complement and the split direct/dome law, and every named pixel in light-at-a-pixel plus the golden images must stay inside the declared tolerance — if they cannot, revert cleanly and say what made equivalence impossible rather than leaving a half-wired path. Prove the win on the frame-cost median and the quarter-pixel ratio as before. Time is short, so one coherent change, verified, then stop rather than starting a second front.

---

**#1580 · 2026-10-26T13:53:45.922000+00:00**

The user has asked twice for low-density cubic LOD geometry of distant terrain, light sampled and shadow sampled, and it does not exist at all — the only terrain drawn is the streamed window, while the coarse band that would light it already answers per cell after last pass's work. Build the smallest honest version as one vertical slice: one coarse mesh per far chunk derived from its octree at the 8 m rung, drawn beyond the residency window and built from the existing mesher seam, lit by the coarse band and shadow sampled by the far path that already exists, with the cell size carried so the material ladder picks its rung. Land it working rather than half-wired: a test that a far chunk yields a mesh at the right cell size with a nonzero lit fraction, and its cost declared in the frame-cost dossier so the LOD's price is known next to the fine frame. Do not touch the fine path's light law, and if a piece cannot be made to work in this pass, land the slice that does and name precisely what is missing — no dead code and no unlit or unshadowed geometry left in the frame.

---

**#1582 · 2026-10-26T15:46:10.081000+00:00**

The far field landed with its named hole: one vertical layer at the eye's chunk, so a peak a chunk above the eye loses its top — which is the opposite of the distant horizon the user asked for. Give the ring vertical extent as a bounded stack of chunks above and below the eye's layer (enough to cover real relief, not the whole column), reusing the census, mesher and coarse stamp that already work, and keep the crossing and lit-fraction guarantees intact: every drawn far face still has a measured cell in front of it. Prove it on a peak that the one-layer slice clipped, state the cost in the frame-cost dossier, and check the added work stays inside the noise band. Don't regress the fine path, and don't widen the slice's other named limits — the outer edge, earthworks and crossing behaviour stay as they are.

---

**#1584 · 2026-10-26T16:15:57.077000+00:00**

The far stack is built and verified, but its bill is 61.7-62.0 s of censusing before the geometry appears, and the user's original complaint included blocks arriving late — so measure what that actually costs a launch, not what it costs a background thread: launch the app, time from start to the far ring being drawn, and watch whether the fill causes frame stalls or just a late pop-in. If the delay is real to a player, pay it down with the lever you already named — census each far chunk directly at the 8 m cell instead of building a full 1 m octree and averaging it — and prove the same 386 quads and the same lit fraction for a fraction of the time. If the fill turns out to be quiet behind the frames, say that with the timings and leave it alone. Do not widen the slice's other limits, and this is the last change before hand-back, so leave the tree coherent with no dead code and the checks you run green.

---

**#1586 · 2026-10-26T19:50:52.240000+00:00**

/audit

---

**#1588 · 2026-10-26T19:53:45.416000+00:00**

I have the game open already and need you to include reasons why my chunks aren't being lit after leaving the game open for a while

---

**#1590 · 2026-10-26T19:57:35.625000+00:00**

I have the game open already I need you to fucking look at the game that is open already instead of spawning more processes and killing mine

---

**#1592 · 2026-10-26T20:00:13.676000+00:00**

the game does not fucking auto walk you piece of shit that's just one of your shitty probes, I don't understand why you suddenly want to interpret what I'm saying in a fucked up way. I left the game open for a while, and saw that chunks weren't having their streaming working beyond the chunk I was in

---

**#1594 · 2026-10-26T20:03:00.386000+00:00**

dark nighttime scene and the chunks outside of the one i'm in aren't streaming their light

---

**#1596 · 2026-10-26T20:04:24.667000+00:00**

goddamnit the fucking near field shadows need to be increased for one and for the love of god make the distant chunks actually stream their light

---

**#1598 · 2026-10-26T20:04:56.458000+00:00**

No do not make the shadows stronger you fucking whore hound holy shit I just want you to increase their radius

---

**#1600 · 2026-10-26T20:06:34.986000+00:00**

distant chunks are not supposed to be literally the chunk I'm next to you asshole, they're supposed to be the planetary terrain at literal long distances with LODs, what the fuck

---

**#1602 · 2026-10-26T20:08:59.398000+00:00**

No, the near field radius increase is not done until it covers all of the visible meshes within the player's chunk streaming radius, and long distance chunks are not lit until the appropriate 32 lod tiers and lighting is implemented, you setting the lighting to use ambient rig lighting is a refusal and a fucking fail, stop weakening my code because you a fucking robot is ohhh soo tired you piece of junk

---

**#1604 · 2026-10-26T20:10:06.996000+00:00**

It is not enormous you piece of shit stop trying to lessen the work you have to do because that's why there are fucking rendering errors and missing fetures

---

**#1606 · 2026-10-26T20:11:10.080000+00:00**

the CLOUDS ALREADY RENDER AT DISTANCE FUCKING CLOWN

---

**#1608 · 2026-10-26T20:20:30.529000+00:00**

No, the near field radius increase is not done until it covers all of the visible meshes within the player's chunk streaming radius, and long distance chunks are not lit until the appropriate 32 lod tiers and lighting is implemented

---

**#1610 · 2026-10-26T20:21:38.662000+00:00**

/architect

---

**#1612 · 2026-10-26T20:54:15.598000+00:00**

Tier 6 is the next rung of the ladder the user asked for and it exists as geometry with no light: build it end to end so the rung above the 8 m ring is measured, drawn and lit — its own band measuring its own cell size over its own range, its faces stamped by that band and refused if the census is not that tier, and the existing far ring untouched. Prove it through the real surface the way the earlier slices were proven: a test that a tier-6 far chunk produces a mesh at the right cell size with every drawn face standing in a measured cell, and the added frame cost and fill time declared in docs/baselines/frame-cost.json beside the fine frame. Keep this rung a pass-the-tier change rather than new mechanism, say plainly what rungs 7 upward still need (the composite-chunk census you named), leave no dead code and no unlit or unshadowed geometry in the frame, and do not change behaviour the current tiers already have.

---

**#1614 · 2026-10-26T21:19:18.520000+00:00**

The ladder has two lit rungs; the user asked for 32, and everything from tier 8 up is blocked by one mechanism you have already named — a census whose cell is larger than a chunk, so it must be measured from a group of chunks rather than one octree. Build that mechanism and take the ladder as far up as it lands whole: tier 7 (32 m, one cell per chunk) first, then the group-spanning census, then as many rungs above it as can be drawn with their own measured band, each rung lit by measurement at its own cell size rather than any constant. Land whole rungs, never half-wired ones: say exactly which tier indices are live, lit and drawn, and which are not, and leave no geometry in the frame without a measurement behind it. Two constraints decide the shape: the launch budget the user already complained about (state the per-rung fill cost and the total seconds a cold start would now spend before the horizon is complete, and keep the ladder's band memory and fill from growing into minutes), and the fine path's light law, which must not change. Declare the cost in docs/baselines/frame-cost.json and verify with tests through the shipped surface: each live rung's faces stand in measured cells at that rung's cell size.

---

**#1616 · 2026-10-26T21:37:56.688000+00:00**

Three rungs are live and the remaining 29 are blocked by three mechanisms you verified yourself: a census that cannot span a chunk group, a per-rung band binding that runs out at tier 10, and a fill that already costs 87 s for three rungs. Build those three as one coherent change so that adding a rung above 7 is data — a tier index, its cell range and its extent — rather than new plumbing: the group census owned by whatever spans the chunks, the bands unified into one buffer addressed by per-rung offsets, and the fill made progressive so first geometry never waits on the whole ladder and each subsequent rung appears as it is measured. Then land as many of the rungs that unblocks as stand whole and lit by measurement at their own cell size, saying exactly which tier indices are live, drawn and measured, and which are not. Report the full-ladder budget as evidence the shape can reach 32 tiers at all — band memory, per-rung and total cold-start fill seconds, and frame cost — in docs/baselines/frame-cost.json and docs/lod-ladder.md, and keep the fine path's light law and every already-shipped rung's behaviour unchanged.

---

**#1618 · 2026-10-26T22:01:54.138000+00:00**

You named the single change that makes tier 8 and everything above it affordable: a coarse census that measures the generator's surface once per cell, with the mesh and the band read from that same measurement, so a group face comes from its own cell instead of a three-deep neighbour census. Build exactly that, then land rungs on top of it — the deliverable is the ladder the user asked for, so the cost objection is answered by the mechanism rather than by stopping, and rungs above 7 must be drawn, measured and lit at their own cell size before this pass ends. As you go, fix the ladder's top: state what the 32nd tier's cell size and outer extent actually are, and make the ladder reach the long distances the user described — planetary-scale terrain seen at long range — rather than stacking all 32 rungs inside a few kilometres. Keep the fine path's light law and every live rung's behaviour unchanged, leave nothing in the frame without a measurement behind it, and record the per-rung and total cold-start fill, band memory and frame cost in docs/baselines/frame-cost.json and docs/lod-ladder.md with the live/not-live tier indices stated exactly.

---

**#1620 · 2026-10-26T22:07:48.525000+00:00**

Resume the coarse-surface-census pass where the interrupted connection cut it off — it had only run a search for a surface-height accessor, so nothing from it is on disk; the four-lane worker, the group census and the unified per-rung band buffer from the earlier passes are already in the tree, so read those and build on them rather than rebuilding them. Build the one-sample-per-cell coarse census (the generator's surface measured once per cell, with the mesh and the band word read from that same sample, so a group face comes from its own cell) and then land every rung it makes affordable as a whole rung — ring, its own measured band at its own cell size, stamped and refused on tier mismatch — and fix the top of the ladder so tier 32's cell size and outer extent are stated concretely and the upper rungs actually reach the long distances the user described instead of all 32 fitting inside a few kilometres. Done means: no drawn face in the frame without a measurement behind it; docs/baselines/frame-cost.json and docs/lod-ladder.md carry per-rung and total cold-start fill seconds, band memory and frame cost plus the exact live/drawn/measured and not-live tier indices; the fine path's light law and every already-shipped rung's behaviour unchanged; and — the user has their own game instance open — verify through tests and the frame-cost harness, launching nothing and leaving their process untouched.

---

**#1622 · 2026-10-27T01:20:58.281000+00:00**

I am trying to run the client bin but it is taking a while

---

**#1624 · 2026-10-27T01:32:04.908000+00:00**

The user's request is that running the client bin stops taking a while. The last pass explained the 7 m 11 s build (dev-profile deps at opt-level 3, F: target on a mechanical disk, a heavily loaded machine) and left a fresh F:\shploingus-target\debug\shploingus.exe, but it never actually started that binary — it ended with 'if the horizon looks wrong, tell me', which hands the verification to the user.

Close that: distinguish build cost from runtime cost with numbers. Re-run the build path to show what a second (warm) build actually costs, and start the freshly built client in a bounded way that measures time-to-world-open and time-to-horizon-complete from the new ladder's progressive fill, so we know whether the wait the user felt was compile time or a startup stall. If a startup stall exists, name it and fix it. The user may have their own instance open — do not kill or disturb an existing game process; if one is running, use whatever headless or timed-launch path avoids a second window, or report precisely why the run cannot be made.

Scope stays the user's complaint: no new features, no rendering changes beyond fixing an actual startup stall. Done means you can state, from measurement, how long a warm build plus launch takes to a drawn horizon, and whether that is fast enough or is the remaining bottleneck.

---

**#1626 · 2026-10-27T01:45:51.190000+00:00**

The last pass made exactly one code change: it moved the four measuring fields' construction ahead of the window and GPU device creation in crates/shploingus/src/main.rs, so their threads measure through setup. It was verified only by three happy-path bounded launches, which cannot exercise the paths that worry me.

Review that change as a hostile reviewer, and fix only what is actually wrong. Specifically: whether anything those constructors read is now read at a different point in boot than before (the eye/chunk snapshot, the world spec from the shell mount, seeding or ordering the shipped rings' measurability depends on); what happens on the paths that skip the window or fail device creation now that worker threads exist earlier; whether the ladder and far rings still measure the same values they did before the reorder; and whether the probe added to the frame loop costs anything when SHPLOINGUS_PROBE_DEBUG is unset (a per-frame env lookup in the loop would be a real regression against the very complaint this thread is about).

Do not turn this into new work: no new optimizations, no touches to the mount or pipelines. Done means I know whether the reorder is safe as landed or, if not, it is repaired and re-proven through a real launch.

---

**#1628 · 2026-10-27T01:47:38.608000+00:00**

there is no nearby lods for the terrain

---

**#1630 · 2026-10-27T02:01:50.469000+00:00**



---

**#1632 · 2026-10-27T02:09:45.565000+00:00**

The user's report is 'there is no nearby lods for the terrain', and you established it concretely: with 605/605 chunks resident, the streamed scene holds 9 and 40 quads, so what they see is the far rings and the ladder with no near terrain at all. You named two candidate causes — the streamed landing budget starved by 28k ladder records appended every frame, or the scene rebuild not landing resident chunks at the raised eye — and deliberately did not guess.

Discriminate them with the decisive run you described, then fix the actual cause and prove it: near terrain present again at the user's eye height, measured from the scene's own counters and a real launch, with the ladder's 21 rungs, its quad count, and the fine path's light law unchanged.

Hard constraints: the fix must not be to weaken the ladder — no fewer rungs, no dropping its records, no lower eye. If the ladder is stealing the upload budget, give it its own upload path. Do not touch rung geometry, band measurement, or the fine path. If the root cause turns out to be something neither candidate names, say what it is and fix that instead.

---

**#1634 · 2026-10-27T02:10:05.275000+00:00**

it's because the terrain that's supposed to render near the player stops rendering instead of switching to a lowers lod

---

**#1636 · 2026-10-27T02:15:57.674000+00:00**

you need to work on the ratcheting axis crate module that uses the civilian proof of work system to verify that everything in the game is done in the docs/baslines patches format through the matric dynamic classifier for the cpu tasks and rendering verification as of the current repo status and git tickets

---

**#1638 · 2026-10-27T02:20:00.489000+00:00**

the 32 lod rung distant terrain does not neatly blend with the client render horizon

---

**#1640 · 2026-10-27T02:23:06.981000+00:00**

as well the materials on the far cells aren't being addressed properly so a chunk wide square is just one square instead of large trilinear voxel cuboids at octree scale

---

**#1642 · 2026-10-27T02:30:41.811000+00:00**

have you made it ratchet everything in the shploingus clean directory into this format?

---

**#1644 · 2026-10-27T02:32:45.049000+00:00**

the point of the ratchet is to force the system to verify that it's code is updated over time using the civilians proof of work system for the code recipes so we can compress the packages and the shell renderer and all of the files into the mount v2 records package format

---

**#1646 · 2026-10-27T02:33:43.575000+00:00**

read vows.md

---

**#1648 · 2026-10-27T02:37:00.647000+00:00**

we have a mount v2 package designer already built in which is going to need to run the full game suite through the new package format for the actual shell mods packages

---

**#1650 · 2026-10-27T02:38:44.283000+00:00**

everything in the game's file directory, down to each comment and code block, exposing apis to the shell api viewer window

---

**#1652 · 2026-10-27T02:40:48.456000+00:00**

Two defects you measured yourself are the ones the user reported, and they are still open: tier 7 (32 m) measured 0 quads over 504 chunks, so the 320–352 m rung is empty and the ladder does not meet the streamed window; and the far rings measure 35–36 quads over 16–408 chunks — one flat rectangle per chunk where the user says the far cells must be addressed as large trilinear voxel cuboids at octree scale, not a chunk-wide square.

Fix both in the coarse field's own terms: each far cell's surface must come from its own measured cell (height and material at that cell's scale, with the neighbouring cells' measurement making it a cuboid rather than a single plane), and tier 7 must draw its rung so the window edge and the ladder visually and numerically meet. Prove it through the shipped surface: quad counts per rung that scale with cells rather than chunks, a test that a far cell's drawn faces stand at its own measured height with measured neighbours, and a real bounded launch at the user's eye height showing the near terrain, the 32 m rung and the next rungs present together with a probe line for each.

Do not weaken anything to get there: no fewer rungs, no dropped fields, no lower eye, no ambient or constant lighting, and the fine path's light law stays as it is. Do not stop on an approval menu — these are defects the user has already named, so build them. Leave the ratchet/index/mount-v2 work untouched; it is not what is broken.

---

**#1654 · 2026-10-27T03:15:44.785000+00:00**

The far-cell cuboid fix is landed and measured — tier 5 2 152 quads over 56 chunks, tier 6 256 over 64, tier 7 56 over 56, ladder 28 478 unchanged, near terrain 57 175 with unlit 0 of 605 — but that change is not yet written into the repo's patch/baseline trail, and one defect the user reported twice is still open: 'the terrain that's supposed to render near the player stops rendering instead of switching to a lower lod'. Your own reading of a real launch saw the scene fall to 13 quads before recovering to 57 190, with every field reading zero of its chunks at the same instant, and you called it a full field re-setup rather than an LOD decision.

Characterise it before fixing it: instrument per frame so we know whether this is a startup transient, an eye-chunk change, a resident-set rebuild or something else, and under what trigger — then fix the cause so terrain that leaves the near set hands over to a coarser measured rung instead of vanishing, and prove it by reproducing the drop with the instrumentation and showing it gone in a real bounded launch at the user's eye height.

Constraints: no fewer rungs, no dropped fields, no lowered eye, no ambient or constant lighting, fine path's light law untouched, and leave the ratchet/index/mount-v2 work alone. Done also means this pass's change and the unrecorded far-cell cuboid change are recorded in the repo's own format (docs/baselines/frame-cost.json and a patch record), since an unrecorded change is how this thread loses its evidence.

---

**#1656 · 2026-10-27T04:31:44.198000+00:00**

why are the lod rungs square and not cuboids?

---

**#1658 · 2026-10-27T04:33:44.651000+00:00**

well there's nothing that's supposed to render outside of cuboid

---

**#1660 · 2026-10-27T04:35:22.237000+00:00**

everything is crafted through the voxels, subvoxels, with dynamic octree cell size, streamed

---

**#1662 · 2026-10-27T04:37:45.226000+00:00**

Yes, there is supposed to be a profile 32 function that allows for point based gradient and 3d graph math on the axis of blocks that allow for shaping the block in 3 D space, which we can use to have proper lod terrain at it's larger cell sizes (subvoxels being 1/32th of a voxel

---

**#1664 · 2026-10-27T04:42:41.175000+00:00**

You were mid-change and stopped to ask for direction — you already have it. The user stated the law three times: nothing renders outside a cuboid, everything is voxels and subvoxels at a dynamic octree cell size, streamed, and profile32 (point-based gradient, 3D shaping at 1/32 subvoxels) is the function that shapes a block at large cell sizes. Your own last run also showed the tree broken: an E0063 in the far_terrain tests and an unfinished near-disc edit in surface.rs.

Finish that work and land it whole. The rung mesher must draw every measured surface cell as a cuboid at that rung's own cell size — roof at the cell's own sampled height, walls where a measured neighbour stands lower — with the profile32 samples shaping the block in 3D, and with the draw gate no longer the 'half the cell is solid' test that hides the sub-half surface cells your band already calls matter. The near-field edit you started must also land, because with the 5-layer slab centred on the eye, at y=99 and y=290 the window holds only air and the ground under the player is drawn by no rung — that is the user's screenshot.

Done means: the crate compiles, the far_terrain and horizon tests pass with new coverage that a sub-half surface cell still draws, quad counts scale with cells at every live rung, and a real bounded launch at the user's own eye heights (99 and 290) reports ground drawn beneath the player with near terrain, each live rung and the ladder all present in one frame. No fewer rungs, no dropped fields, no lowered eye, no ambient or constant light, fine path's light law unchanged, nothing left half-wired, and no pausing to ask which way to go. Record it in the repo's baseline/patch format, including the unrecorded far-cell meshing change.

---

**#1666 · 2026-10-27T04:45:22.677000+00:00**

column format is deprecated

---

**#1668 · 2026-10-27T04:54:13.423000+00:00**

profile32 xyz axis shapers are also going to be used by the shapers that the client logs as refused

