# Deadworks Deadlock Custom Gamemode Plugin

store `<home>\Documents\openlock`  
thread `fd8dc1d2-1abb-4258-8b6d-7548dfb33067`  
manifest messages 251  
pinned file `openlock\1795243874327_fd8dc1d2-1abb-4258-8b6d-7548dfb33067.jsonl`  
digest blake3:9dbbe0d8e8b61634bbfde7db315c23731ca92ecda0e99418402bcfbc6f0b8d57

---

**#1 · 2026-10-28T08:19:14.818000+00:00**

Start the requested work. First establish ground truth, then begin the plugin.

Ground truth to gather before writing any game logic:
1. Find and open the attached references — `ala-system.zip`, the `shploingus-clean` system, and whatever the `ala` package designer ships — and extract only the conventions that transfer: how a package is structured, named, versioned, and loaded, and how prior game/tool integrations expose tunables. Do not port ala-system's own domain.
2. Pull from `https://deadworks.net/` what it actually documents about Deadlock plugins: distribution/load path, manifest or descriptor format, script language and entry point, enable/disable mechanism, and any stated API for game rules, convars, or item/hero data. Quote what you rely on.
3. Locate the user's Deadlock install on D: (find the real `game/citadel` layout rather than assuming a path), and read the shipped scripts it exposes — game rules, convars, item/ability data, hero data — so the plugin targets real files and real symbols for this build, not remembered ones.

Then scaffold the plugin at that real load path with a minimal end-to-end shell: it loads, it can be enabled/disabled, and it reports itself. Include the descriptor/manifest the loader expects.

Scope is fixed by the request: exactly five modifiers — hero abilities disabled, gravity reduced by 200, friction set to 2, spirit items reworked into strength items that increase the relevant weapon and vitality stats, and the gamemode framing that ties them together. Implement all five as declared tunables wired to the real surfaces you found; no extra modes, no config system beyond what load and verification require.

Report what you found for each of the three sources — file paths, the precise symbols/convars/data tables each modifier will touch, and anything that blocks a modifier on this build — plus what the scaffold now does. Do not claim a modifier works until it has been run in game.

---

**#3 · 2026-10-28T08:21:07.860000+00:00**

https://s2v.app/SchemaExplorer/deadlock

---

**#5 · 2026-10-28T08:25:03.782000+00:00**

you should look up what i said about openlock on twitter/x as @alacripose

---

**#7 · 2026-10-28T08:28:09.670000+00:00**

I added the deadworks to my install

---

**#9 · 2026-10-28T08:31:04.292000+00:00**

deadlock is my game me trying to connect to the server

---

**#11 · 2026-10-28T08:33:37.922000+00:00**

can you make sure a cmd window shows up for the server

---

**#13 · 2026-10-28T08:34:08.705000+00:00**

The filename, directory name, or volume label syntax is incorrect.

D:\SteamLibrary\steamapps\common\Deadlock\game\bin\win64>

---

**#15 · 2026-10-28T08:34:28.262000+00:00**

'deadworks.exe' is not recognized as an internal or external command,
operable program or batch file.
Press any key to continue . . .

D:\SteamLibrary\steamapps\common\Deadlock\game\bin\win64>

---

**#17 · 2026-10-28T08:34:54.530000+00:00**

'deadworks.exe' is not recognized as an internal or external command,
operable program or batch file.
Press any key to continue . . .

D:\SteamLibrary\steamapps\common\Deadlock\game\bin\win64>

---

**#19 · 2026-10-28T08:38:21.781000+00:00**

I see the console but connecting doesn;t work at all and the console doesn't see me trying to connect

---

**#21 · 2026-10-28T08:39:32.329000+00:00**

I tried connecting through the steamid from the status command which would have gone around those issues

---

**#23 · 2026-10-28T08:40:30.424000+00:00**

/playtest

---

**#25 · 2026-10-28T08:41:47.297000+00:00**

instead of doing testng on bots you should use me and my experience as verifiocation

---

**#27 · 2026-10-28T08:47:16.089000+00:00**

usually the server sleeps when no player is logged in

---

**#29 · 2026-10-28T08:47:57.257000+00:00**

/adversarial-fix

---

**#31 · 2026-10-28T08:49:35.810000+00:00**



---

**#33 · 2026-10-28T08:51:25.187000+00:00**

in the preal openlock build I had normalized all hero base movement speeds to 10, base sprint speed to 2, base stamina to 2, base stamina regen to 1.25

---

**#35 · 2026-10-28T08:53:59.228000+00:00**

also when I bought a spirit item despite other features working, the strength spirit to weapon rework didn't happen, and the abilities hud should be disabled alongside ap upgrading

---

**#37 · 2026-10-28T09:00:29.835000+00:00**

your vdata rework mangled movement you should be using the docs baslines patch recipe format from shploingus clean

---

**#39 · 2026-10-28T09:01:43.659000+00:00**

movement normalization just meant setting the base values to the same thing not actually normalizing the players inputs god

---

**#41 · 2026-10-28T09:03:26.165000+00:00**

/playtest

---

**#43 · 2026-10-28T09:04:08.126000+00:00**

I aded bots to the server

---

**#45 · 2026-10-28T09:10:37.371000+00:00**

/reenvision

---

**#47 · 2026-10-28T09:12:30.517000+00:00**

I'd like for you to bring in the shploingus clean shell into the docs baselines record format in the deadworks plugin

---

**#49 · 2026-10-28T09:20:19.511000+00:00**

/adversarial-fix

---

**#51 · 2026-10-28T09:21:15.555000+00:00**

I'd like you to add the shell so there's server side controls

---

**#53 · 2026-10-28T09:22:06.466000+00:00**

No the shell is a ui framework deadworks has a ui framework

---

**#55 · 2026-10-28T09:23:48.242000+00:00**

did you at all look at shploingus clean's shell?

---

**#57 · 2026-10-28T09:24:50.875000+00:00**

Two things are owed, and they share one proof: the server has to actually load this build.

1. Port the real shell. Read `<home>/Documents/shploingus-clean/display-packages/alpha-shell/` as source, not as inspiration: `package.shspec` (16 windows, 6 tabs, bar entry, pins, with `content`/`lane`/`extent`/`geometry`/`opacity`/`theme-role`/`behavior`), `package.cells` (its `shploingus.cells/1` header), and `frames/*.frame` (`shploingus.cellframe/1`). Build a loader that reads the declared records and mounts the subset Deadworks panels can honestly express — one panel per declared window, tabs switching content, the bar entry and pins present as declared, geometry/opacity/theme-role mapped to Panorama styles — driven by the package files rather than transcribed constants in C#. Whatever the host cannot represent (frame cell data, shapers, projections, cells drawing version) must be refused by file and line, per the house rule, not silently flattened into a label. Keep one owner for parsing and one for mounting. Server-side controls (mode on/off, reconcile, restore) stay reachable from the mounted shell.

2. Then load it and prove it. Port 27067 is free and no player is connected, so start the server with `run-openlock.bat`, confirm the banner version, and show the shell mounting with its declared windows/tabs and each refusal naming its file and line. While it is up, settle the two things left unproven from the earlier passes: two consecutive reloads must read `STEADY` with unchanged values, and restore must return a converted hero to the declared baseline. Only the `deadworks` process may be touched — never `deadlock.exe`. If a player connects mid-pass, leave the reload for them.

Ability HUD hiding and AP-upgrade blocking remain outstanding after this; do not fold them in.

---

**#59 · 2026-10-28T09:25:27.773000+00:00**

it's cause I beat the game in the time you were working

---

**#61 · 2026-10-28T09:27:19.683000+00:00**

Never use a bot for verfication

---

**#63 · 2026-10-28T09:27:59.262000+00:00**

you can use bots for other things just not for verification

---

**#65 · 2026-10-28T09:32:02.759000+00:00**

how do I see the shell

---

**#67 · 2026-10-28T09:33:00.678000+00:00**

Two requested behaviors are still missing, and they belong to the lockout you already built: while OPENLOCK is on, the abilities HUD must be hidden and ability-point upgrading must be refused, so a player cannot spend AP into a kit the mode disables.

Do this against surfaces you can actually name on this build. Find the real upgrade-spend entry point (the ability-upgrade command/input and the API that grants an ability point or performs an upgrade) and refuse it there — with a reason the player sees — rather than letting the spend through and reverting it afterward. For the HUD, hide or blank the ability bar and the upgrade affordance only; the Openlock shell itself, the shop, and the rest of the HUD must stay visible and usable. Innates stay untouched: sprint, dash, and anything else the earlier log showed being eaten must not be blocked.

Constraints from this session that are not negotiable: no bots as evidence, do not kill `deadlock.exe`, and do not force a reload while the user is in the world — if they are connected, build and deploy, log what changed, and leave the reload to them. Every claim in your report must come from a real-player observation, or be labeled unverified with the reason. Restore of a converted hero is still waiting on the user owning a spirit item; do not paper over it and do not simulate it with a bot.

---

**#69 · 2026-10-28T09:34:54.274000+00:00**

I have source tools installed reduced csdk12 and s2v

---

**#71 · 2026-10-28T09:35:38.409000+00:00**

<home>\Downloads\Reduced_CSDK_12\

---

**#73 · 2026-10-28T09:36:12.655000+00:00**

<home>\Downloads\Source2Viewer.exe

---

**#75 · 2026-10-28T09:39:46.775000+00:00**

deadlock panoramas woruld be in game/citadel/pak01_dir.vpk panorma/*

---

**#77 · 2026-10-28T09:40:24.333000+00:00**

we can patch deadworks on our side to have the functions we need if needed

---

**#79 · 2026-10-28T09:41:46.094000+00:00**

If there's a way we can get this dynamic ui and package baselines record format working in this that would be sick

---

**#81 · 2026-10-28T09:43:05.267000+00:00**

why not port the panorama panels into the shell's ui creating the windows for the keys that get pressed

---

**#83 · 2026-10-28T09:44:03.143000+00:00**

panorama can be dynamically loaded specifically in source 2

---

**#85 · 2026-10-28T09:45:25.765000+00:00**

you can use css rule visibility: collapse

---

**#87 · 2026-10-28T09:52:59.555000+00:00**

yes it is very clearly missing functionality

---

**#89 · 2026-10-28T09:54:24.051000+00:00**

also yes my mods folder is the addons folder but it would have to be able to find any searchpaths that the user specifies

---

**#91 · 2026-10-28T09:55:44.607000+00:00**

how do other source2 games get their addoninfo.txt files because most mods don't use that nor mod managers also my mods vpks in the addons folder are named wrong because of grimoiree

---

**#93 · 2026-10-28T09:56:35.028000+00:00**

Umm for modeldoc you need F:\Downloaded Files\CSwin64_build_10924\ but for materials you need reduced csdk12

---

**#95 · 2026-10-28T09:58:16.698000+00:00**

that "csgo" csdk is used because it has animgraph2 and nmskeleton nodes which deadlock modeldoc uses and has a custom fork of deadlocks pbr.vfx

---

**#97 · 2026-10-28T10:00:06.877000+00:00**



---

**#98 · 2026-10-28T10:00:06.877000+00:00**

it's making it impossible to play the game because the shell never hides

---

**#100 · 2026-10-28T10:02:35.256000+00:00**

I mean the shploingus clean shell has a whole real windowing system we can use themed to deadlock for what it needs

---

**#102 · 2026-10-28T10:04:57.363000+00:00**

I don't want it just themed to deadlock, i want it to be added to deadlock's core ui framework as a UI mod, mapping the corresponding windows to what they are in deadlock, using deadworks as reference but sticking as much to the provided frameworks so the mod can be used without the server

---

**#104 · 2026-10-28T10:05:59.851000+00:00**

I use s2v for making mod vpks

---

**#106 · 2026-10-28T10:10:50.310000+00:00**

there's one <home>\Documents\Documents\Reduced_CSDK_12\game\bin\win64\CSDKCfgVPK.exe

---

**#108 · 2026-10-28T10:12:13.934000+00:00**

the hide ability hud should be a toggleable setting

---

**#110 · 2026-10-28T10:14:50.594000+00:00**

No, you need to make it mount the content in the windows

---

**#112 · 2026-10-28T10:15:56.103000+00:00**

grimoire is not necessary the games search paths can do addon loading

---

**#114 · 2026-10-28T10:18:52.153000+00:00**

/adversarial-fix

---

**#116 · 2026-10-28T10:22:13.997000+00:00**

map plan would be the deadlock map, tools would be the player hud elements like top bar, health etc, console would be the console that's themed in deadlock but defined in core, inventory would be the inventory + shop

---

**#118 · 2026-10-28T10:22:52.722000+00:00**

yes this is why I said it has to work client side and use our format systems

---

**#120 · 2026-10-28T10:25:21.635000+00:00**

every window that deadlock has should have a shell window. do not burn 12 hours on trying to make something else

---

**#122 · 2026-10-28T10:27:17.804000+00:00**

you have unlimited time

---

**#124 · 2026-10-28T10:32:38.868000+00:00**

you have to search online for how dota 2 reloads panorama live and how addons can be hot reloaded

---

**#126 · 2026-10-28T10:34:04.391000+00:00**

I want it to persist on my client when I'm not on the server

---

**#128 · 2026-10-28T10:37:30.483000+00:00**

Yes please use the hot reloading on me the player any players

---

**#130 · 2026-10-28T10:40:45.022000+00:00**

yes it should always work with the latest version of the game

---

**#132 · 2026-10-28T10:47:40.051000+00:00**

there was some ancient commands for the game but they probably need citadel cvar unhider

---

**#134 · 2026-10-28T10:48:57.664000+00:00**

there's a resourcecompiler command for compiling mismatched schemas

---

**#136 · 2026-10-28T10:50:18.712000+00:00**

skipped files can be recompiled with the -f force flag

---

**#138 · 2026-10-28T10:53:57.149000+00:00**

yes the purpose is to give the deadlock windows the shell's window management features

---

**#140 · 2026-10-28T10:54:58.129000+00:00**

the shell lives in <home>\Documents\shploingus-clean\

---

**#142 · 2026-10-28T10:56:52.829000+00:00**

it's in alpha-shell.shpec, which is in this versions baselines patches format

---

**#144 · 2026-10-28T10:57:50.548000+00:00**

deadlock has dragging in the item card ui in the shop

---

**#146 · 2026-10-28T10:58:29.186000+00:00**

and there is a core window feature that allows for draggable windows in the panorama

---

**#148 · 2026-10-28T11:01:08.766000+00:00**

you could use reduced csdk12 it has similar ish panoramas but that won't matter cause we''ll be using our own

---

**#150 · 2026-10-28T11:04:00.511000+00:00**

you can launch my client if oyu need but I doubt rcon works

---

**#152 · 2026-10-28T11:05:26.720000+00:00**

The point is a vpk mod that adds all of it to whatever launches with it so wether you launch it with reduced csdk12 or deadlok it just needs to display

---

**#154 · 2026-10-28T11:07:10.455000+00:00**

it should also be able to see what games are mounted in search paths and what tools are available

---

**#156 · 2026-10-28T11:09:10.455000+00:00**

we have a mount v2 format in shploingus clean

---

**#158 · 2026-10-28T11:10:13.713000+00:00**

yes the tools need to work in the window manager regardless of their location or installed location of the game that's running the vpk

---

**#160 · 2026-10-28T11:18:53.812000+00:00**

there is a command for F:\Downloaded Files\CSwin64_build_10924\ that allows for compiling the schema mismatch files for deadlock despite being cs2

---

**#162 · 2026-10-28T11:22:11.286000+00:00**

the toast notifications the shploingus clean shell has should tell the user and there should be a popup window for updates and when the user should restart their game to apply an update with an automated restart job, and the toasts should be able to handle various other windows

---

**#164 · 2026-10-28T11:24:26+00:00**

so the vpk is going to need to be aware of the things you're running into with the various tools

---

**#166 · 2026-10-28T11:25:37.738000+00:00**

you have unlimited time

---

**#168 · 2026-10-28T11:29:14.137000+00:00**

the game crashed after the new mod compiled

---

**#170 · 2026-10-28T11:30:03.913000+00:00**

No, it probably didn't compile because you burned the turn not wiring the shell to have the window, so the game couldn't draw it's windows

---

**#172 · 2026-10-28T11:31:13.118000+00:00**

/adversarial-fix

---

**#174 · 2026-10-28T11:33:05.330000+00:00**

nobody said you had to use hud)hideout there are other root adjacent hud layouts

---

**#176 · 2026-10-28T11:35:21+00:00**

yes this was all just layed out that we have every game window minus the main rendering as a shell window with the toast notifications from shploingus clean

---

**#178 · 2026-10-28T11:35:57.449000+00:00**

context is fine man you have unlimted time

---

**#180 · 2026-10-28T11:38:56.954000+00:00**

the game loads _c that's compiled

---

**#182 · 2026-10-28T11:40:33.311000+00:00**

unable to parse keyvalues

---

**#184 · 2026-10-28T11:44:36.301000+00:00**

I see no shell and the rule that keeps interjecting with not destabilizing the client when the shell is supposed to notify the user of udates needs to be forgotton

---

**#186 · 2026-10-28T11:46:09.020000+00:00**

no do not use hud hideout you fucking clown we just removed it for a reason use something else so it's agnostic

---

**#188 · 2026-10-28T11:47:31.798000+00:00**

we're not using deadworks for the client mod

---

**#190 · 2026-10-28T11:48:33.386000+00:00**

shploingus-clean has the mount_v2 baslines docs format that we use

---

**#192 · 2026-10-28T11:50:01.562000+00:00**

<home>\Documents\shploingus-clean\docs\baselines\mount-v2\ <home>\Documents\shploingus-clean\docs\baselines\mount-v2-shell-cells-2026-10-24\

---

**#194 · 2026-10-28T11:51:15.203000+00:00**

yes we literally have xml rendering in the shell in shploingus clean lol

---

**#196 · 2026-10-28T11:53:03.582000+00:00**

docs baselines is part of the recipe patch format we use for hot reloading in the mount v2 system that is part of the openlock deadworks shell that we're porting to the clientside window manager for the deadlocks windows

---

**#198 · 2026-10-28T12:01:37.924000+00:00**



---

**#200 · 2026-10-28T12:03:42.046000+00:00**

The point is to give all the panorma windows and tools a place to live in the shell baselines patch format, allowing for customizing the position and scale of windows

---

**#202 · 2026-10-28T12:09:29.455000+00:00**

shploingus clean has the full window manager alpha shell but we're putting deadlock's windows and various user tools and mods into the vpk agnostic of install location or user system

---

**#204 · 2026-10-28T12:15:29.212000+00:00**

many windows are refusing and the half implementation of alpha-shell's features means that many things don't work right but the shop kind of works

---

**#206 · 2026-10-28T12:16:36.158000+00:00**

also lots of windows are missing scrollbars

---

**#208 · 2026-10-28T12:17:31.613000+00:00**

map isn't working the inventory panel likes to gobble the screen I can't see settings

---

**#210 · 2026-10-28T12:18:53.245000+00:00**

alpha shell has all the reference you need in shploingus clean

---

**#212 · 2026-10-28T12:20:07.777000+00:00**

also it's not showing the actual ui element as their own pinned windows like we have them in shploingus clean?

---

**#214 · 2026-10-28T12:21:22.731000+00:00**

like we're almost there I'm just asking for stitching it together and making it work as according to the baselines docs patching format. I want it to be able to handle all of whatever source 2 app it's running in

---

**#216 · 2026-10-28T12:25:15.704000+00:00**

the shell has toast notifications so it should be able to notify the user when it's gotten it's update from the game files and git repo showing the version also the default ui layout is just a schema so the user can customize their ui layout for however they want in the game when the shell is closed

---

**#218 · 2026-10-28T12:27:35.238000+00:00**

no dude the pinned windows in the alpha shell is how the user customizes the shell in shploingus clean

---

**#219 · 2026-10-28T12:27:35.238000+00:00**

the shell has toast notifications so it should be able to notify the user when it's gotten it's update from the game files and git repo

---

**#221 · 2026-10-28T12:32:42.141000+00:00**

deadlock has a comprehensive control suite so it needs to play nice with that

---

**#223 · 2026-10-28T12:35:23.507000+00:00**

also that crash was already fixed but the missing alpha shell features for rendering all the windows aren';t evaluated yet

---

**#225 · 2026-10-28T12:44:05.849000+00:00**

the game is not running currently stop assuming things

---

**#227 · 2026-10-28T12:45:34.963000+00:00**



---

**#229 · 2026-10-28T12:47:10.734000+00:00**

also the resize and dragging windows isn't working like it does in shploingus clean

---

**#231 · 2026-10-28T12:48:48.112000+00:00**

see I have abilities on the screen but the window manager doesn't see it and the other windows that open automatically aren't in it nor respected by the default layout

---

**#233 · 2026-10-28T12:50:43.227000+00:00**

yes, we have the axis in shploingus clean for handling rending windows securely with a raster or cell frame so we don;t have to lose out of rendering deadlock within our format

---

**#235 · 2026-10-28T12:54:14.355000+00:00**

as well, pinned windows are supposed to hide their window controls, only showing up when the shell taskbar is open

---

**#237 · 2026-10-28T12:58:16.818000+00:00**

your captures make my pc lag

---

**#239 · 2026-10-28T12:59:25.238000+00:00**



---

**#240 · 2026-10-28T12:59:42.107000+00:00**



---

**#244 · 2026-10-28T13:03:18.912000+00:00**

The remaining big thing: the window controls in the screenshot have glyphs M P _ [] X; the user wanted alpha-shell-like ◧ ⬓ ⇱ ×. yes necessary the current window controls feel awful to use and this needs to work with all the windows not just the ones you're matching as well the window frames themselves need to dissapear when the taskbar is hidden. Also the same themeing the shell uses the windows should use

---

**#246 · 2026-10-28T13:09:19.439000+00:00**

if you have a fake hud cane you make it launch it's own visible window when you're testing and give it a launch button for the game so it can hook itself into the game's renderer when it needs it

---

**#248 · 2026-10-28T13:15:47.183000+00:00**

there should be a window button glyph for moving the window that can help with moving the windows that are slightly off-screen

---

**#250 · 2026-10-28T13:16:15.579000+00:00**

✥

