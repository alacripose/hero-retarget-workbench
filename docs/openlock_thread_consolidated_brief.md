# OpenLock, Confluent Dreams, the Meridian, and the Interline
 https://chatgpt.com/share/6afd66d5-30d8-83e8-9fcf-cd2042f0e13e
## Consolidated discussion record and project-worldbuilding brief

**Compiled:** 18 November 2026  
**Purpose:** Preserve the major ideas, references, naming explorations, project relationships, fictional-world concepts, and unresolved decisions from the discussion thread in one portable Markdown document.

> **Scope and fidelity note**  
> This is a detailed reconstruction and synthesis of the discussion, not a verbatim transcript. It consolidates the available conversation context and research notes. Where a point came directly from the user's descriptions, it is marked as an established user-stated concept. Where the document draws a structural conclusion from several details, it is marked as an interpretation or proposal. Unresolved questions are deliberately left unresolved rather than converted into decisions.

---

# 1. Executive summary

The thread is fundamentally about finding a name and a coherent identity for a large, interconnected creative and technical family. The original name **OpenLock** began as a platform codename, not as the name of a single game. **Confluent Dreams** is one game intended to exist within that platform. The broader family includes tools, games, world simulations, a shell/client experience, portable runtime and service infrastructure, agent-assisted workflows, and worlds that can be inhabited and extended. These are not meant to feel like a set of disconnected products.

The user repeatedly described the projects as interconnected in the same way that the fictional worlds and institutions are interconnected. The latest useful metaphor is **cells and the lines between them**:

- **Cells** are local, self-contained units with their own identity, state, history, and activity. Depending on context, a cell might be a world, room, location, package, citizen, simulation, client surface, or creative workspace.
- **Lines** connect cells and permit travel, communication, influence, exchange, or continuity across boundaries.
- **Nodes, gates, and crossings** are locations where lines meet, cross, or permit passage between otherwise separate cells or worlds.
- **The space between worlds** is not merely empty distance. It may have its own geography, rules, inhabitants, and history.

That last idea is what made the user's recollection of *Bleach* especially relevant. The remembered red ribbons appear to combine two different film moments: the red spiritual tracking thread in **Bleach: Fade to Black** (2008), and the Valley of Screams / Senna's red hair ribbon in **Bleach: Memories of Nobody** (2006). Those references share a theme: a connection remains visible or meaningful across separation, loss, and the boundaries between worlds.

A second important clarification came from Deadlock terminology. The game's **rideable transit routes** have been called Hyperlines in Neon Prime, Shadowlines in the Shadowline development period, and Transit Lines in Deadlock. **Ley Lines** are a separate, deeper occult concept in the setting. In an earlier Shadowline context, Astral Gates were called **Shadowline Nexus** locations, which helps explain why the ideas can feel connected without being identical.

For naming, the strongest currently promising direction is still a grounded, institutional name with ordinary public meaning and a deeper fictional reading. **The Meridian Survey** was one of the most promising proposals. **The Interline** is a useful candidate for the hidden connective structure, network, or internal term. Neither is a final decision. **Confluent Dreams** remains the game title, while **Brass Meridian** and **The Switchyard** are places within the fictional setting rather than umbrella brands.

The desired tone is not generic futuristic technology branding. It is historical, institutional, physical, atmospheric, and slightly uncanny: an old survey office, a railway authority, a commission, an observatory, a civil register, or a public institution whose name feels as though it has existed for generations. The public meaning should be plausible and mundane; the deeper meaning should emerge through the world and the systems behind it.

---

# 2. What the platform is — and what it is not

## 2.1 OpenLock is the platform codename

**Established by the user:** OpenLock was originally the codename for the platform. It was not intended to be the name of a single game.

The important relationship is:

- **OpenLock:** the original platform codename / contiguous family of technology and experiences.
- **Confluent Dreams:** a game intended to exist under that platform.
- **The project family:** tools, editors, client surfaces, operating-layer work, services, games, simulations, worlds, and community-created extensions.

The public name may or may not remain OpenLock. The codename should not be mistaken for a final brand decision.

## 2.2 The family is one continuous environment

The user does not regard games, tools, shells, operating systems, worlds, and creative software as inherently separate product categories. They can be separate technical projects and run natively on different platforms, but they are intended to participate in one continuous environment.

The experience should not force a person to leave a world, open an unrelated tool, move files through a disconnected workflow, and then return to the world. Creation, play, observation, editing, publishing, collaboration, and maintenance should be able to coexist as different modes of participating in the same family.

This does **not** mean every component must be one monolithic executable or one operating system. It means that separate technical components should remain connected through shared conventions, package formats, identity, records, services, and user-authorized interactions.

## 2.3 The platform is not simply an operating system

The user wants an eventual Linux-based operating system and a portable shell/client experience. The OS is an important project within the family, but it is not the whole platform.

The wider platform should be able to expose different client surfaces and operate across different devices and host environments. The Debian backend is an important authoritative service/store environment, but it is not the only client surface and should not be equated with the entire platform.

A useful working distinction is:

| Layer | Working meaning |
|---|---|
| Platform family | The connected set of services, packages, worlds, tools, clients, and projects |
| Operating layer / shell | A user-authorized environment for launching, presenting, managing, and connecting experiences |
| Backend | Shared records, package/store services, persistence, orchestration, and other authoritative services |
| Client surface | The environment a person actually uses; it may be native to Windows, Linux, or another device class |
| Game / world | An inhabited experience that can use the platform without defining the platform as a whole |
| Tool / editor | A way to create, inspect, modify, and publish parts of the family |

## 2.4 Openness and ownership

The desired ecosystem is open and community-owned in spirit. People should be able to create, modify, publish, play, inhabit, extend, preserve, fork, and self-host experiences.

Openness should be both a practical property and a communicated philosophy. It should not be reduced to a marketing word pasted into the brand. The underlying design should support local ownership, inspectable records, portable packages, user authorization, and community extensions.

The project is **not** meant to be branded as an AI company or an AI service. Agent assistance is part of the infrastructure and interaction philosophy, not the entire public identity.

---

# 3. Emotional and philosophical foundation

## 3.1 Returning to worlds that mattered

The emotional core described by the user is close to:

> Walking back through time to not just see and feel the things we used to love, but to be part of them again — almost like heaven, with death and hell as the outside world.

The nostalgia here is active rather than archival. It is not enough to preserve screenshots, assets, or a record that a game once existed. The goal is to return to creative worlds and inhabit them: to make things, play, encounter other people and agents, and see the worlds continue to live.

Important memories and aesthetic reference points include:

- LittleBigPlanet and its Create mode, especially the feeling of entering other people's crafted spaces.
- Minecraft worlds and modded environments that accumulate histories.
- Rain World and its sense of ecosystems, inhabitants, and processes continuing beyond the player's immediate attention.
- The 2024 version and atmosphere of Deadlock, including its earlier aesthetic and development lineage.
- Twilight Town and other Kingdom Hearts locations where everyday spaces, transit, strange architecture, and emotional memory coexist.
- Older creative communities and game environments that felt like places rather than disposable sessions.

These references are not all intended to appear literally in every project. They describe a shared emotional direction: a world should feel like it has a life before, during, and after the player enters it.

## 3.2 Participation, not just preservation

The user wants people to be able to return to an experience and become participants in its continued life. They should be able to make things, extend systems, inhabit places, and witness activity that is not solely caused by the player.

This is consistent with the user's simulation interests:

- Citizens should act independently of the player.
- The player should also act independently of the citizens.
- Society should be able to develop institutions, rules, work, and memory.
- Production and material use should have causal steps rather than appearing from nowhere.
- History should be preserved as evidence and records, not only as a narrative written after the fact.

## 3.3 Accessibility and agency

The platform's assisted interaction model is important because people should have more than one way to participate. Assistive agents and interfaces can handle complicated, repetitive, or physically demanding work, while retaining the user's authority over consequential actions.

This should be understood as a design value, not as a public branding gimmick. The public identity should not reduce the project to a medical or disability-related product. The wider principle is that the environment should permit participation through different modes of interaction.

## 3.4 Agents should help without displacing the human

The user has repeatedly emphasized a user-authorized architecture. Agent systems may delegate work, operate interfaces, manage workflows, train, test, and act through tools, but human authority remains part of the control model.

For naming and worldbuilding, this matters because the platform should not sound like a company that sells artificial intelligence. It should sound like a place, institution, environment, or body of work that people can enter and take part in.

---

# 4. Visual, material, and atmospheric direction

## 4.1 Broad aesthetic

The desired aesthetic combines:

- Industrial occult imagery.
- Dieselpunk and alternate 1950s–1960s military-industrial design.
- Dark, brass, violet, and twilight palettes.
- Painterly fantasy environments.
- Old railways, signage, public buildings, stations, and mechanical infrastructure.
- Colossal geometry and structures that seem older or larger than the civilization around them.
- Old machinery repurposed for supernatural or otherwise unexplained uses.
- A sense of melancholy, memory, and time that has accumulated in places.

The intention is not generic cyberpunk. Avoid defaulting to neon gradients, holographic surfaces, clean futuristic glass, or generic science-fiction interface vocabulary.

## 4.2 Material language

Useful material references include:

- Brass, darkened metal, aged iron, painted metal, and worn machinery.
- Violet or deep purple used as an atmospheric or symbolic element rather than a generic neon accent.
- Warm dusk light and twilight skies.
- Old paper, printed records, institutional signage, maps, and survey instruments.
- Concrete, stone, tiled public interiors, station platforms, industrial railings, and large-scale structural forms.

The feeling should be lived-in and historically layered. Things should look maintained, modified, repurposed, repaired, or gradually overtaken by something unfamiliar.

## 4.3 Existing family design cues

The family design references discussed include IBM and Bitters typography, dark interfaces, and an industrial/editorial visual language.

A shared Popit Forge prototype screenshot was described as having:

- A dark primary viewport.
- Acid-lime active controls.
- Blue panels and timeline elements.
- Serif display headings.
- Monospaced metadata.

These are prototype-level design references, not a finalized universal style guide. They do suggest that the family can combine editorial typography with highly practical control surfaces.

## 4.4 What was visible in the shared environment references

The user shared an unfinished Confluent Dreams map screenshot. The visible blockout was a grassy, hilly environment with blocky central structures. It was described as a rough, flatgrass-like starting point with hills. This image was not evidence of a finished town, station, arena, or detailed architecture; those elements came from the user's textual world description.

The distinction matters: do not infer finished environment details from a rough blockout image.

---

# 5. The one-wing motif and symbolic vocabulary

The user described a personal one-wing motif with several simultaneous meanings:

1. **Insignia:** a visual mark or emblem that can recur across the family.
2. **Philosophy:** freedom, movement, individuality, and the ability to overcome limitations.
3. **Mythology:** a symbol that can have a deeper role in the fictional world.

The user confirmed that all of those interpretations were relevant. It should not be collapsed into only one meaning, such as a logo flourish or a character reference.

A dual light/dark reading is also personally meaningful. The user described a relationship between a bright side and a darker counterpart, using a character contrast as an analogy. This is potentially useful for personal symbolism and internal mythology, but it should not automatically become the public brand's central theme.

**Naming guardrail:** do not use the user's personal name or handle as the project brand. The motif can inform the visual and philosophical identity without making the umbrella name a personal-name derivative.

---

# 6. The interconnected-cell model

The user's latest formulation — that the project family is interconnected in the same way the fictional worlds are interconnected, and that both have cells — is a particularly productive organizing idea.

The following model is a synthesis, not a final technical specification.

## 6.1 Cells

A cell is a locally coherent unit. It has boundaries, identity, state, and the capacity to participate in a larger system.

Possible correspondences include:

| Context | Possible cell |
|---|---|
| Game world | A world, region, biome, room, instance, or inhabited location |
| Creative tool | A project, document, editor workspace, or package |
| Simulation | A citizen, institution, settlement, job, court, or local society |
| Platform | A client, service, package, device, or locally operated environment |
| Narrative | A world, plane, city, organization, or pocket of history |
| Community | A self-governing group, shared space, or creator-maintained project |

Not every cell needs to be the same size. The term is useful because the local unit can remain meaningful while participating in a larger connected whole.

## 6.2 Lines

Lines connect cells. They may carry more than one kind of relationship:

- Physical movement or transit.
- Communication.
- Data and package transfer.
- Shared identity or provenance.
- Influence or exchange.
- Narrative continuity.
- Access between otherwise separate worlds.

The key distinction is that a line need not be a road or a user-facing transit feature. It can be a hidden relationship, an occult current, a system boundary crossing, or a logical connection.

## 6.3 Nodes, crossings, and gates

Where lines meet, a node or crossing can form. Some crossings may be ordinary junctions; others may be gateways into different world layers.

Possible terms:

- **Node:** a point where connections converge or route through.
- **Junction:** a place where routes meet and can be selected or transferred between.
- **Gate:** a threshold that permits passage between otherwise separated spaces or planes.
- **Nexus:** a powerful or unusually consequential node.
- **Confluence:** the condition or event in which separate flows meet.
- **Switchyard:** a physical or operational place where routes are redirected, sorted, or exchanged.

These are possible distinctions to preserve rather than synonyms to use interchangeably.

## 6.4 The between-space

The space between cells may itself be inhabited, structured, and consequential. It is not necessarily an empty void or a conventional loading transition.

It could contain:

- Routes that cannot be seen from either endpoint.
- Lost or displaced entities.
- Old infrastructure connecting worlds.
- Remnants of former passages.
- Rules that differ from the worlds being connected.
- Places that are only accessible by following a particular line or opening a particular gate.

This is the part of the idea most closely associated with the user's Bleach recollection and the atmosphere of a twilight transit space.

## 6.5 A possible conceptual stack

One useful model for the fictional and technical family is:

1. **Cell:** a locally coherent world, space, package, person, or service.
2. **Boundary:** what makes the cell distinct and governs how it can be entered or modified.
3. **Line:** the relationship or route connecting it to another cell.
4. **Node:** a point of convergence or routing.
5. **Gate:** a threshold between different layers or planes.
6. **Interspace:** the medium or territory between cells.
7. **Survey / registry:** the system or institution that observes, records, maps, or regulates the structure.
8. **Confluence:** a higher-order event or condition when multiple lines, cells, or histories meet.

This stack is an interpretive aid. It is not yet a canonical ontology or an approved platform schema.

---

# 7. The Bleach references: two films remembered as one image

The user's memory of Ichigo reaching for or following red ribbons appears to combine two separate moments from two *Bleach* films. Both are relevant to the thread's themes, but they are not the same scene.

## 7.1 The red spiritual tracking thread: *Bleach: Fade to Black* (2008)

The strongest match for the red ribbon-like visual is **Bleach: Fade to Black**.

In the film, Ichigo and Renji attempt to find the missing Rukia. Renji proposes using **Reiraku**, visible spiritual threads used to trace a person's spiritual presence. He explains that visualizing Reiraku in Soul Society is normally difficult because the environment is made of Reishi, but Ichigo may be able to follow Rukia because their spiritual compositions are similar.

When Ichigo and Renji use Reiraku, Ichigo releases a pulse of blue energy. A red ribbon-like thread appears above him and extends toward the location where Homura and Shizuku are carrying Rukia. The thread follows their movement.

This is almost certainly the particular red, thread-like image that the user was remembering.

**Why it resonates with the project idea:**

- A connection becomes visible even when its endpoint is distant or hidden.
- The thread is not merely a path on a map; it represents a spiritual relationship.
- The ability to trace the line depends on a correspondence between the two connected beings.
- A bond allows someone to find a person across a hostile or unfamiliar space.

Source: [Bleach Wiki — Bleach: Fade to Black](https://bleach.fandom.com/wiki/Bleach%3A_Fade_to_Black). The page describes Renji's Reiraku proposal and the red ribbon-like thread that follows Homura and Shizuku carrying Rukia. This is a fan-maintained reference, not an official production document.

## 7.2 The in-between world and Senna's red hair ribbon: *Bleach: Memories of Nobody* (2006)

The other important reference is **Bleach: Memories of Nobody**.

This film introduces the **Valley of Screams**, an in-between dimension associated with Blanks: souls that have become lost between the Human World and Soul Society. The Valley is not simply a road between two normal locations. It is a separate space with its own existence and consequences, and its collapse threatens the relationship between the two worlds.

The ending also gives the user another red-ribbon memory. Senna sacrifices herself to push the Human World and Soul Society apart again. After she fades away, Ichigo encounters the red hair ribbon associated with her. The closing image preserves a trace of the connection even as the person and the world's memory of her are slipping away.

The film therefore contributes two different images to the user's recollection:

1. A real in-between realm where lost souls and separated worlds become entangled.
2. A red ribbon that remains as a personal trace after Senna has disappeared.

**Why it resonates with the project idea:**

- The space between worlds has its own geography and inhabitants.
- A connection can persist after ordinary memory or physical presence fails.
- An object or line can become evidence that a relationship existed.
- Crossing, collapse, separation, and restoration are all part of the same cosmological structure.

Sources:

- [Bleach Wiki — Bleach: Memories of Nobody](https://bleach.fandom.com/wiki/Bleach%3A_Memories_of_Nobody)
- [Bleach Wiki — Memories of Nobody, image gallery](https://bleach.fandom.com/wiki/Bleach%3A_Memories_of_Nobody/Image_Gallery)
- [Wikipedia — Bleach: Memories of Nobody](https://en.wikipedia.org/wiki/Bleach%3A_Memories_of_Nobody)

The film's world mechanics and ending are summarized in those references. They are secondary sources; the movie itself remains the primary source.

## 7.3 The combined memory is thematically coherent

The user may have fused the red Reiraku thread from *Fade to Black* with the Valley of Screams and Senna's ribbon from *Memories of Nobody*.

That is a factual correction about the source scenes, not a correction to the idea. The combined image is useful precisely because it brings together three concepts:

- **A traceable line:** a bond that can be followed through space.
- **An interstitial world:** a place that exists between otherwise distinct worlds.
- **A surviving token:** something that remains after a person, place, or memory has been lost.

Together, these are strong visual and narrative material for the user's line-and-cell concept.

---

# 8. Deadlock: Hyperlines, Shadowlines, Transit Lines, and Ley Lines

The user connected Deadlock's Ley Lines with the older Shadowlines idea. Research supports a relationship between the terminology, but they should not be treated as precisely the same feature.

## 8.1 The rideable transit routes changed names

The community-maintained Deadlock reference records the rideable routes as having these historical names:

| Development context | Term for the rideable routes |
|---|---|
| Neon Prime | Hyperlines |
| Shadowline | Shadowlines |
| Current Deadlock terminology | Transit Lines |

Some older UI and voice-line remnants may retain earlier words. The current term is Transit Lines.

Source: [The Deadlock Wiki — Zip-lines](https://deadlock.wiki/Zip-lines). The page records this development naming history. It is a community-maintained source, not a direct Valve statement.

## 8.2 Ley Lines are an occult layer

**Ley Lines** appear as an occult or magical concept in Deadlock's setting. In the in-progress story transcription **The Binding of Oathkeeper**, Dynamo refers to a lecture on ley lines and tells students to review their notes on Astral Gates.

That connects Ley Lines conceptually to the world's occult geography and the Astral Gate system. However, the story transcription is marked as in-progress and should not be treated as proof that every detail is finalized or that Valve has established a complete canonical system around it.

Source: [The Deadlock Wiki — The Binding of Oathkeeper / Transcription](https://deadlock.wiki/The_Binding_of_Oathkeeper/Transcription).

## 8.3 Shadowline's "Shadowline Nexus" terminology

A community archival page for Shadowline records that:

- Rideable lines were called Shadowlines.
- Astral Gates were referred to as **Shadowline Nexus**.
- A voice line described the four lanes as having a Shadowline that players could ride.
- Viscous's background described the Bermuda Triangle Astral Gate as a Shadowline Nexus.

The same page notes that Shadowlines were **presumably** based on Ley Lines. That last relationship is an inference made by the community source, not an independently proven official explanation.

Source: [The Deadlock Wiki — Shadowline](https://deadlock.wiki/Shadowline).

## 8.4 The distinction worth preserving

The cleanest working distinction is:

- **Transit Line / Hyperline / Shadowline:** the player-facing, rideable transportation route in the game map.
- **Ley Line:** the occult or magical network that may underlie, intersect with, or explain deeper world connections.
- **Astral Gate:** a passage between worlds or planes.
- **Shadowline Nexus:** an earlier label associated with an Astral Gate or major occult junction.

This creates a useful layered vocabulary for the user's world without claiming that Deadlock's terms map one-to-one onto the user's project architecture.

## 8.5 Why this is relevant to the user's naming problem

The attraction is not merely to the word Shadowline or Ley Line. It is to the idea that there are visible routes and deeper, less visible structures beneath them.

A transit route can be what inhabitants use every day. A Ley Line can be the hidden geography that shapes where routes, gates, cities, and conflicts emerge. A nexus can be a place where those forces converge.

That distinction is especially useful for a world in which ordinary infrastructure — railway stations, public institutions, maps, survey markers, industrial buildings — coexists with an occult connective substrate.

---

# 9. The naming direction

The naming conversation has not reached a final brand decision. Several names have been considered, but the criteria have become clearer.

## 9.1 What the umbrella name should feel like

The user is drawn to names that feel:

- Like real institutions, places, or historical organizations.
- Old enough to have accumulated records and traditions.
- Publicly understandable in an ordinary, non-fantastical way.
- Capable of concealing a deeper or stranger meaning.
- Connected to geography, surveying, travel, boundaries, confluence, and the relationship between separate places.
- Durable enough to encompass games, tools, worlds, software, and community projects.

The user does **not** want names that sound obviously AI-generated, generic technology-company names, or generic sci-fi/fantasy names.

## 9.2 Explicitly disliked or disfavored naming patterns

Avoid turning the umbrella brand into a phrase built around:

- AI
- Engine
- Forge
- Studio
- Metaverse
- Digital
- Network

These words may still be usable as ordinary technical descriptions in documentation where appropriate, but the user does not want them as the identity-defining brand vocabulary.

Other avoidances:

- Overly futuristic combinations that feel generated rather than inherited.
- Fantasy names that announce their genre too loudly.
- Corporate language that makes the ecosystem feel like a software vendor.
- A name that uses the user's personal name or handle.
- Names that accidentally turn a location in the fictional world into the umbrella brand.

## 9.3 The Confluent / Meridian semantic direction

The user said they wanted something that sounds like the conceptual territory of **“the confluent meridian”**, but not that exact phrase.

These two ideas are doing different jobs:

- **Confluence:** separate flows, histories, routes, worlds, or systems meeting.
- **Meridian:** a reference line used to locate, measure, orient, and relate places across geography.

Together, they suggest a system that measures or maps the relationship between separated places and the routes that connect them.

This is not just a poetic combination. It gives the umbrella institution a plausible public function: surveying, mapping, registering, observing, or maintaining a shared reference for a complicated territory.

## 9.4 The strongest current proposal: The Meridian Survey

**The Meridian Survey** was one of the names the user liked more than most earlier suggestions.

Why it works:

- It sounds like a real public institution or long-lived organization.
- It has a practical public meaning: a survey that establishes, studies, records, or maps a territory.
- It does not sound like an AI company or generic software platform.
- It can contain a deeper purpose: mapping the lines, cells, gates, and interstitial regions that ordinary geography does not explain.
- It can plausibly have public offices, field stations, records, maps, standards, archives, and old institutional history.
- It leaves room for ambiguity about what the institution truly surveys.

The name remains a proposal, not a user-approved final decision.

## 9.5 The Interline as a deeper term

**The Interline** is a useful companion term.

Rather than necessarily naming the whole platform or institution, it could name:

- The hidden connective structure between cells or worlds.
- The system of routes that passes through or beneath ordinary geography.
- An internal term used by the institution.
- A phenomenon that the public institution studies without fully understanding.
- A name for the space or topology that links separate places.

This creates a potential naming architecture:

- **The Meridian Survey:** the public institution or umbrella identity.
- **The Interline:** the underlying network or connective substrate.
- **The Switchyard:** a particular location where routes converge or are transferred.
- **Brass Meridian:** a particular region, landscape, or enormous city-like territory.
- **Confluent Dreams:** a game set within or connected to this broader family.

This arrangement is promising because each name has a different role. It should not be treated as settled until the user chooses it.

## 9.6 Other names considered

| Name | How it entered the discussion | Current status / caution |
|---|---|---|
| **NACRE** | Shell, layer, nacreous material, mother-of-pearl, iridescence; the name has a physical and layered feel | Visually and semantically interesting, but the user remained unsure. There are existing software/product uses of Nacre, so collision research would be needed before adopting it. |
| **Crosslane** | Evoked crossing routes and the user's purple horizontal lane through a jungle environment | The user liked the concept, but it was not chosen as the platform name. It may work better as a route, map feature, or in-world term. |
| **ATOLL** | Suggested as a bounded but interconnected geography | Not strongly accepted; no decision. |
| **PENUMBRA** | Half-light, shadow, threshold, and the overlap of light and dark | The user was attracted to it as an OS/platform possibility. Later collision concerns were raised, including existing uses in software and Adobe-related naming. Not rejected outright, but not selected. |
| **The Meridian Survey** | A grounded institutional name around mapping, coordinates, and the meeting of separate territories | One of the strongest candidates; still open. |
| **The Coalescent Observatory** | A name combining convergence and observation | The user liked it more than many earlier names but said it sounded like an AI-generated name. Not a preferred direction at present. |
| **The Meridian Commission** | A more governmental/institutional variant | Considered, not selected. |
| **The Meridian Compact** | A treaty, charter, or shared framework between territories | Considered, not selected. |
| **The Interline Survey / Commission** | Variations combining the hidden line structure with public institution language | Considered, not selected. |
| **The Confluence Commission** | Institutional take on the convergence concept | Considered, not selected. |
| **The Confluent Survey** | A direct combination of the key semantic direction | Considered, not selected. |
| **The Continental Register** | A registry or record-keeping body with a broad geographic remit | Considered, not selected. |
| **The Geodetic Commission** | A credible surveying/geography institution name | Considered, perhaps too technical or conventional; no decision. |
| **The Meridian Society** | A historical society or institution | Considered, not selected. |
| **The Meridian Institute** | A research institution variant | Considered, not selected. |
| **The Common Datum** | A shared point of reference or coordinate standard | A useful underlying concept; not selected as the name. |

## 9.7 Names that should remain in their own category

The following are **not** umbrella-platform candidates in the current understanding:

- **Confluent Dreams:** the game title.
- **Brass Meridian:** a physical region / landscape / city-like territory in the fictional setting.
- **The Switchyard:** a location or transit hub within the world.
- **Crosslane:** a possible map feature or route term.

Keeping these roles distinct will reduce future naming confusion.

## 9.8 Naming system rather than a single isolated word

The conversation increasingly suggests that the right solution may be a structured vocabulary rather than one name that has to do everything.

For example — as a proposal only:

| Role | Candidate term | Possible function |
|---|---|---|
| Public institution / umbrella | The Meridian Survey | The visible organization with a mundane public remit |
| Hidden connective structure | The Interline | The system of routes and relationships beneath ordinary geography |
| Convergence event / condition | Confluence | The meeting of worlds, lines, histories, or systems |
| Physical transit location | The Switchyard | A place where routes meet, transfer, or depart |
| Major region | Brass Meridian | The inhabited landscape or city-scale territory |
| Game | Confluent Dreams | One experience inside the wider family |
| Local unit | Cell | A self-contained world, service, package, room, or inhabited unit |
| Crossing / threshold | Gate | A passage between cells or layers |
| Major convergence point | Nexus / Junction | A place where multiple lines meet |

The structure gives each name a job and avoids requiring the public platform name to carry every symbolic association.

---

# 10. Fictional organization and the world behind it

## 10.1 An institution whose purpose is unclear, even to its creator

The user described an organization in the fictional world whose actual purpose is not yet known, even to the user as its creator.

It seems:

- Civilizational in scale.
- Older than the world or older than the known civilization's understanding of it.
- Similar in surface form to an old international commission, society, public authority, or survey institution.
- Much larger and stranger internally than its public face suggests.
- Connected to huge, dark, rectangular cuboid structures.
- Associated with labyrinthine interior environments that extend deep into the Earth's crust or below conventional geography.
- Not necessarily malevolent, despite the oppressive or uncanny scale of its structures.

The organization should not be reduced to a conventional secret society, evil corporation, cult, or generic ancient order.

## 10.2 Public meaning and hidden meaning

One attractive direction is a public-facing organization whose stated purpose sounds mundane and credible — perhaps surveying, geodesy, geological measurement, civil infrastructure, mapping, archival records, or the maintenance of a shared datum.

Its deeper activity may involve mapping or maintaining the topology of cells, lines, gates, and spaces between worlds.

This is a proposed interpretation, not an established answer to the organization's purpose.

## 10.3 Architectural references

The atmosphere and structure of the organization were compared to a blend of:

- Kane Parsons' Backrooms imagery: huge, uncanny, institutional interiors that seem to continue beyond normal architectural expectations.
- Rain World's Iterators: immense structures and systems that imply a civilization-scale purpose and a reality larger than the characters understand.
- Kingdom Hearts: Missing-Link / Scala ad Caelum-like ideas of monumental, historically layered places, with caution that some user references were to leaks or unreleased material and should not be treated as confirmed canonical detail.

These are points of atmosphere and structural inspiration, not elements to copy literally.

## 10.4 The institution's uncertainty is valuable

The fact that its purpose remains unknown can be a deliberate creative strength. The institution may be understood through partial evidence: maps, old records, facilities, signage, field notes, route markers, and the effects of its activity.

The public identity may be coherent while the true purpose remains unresolved. People inside the world may know their duties without understanding the whole system.

---

# 11. Confluent Dreams: game and setting notes

## 11.1 Position in the family

**Confluent Dreams** is a game intended to exist under the larger platform family. It is not the name of OpenLock as a whole.

The game is intended to be independent of the platform's deeper mythology in the sense that it should still work as its own game and world. It can nevertheless share an aesthetic, technical substrate, and vocabulary with other family projects.

The user has also discussed a "hush" style or mode as a way for Confluent Dreams to stand on its own without requiring the audience to understand all platform mythology. The exact meaning and implementation of that style was not fully specified in the available discussion.

## 11.2 Major inspirations

The user's reference set includes:

- **Kingdom Hearts Twilight Town:** map geometry, story beats, everyday-but-strange town atmosphere, materials, and painterly visual style.
- **Halo:** environmental and gameplay references.
- **Final Fantasy VII Midgar:** large city-scale structures and industrial urban geography.
- **Final Fantasy XIII:** huge city environments, walls, machinery, and monumental scale; the user referred to the large city/gear-wall quality of the setting.
- **LittleBigPlanet:** creative play and player-made spaces.
- **Rain World:** ecology, living systems, and environmental continuity.
- **Minecraft:** world inhabitation, construction, and long-lived shared spaces.
- **Deadlock:** especially its 2024 look and feel, early development atmosphere, and arena-shooter framework.

These sources contribute different things. They should not all be flattened into a generic crossover aesthetic.

## 11.3 Brass Meridian

**Brass Meridian** is a physical place in the fictional world: a region, landscape, or vast city-like environment. It should be understood more like a major geography or monumental inhabited setting than like a company, platform, or institutional brand.

The name carries associations of geography, metal, scale, and orientation. It is not currently the recommended umbrella name.

## 11.4 The Switchyard

**The Switchyard** is a location within the world and a multi-world transit/crossroads concept.

Its functional and atmospheric associations include:

- Train and rail transit.
- Multiple routes or worlds meeting.
- A gathering place.
- A point of transition between experiences.
- A place that can serve multiple roles, somewhat like a central hub or recurring meeting location.

The user compared its role loosely to the Mysterious Tower / Sunset Terrace / world-map hub functions in Kingdom Hearts. This should be treated as a role comparison, not an exact setting equivalence.

The Switchyard is a strong in-world term because it is ordinary, mechanical, and physical while still carrying a larger symbolic function.

## 11.5 The train station and one-way arrival

The map is conceived as an inhabited environment rather than a standalone arena floating in isolation.

Players arrive through a train station as a one-way trip. The station is an entry point into the broader town and arena environment.

This gives the world a sense of commitment and passage: arriving is a transition into a place with its own geography and rules, not merely the start of a match instance.

## 11.6 Icodomes and player rooms

Player rooms are located around the outskirts in **Icodomes**. The town, arena, station, and living spaces form a contiguous environment.

The exact physical design and system behavior of Icodomes were not fully settled in the available context. The name itself should be retained as user-provided terminology.

## 11.7 Arena and the forces outside it

The arena is a bloodsport watched by powerful interests that control or influence the outside world. The Fairfax family is among those powers.

Other people or beings from across different games or worlds can be brought into the arena to fight. The user compared the premise loosely to the Deadlock Maelstrom / bear-pit feeling, but the fights are not simply about money or ordinary competition.

The arena has consequences beyond the people fighting inside it. The outside world is affected by the powers that operate the spectacle.

## 11.8 The Fairfax family and the Moon event

One described Fairfax-family action involves blowing up the Moon after discovering that a competitor is hollowing it out. The user compared the event to a Warframe-style moon reveal or hidden structural discovery.

This is a worldbuilding note from the user's description. It should not be converted into a final plot chronology without further confirmation.

## 11.9 The announcer

The user had an announcer concept that later became very close in feeling to Deadlock's Deadman Danny. This was noted as a similarity in concept, not an assertion that the user's idea was copied from or identical to that character.

## 11.10 Alternate-universe Deadlock combat philosophy

The user's alternate-universe interpretation departs from conventional MOBA assumptions.

Key stated ideas include:

- The game is primarily a fast, close-range, first-person arena shooter.
- It should not become a conventional MOBA with long crowd-control chains or constant slows.
- Players train strength for melee, improve weapons, and develop movement.
- Movement is an active expression of player skill, potentially including wall-running and superglide-like movement.
- Combos and aerial combos are part of the combat language.
- Hero archetypes should grow toward the individual player's playstyle.
- Spirit is not simply currency: souls are literal living entities in the world.
- Heroes have a base kit, while the player's development and choices shape their eventual expression.

The user's concern was that the current Deadlock meta had become abysmally unplayable for the desired style. The design response is not just to copy Deadlock's systems, but to recover a particular fast, physical, readable, close-range arena-shooter feeling.

## 11.11 May 2026 design notes supplied by the user

The user pasted material from May 8, 2026 X posts describing an alternate 1950s/1960s military-occult version of the game. The notes included:

- Firearms and supernatural power in an alternate military-industrial world.
- A local server instance opening with the game, with Steam networking.
- User-hosted and joinable matches.
- Hero base kits that develop toward each player's chosen playstyle.
- Primary / secondary weapon swapping.
- Magic or poke capabilities connected to strength.
- Active and passive movement progression.
- A high-impact ultimate weapon with a roughly three-minute cooldown.
- Functional itemization tiers and power upgrades.
- Strong and fast default heroes.
- A fast arena-shooter emphasis rather than a conventional MOBA.
- Short-range fights with protected sightlines.

These are user-supplied design statements, not an independently verified product specification. They are useful as an archived concept snapshot.

## 11.11.1 Related May 7 post lookup

The user also remembered a May 7, 2026 X post or post sequence that may have contained the Moon-destruction scene and related story beats, but the specific posts could not be located during the discussion. The May 8, 2026 notes were available because the user pasted their text. The missing May 7 material should therefore remain an unresolved source lead; do not invent or reconstruct its wording.

## 11.12 Earlier OpenLock map concept

The user also described earlier OpenLock map work based on a modified version of a Deadlock map. One version had a horizontal lane cutting through a jungle, with the purple lane appearing tumbled or sloped down through the environment. One player on each team spawned at opposite ends. The broader design idea was that maps were not arbitrary competitive arenas: they represented locations around the world and could belong to a larger connected geography.

This earlier map concept should be kept distinct from the later Confluent Dreams town / train station / arena blockout. They are related parts of the user's design history, not necessarily the same map.

## 11.13 The map blockout

The unfinished map image was described as a grassy, hilly blockout with a rough flatgrass-like starting area and blocky structures. It was not a finished depiction of the larger town, station, arena, or Brass Meridian geography.

When future design notes reference this image, preserve the distinction between the visible prototype and the larger intended setting.

---

# 12. The platform's technical project family

The naming discussion is connected to a real technical family. The following project notes summarize the repository and architecture context discussed in the thread and adjacent work. These are not claims that every feature is complete or production-ready.

## 12.1 `dl-openshell`

Repository: [alacripose/dl-openshell](https://github.com/alacripose/dl-openshell)

The public README describes a Panorama UI shell / window-manager-style layer for Deadlock. The project includes concepts such as:

- Launcher bar and taskbar.
- Toasts and desktop/workspace presentation.
- Tools view and panels.
- Popit-style tool layers beside windows.
- Palettes and chrome forms.
- Live package and observer payloads.
- Packages sourced from other Git repositories.
- In-game console and user/observer/developer grades.
- Integrated UI audio.

The project references package and delivery conventions including `openlock.addons/2`, `dl_openshell_deliver`, `openlock_observer`, and `openlock_toast`.

The important conceptual point is that OpenLock is not only an installer or launcher. Its roots include a live client-facing shell experience with tools and windows inside a host game environment.

## 12.2 `secure-shell`

Repository: [alacripose/secure-shell](https://github.com/alacripose/secure-shell)  
**Access note:** discussed as a private repository.

The architecture discussed includes:

- Debian-hosted backend services.
- A client fork of the OpenLock window-manager / taskbar experience.
- Package streaming.
- Project activity ledger.
- Signed checkpoints.
- AES-256-GCM prompt vault.
- A portable, user-authorized operating layer.
- Device discovery, installation, debugging, and restoration workflows.
- A custom client/server relationship in which the client owns the interactive presentation surface and the backend owns authoritative records and events.

The backend should not be understood as the only client or as the entirety of the platform. The architecture is meant to support different native clients, including Windows and Debian/Linux environments.

A central requirement is that users authorize consequential operations. The platform may discover devices and offer installation, debugging, and restore operations, but authority cannot be assumed merely because a device is visible.

## 12.3 `ala-cities`

Repository: [alacripose/ala-cities](https://github.com/alacripose/ala-cities)

This project is a deterministic Rust city-building / simulation project using wgpu. Its design philosophy is strongly evidence-first and includes records of builds, refusals, and retirements.

The user's stated simulation principles include:

- Citizens act independently of the player.
- The player is also an independent actor, not the sole cause of the city's activity.
- Citizens can perform multi-step work.
- Economy, materials, tools, and crafting should have conserved and causal relationships.
- Materials should not simply appear from nothing.
- Citizens should be able to create institutions and governance structures.
- The city should support a living society rather than a static decorative population.

The project was discussed with reference to design documents such as `DESIGN.md`, `UNIFIED_DESIGN.md`, and `docs/GRILLING-C9.md`. User answers in the design discussion addressed economy, citizens, growth, and production.

The connection to the larger platform is conceptual and architectural: the world is composed of independent agents and systems that form a society, not merely a visual scene controlled by the player.

## 12.4 `ala_civ_bots_prototype` / Ensouled Civilization

Repository: [alacripose/ala_civ_bots_prototype](https://github.com/alacripose/ala_civ_bots_prototype)

The project is a Minecraft 1.20.1 Fabric prototype for embodied, persistent citizens using a non-LLM System-1 approach.

The discussion described features already built at the end of October 2026, including:

- Persistent fake-player citizens using a silent connection.
- Perception within a limited radius and entity stimuli.
- Commands for movement, looking, jumping, equipping, using, mining, collecting, eating, moving away, and waiting.
- Tree-harvesting verification.
- Gzipped NBT persistence.
- Handoff self-tests involving two citizens.

Known gaps at that point included GUI and chest interaction, chat, human interaction, message persistence, combat, cognition while unloaded, and vanilla shadow mode.

The user explicitly emphasized that bots must never end up stateless. When testing is complete, they must be handled gracefully so they can exercise their freedom rather than being discarded or reset as disposable test fixtures.

This project helps ground the user's interest in cells: citizens are persistent local agents inside a larger world, with identity, memory, embodiment, and continuity.

## 12.5 `hero-retarget-workbench`

Repository: [alacripose/hero-retarget-workbench](https://github.com/alacripose/hero-retarget-workbench)

This Blender 5.4 add-on is the concrete beginning of the user's Deadlock model/retargeting workflow. The discussed features include:

- Hero picker.
- Custom model import.
- Model parts.
- Cloth.
- Skeleton and animation work.
- Compare tools.
- Weight workflows.
- Handoff and compile operations.
- Integration with real Deadlock / Source 2 Viewer / CSDK13 assets and tools.

It was described as a work in progress. Status and gate failures were recorded around 16 November 2026. The document should not claim that all functions are complete.

The project contributes the practical toolmaking side of the family: editing, asset authoring, retargeting, comparison, and compilation against a real host ecosystem.

## 12.6 Popit and Popit Forge

`dl-openshell` includes Popit-related structures modeled around LittleBigPlanet shape schemas and tool behavior. The discussed schema references include LBP1, LBP2, LBP3, PSP, Vita, and Karting concepts, plus CREATE / PLAY modes, contextual tool tiles, direct manipulation, and routing back into the shell.

The user also described a separate, unfinished Blender fork/prototype called **Popit Forge**. A screenshot label appeared as “POPIT FORCE,” but the user called the project Popit Forge. Treat the user's project name as Popit Forge unless the user later corrects it.

This project is especially relevant to the nostalgic/creative core: it connects a remembered creative interface to a new tool environment that is part of the larger family.

## 12.7 Shared system architecture and package philosophy

Across the projects, recurring requirements include:

- A single coherent package/streaming surface rather than separate incompatible runtime paths.
- Fast, stateful, streamable packages that can travel over a network.
- Operation on small devices as well as larger systems.
- The ability to scale to large numbers of workers or agents.
- Integrity and provenance, including signed records and Blake3-based signing in the SWF-related work.
- Git early and often, with tickets, pull requests, and comments as part of the development record.
- Clear separation between evidence, authority, and certification.
- Human-readable, local, encrypted sign-off before consequential actions.
- No assumption that an agent may perform arbitrary source inspection or bypass the system's security boundaries.

These are architecture-level family traits, not necessarily public marketing language.

---

# 13. Shared governance and evidence philosophy

The user has a broader institutional / agent doctrine that informs the project family.

## 13.1 Evidence as the source of truth

The architecture distinguishes evidence from authority. A document, test, record, or artifact can establish what happened, but it does not automatically become permission to act.

The user has emphasized that **paper is evidence, not authority**.

## 13.2 Separate planes

The user has described a framework involving:

- Governor Base.
- Civilians.
- Contracts.
- Resumes.
- Retirement.
- Tickets.
- Organizations.

The planes should not be merged merely for convenience. Their boundaries are meaningful.

## 13.3 Verification and development

The framework includes evidence grades and certification levels, with Bronze, Silver, Gold, Diamond, and Platinum-like progression referenced in prior doctrine. Graduation is a terminal transition, not merely a warning or cosmetic label.

A scientific-method candidate loop and axis-based refusal rules have also been discussed. These design principles support auditable behavior and ensure that a refusal can be a valid system outcome rather than a failure to be hidden.

## 13.4 Civilian life as a verification dimension

One of the six Axis stars is a civilian verification step in which agents live through cadence ticks, jobs, work, courts, and learning trees.

The user wants citizens to develop and exercise lives rather than remain stateless scripts used only to pass tests. Their social institutions should arise through actual participation in the simulated world.

This is one of the strongest direct connections between the user's civic simulation projects and the wider idea of a world made of cells.

---

# 14. The Switchyard, transit, and the between-world aesthetic

The Switchyard is currently best understood as a physical in-world place that expresses the connective structure.

It may combine several roles:

- Train station or railway interchange.
- World-to-world transit hub.
- Meeting place.
- A practical public facility with hidden or poorly understood functions.
- A place where one can see routes departing toward places not visible from the platform.

The user's reference to Twilight Town provides an important atmospheric clue. The desired experience is not simply a portal room. It is an inhabited place with ordinary details — platforms, signage, public architecture, routines, and a sense of home — that happens to be connected to something much larger and stranger.

The Bleach Valley of Screams adds a different dimension: the connective in-between may be a territory in its own right. The Deadlock Ley Line and Astral Gate vocabulary provides a possible occult geography. The user's own cell/line model ties those ideas together.

A possible hierarchy, still open to revision:

- A **station** is an ordinary access point.
- A **Switchyard** is a major route-sorting and transfer facility.
- A **Transit Line** is an established route people can travel.
- An **Interline** is the deeper connective structure that may not be fully visible or understood.
- A **Ley Line** is a supernatural or occult current in the fictional world's cosmology.
- A **Gate** is a threshold into another layer or world.
- A **Nexus** is a major convergence point.

Do not collapse these into a single term unless the user explicitly decides to simplify the vocabulary.

---

# 15. The historical development references around Deadlock

The discussion also touched the development lineage around Neon Prime, Shadowline, Deadlock, and Primelock.

## 15.1 Neon Prime and Shadowline

Community-maintained development-history references describe Neon Prime as an earlier Valve project and Shadowline as an early development version or transitional stage on the way to Deadlock. The exact distinction between Shadowline and the current Deadlock project has been described as debated in the community.

A community timeline lists Neon Prime development in 2020–2022, a late-2022 transition toward Shadowline / Deadlock, and later Deadlock development. These are community reconstructions, not necessarily an official Valve-published chronology.

Source: [The Deadlock Wiki — Development](https://deadlock.wiki/Development).

## 15.2 Primelock is separate

The user explicitly clarified that **Primelock** is its own project and is not the user's work. It recreates the Neon Prime aesthetic as a community project.

Do not confuse:

- The user's OpenLock platform codename.
- Valve's Neon Prime / Shadowline / Deadlock development lineage.
- The independent Primelock community recreation project.

The similarity of the words OpenLock and Primelock is not evidence of a project relationship.

## 15.3 Terminology caution

When discussing the historical development of Deadlock, distinguish:

- Publicly observable game content.
- Archived voice lines or removed content.
- Community reconstructions of development history.
- Unreleased or leaked materials.
- The user's own alternate-universe design.

Do not present every community timeline, leak, or inference as official Valve canon.

---

# 16. Consolidated naming and terminology glossary

| Term | Current working meaning | Status |
|---|---|---|
| **OpenLock** | Original codename for the connected platform family | Codename; public brand undecided |
| **Confluent Dreams** | One game intended to exist under the platform | User-provided game title |
| **The Meridian Survey** | Potential grounded institutional / umbrella name | Promising proposal; not final |
| **The Interline** | Potential name for the hidden connective structure or internal network | Useful proposal; not final |
| **Confluence** | Meeting of distinct flows, lines, systems, histories, or worlds | Core concept |
| **Brass Meridian** | Physical region / large landscape or city-like place | In-world geography, not platform brand |
| **The Switchyard** | Transit hub / crossroads / gathering place in the world | In-world location |
| **Icodomes** | Player-room or living-space concept around the outskirts | User-provided setting term; mechanics not fully defined |
| **Cells** | Self-contained local units connected into a larger whole | Emerging structural metaphor |
| **Lines** | Connections between cells; may carry travel, data, influence, or narrative continuity | Emerging structural metaphor |
| **Nodes / Junctions** | Points where lines converge or are routed | Candidate vocabulary |
| **Gates** | Thresholds between cells or planes | Candidate vocabulary, with Deadlock reference |
| **Nexus** | Major or consequential convergence point | Candidate vocabulary, with Deadlock reference |
| **Ley Lines** | Occult or magical connective geography in Deadlock-like lore | External reference; not identical to a transit route |
| **Shadowlines** | Historical name for rideable routes in Shadowline | External development terminology |
| **Transit Lines** | Current Deadlock term for rideable routes | External game terminology |
| **Hyperlines** | Earlier Neon Prime term for rideable routes | External development terminology |
| **Reiraku** | Spiritual threads used to trace a person in Bleach | External inspiration/reference |
| **Valley of Screams** | In-between dimension in Bleach: Memories of Nobody | External inspiration/reference |
| **Survey** | Publicly plausible activity of mapping, measuring, recording, or observing a territory | Strong naming concept |
| **Datum** | Shared point/reference for measurement or location | Useful technical and institutional concept |
| **One wing** | Insignia, philosophy, and personal mythology motif | Important symbolic reference; not necessarily the public brand |
| **Popit Forge** | User's unfinished creative-tool / Blender fork | User-provided project name |
| **Ensouled Civilization** | Persistent embodied citizen prototype in Minecraft | User project |

---

# 17. Working principles for future naming and worldbuilding

The following are practical guardrails distilled from the discussion.

## 17.1 Keep the public name ordinary enough to be believable

A name like The Meridian Survey is appealing because it could plausibly appear on a building, map, government document, train timetable, maintenance uniform, or archival record.

The audience should not immediately be told that the institution is a supernatural multiverse organization. The name should have a mundane surface meaning that can survive ordinary use.

## 17.2 Give the hidden system its own vocabulary

The public institution need not be named after the secret connective network. It can have an external name and an internal term for the phenomenon it studies.

This is why The Meridian Survey + The Interline is promising as a structure, even though neither is final.

## 17.3 Preserve place names as place names

Brass Meridian and The Switchyard already have specific spatial roles. They should not be repurposed as umbrella names just because they sound evocative.

## 17.4 Avoid a one-word name that must explain everything

The platform, fictional institution, world geography, transit network, and game can each have their own name. Their relationship should be discoverable through the system rather than packed into one overloaded brand word.

## 17.5 Let the technical and fictional structures rhyme without being identical

Cells, packages, users, services, cities, worlds, and story locations can share design principles without being forced into literal one-to-one analogies.

For example, a package may be a cell in the platform's organization, while an inhabited city district may be a cell in the fictional world. The analogy is useful because both are locally coherent and connected, not because their implementation is the same.

## 17.6 Do not make the institution simply evil

Its scale, age, secrecy, and architecture can be unsettling, but its purpose should remain more complicated than a generic sinister organization. It may preserve, map, regulate, protect, exploit, misunderstand, or simply outlast the world around it. The answer is still open.

## 17.7 Make the connective structure meaningful to inhabitants

Transit and world connections should not exist only as lore exposition. They should affect where people live, work, travel, meet, trade, create, and remember.

That is consistent with the user's goal that the worlds be inhabited rather than static backdrops.

---

# 18. Decision log: settled, promising, and unresolved

## 18.1 Settled / user-stated

- OpenLock began as a platform codename, not a game title.
- Confluent Dreams is a game within the larger family.
- The user's projects are intended to be interconnected rather than isolated products.
- The ecosystem should be open, extendable, community-owned in spirit, and capable of local/self-hosted participation.
- It is not intended to be branded as an AI company or service.
- The user wants a Linux-based OS project, but the OS is only one part of the wider platform.
- Brass Meridian is an in-world physical region / landscape / major city-like place.
- The Switchyard is an in-world transit hub / crossroads.
- Confluent Dreams has a train-station arrival and a larger contiguous environment including town, arena, and living areas.
- Player rooms are associated with Icodomes around the outskirts.
- The arena is a bloodsport watched by powerful outside interests, including the Fairfax family.
- The user's project family includes shell work, creative tools, game projects, simulations, and agent-related systems.
- The one-wing motif has insignia, philosophical, and mythological meanings.
- The user prefers institutional/place-like names over generic tech or AI-style names.
- The user liked the conceptual territory of something like “the confluent meridian,” without wanting that exact phrase.
- The remembered Bleach image combines material from two different films.
- The rideable line terminology in Deadlock has a different history from the separate Ley Line concept.
- Primelock is a separate community project, not the user's project.

## 18.2 Strong proposals / promising interpretations

- The Meridian Survey as a public-facing institution or potential umbrella name.
- The Interline as the hidden connective substrate or internal name for the network linking cells.
- A layered naming system separating institution, connective structure, places, routes, gates, and worlds.
- The cell/line/node/gate/interspace model as a shared conceptual structure across the platform and fictional worlds.
- The institution's public purpose being surveying, mapping, geodesy, records, or maintaining a shared reference.
- The Switchyard acting as a physical expression of the connectivity model.

## 18.3 Unresolved

- Whether OpenLock remains the public platform name or is replaced.
- Whether The Meridian Survey is adopted, modified, or discarded.
- Whether The Interline is an in-world network, an internal organization term, a platform concept, or something else.
- The exact relationship between Ley Lines, transit routes, gates, and the Interline in the user's own mythology.
- The true purpose and origin of the enormous institutional organization.
- Whether the institution is responsible for maintaining the connective structure, merely documenting it, exploiting it, or misunderstanding it.
- The precise meaning and mechanics of Icodomes.
- The exact meaning and scope of the “hush” style for Confluent Dreams.
- The detailed geography and chronology of Brass Meridian, The Switchyard, the station, town, arena, and Icodomes.
- The final combat and progression specification for the alternate-universe Deadlock-style game.
- The exact relationship between platform cells and fictional-world cells at the technical level.
- The final public style guide and brand identity.

---

# 19. Questions worth preserving for future work

These are not questions the user needs to answer immediately. They are the natural open threads left by the discussion.

## 19.1 Institution and hidden system

1. Is The Meridian Survey a real public institution in the fictional world, the name used by the platform family, or both through a deliberate cross-layer relationship?
2. Does the Survey map the Interline, maintain it, regulate its crossings, or merely record phenomena it cannot control?
3. Is the organization older than the world's current civilization, older than the planet's familiar geography, or simply older than the records available to its inhabitants?
4. Are the dark cuboid structures facilities built by the institution, artifacts it discovered, or components of the world itself?
5. Does the institution have a public, mundane service that genuinely benefits ordinary inhabitants?

## 19.2 Cells and connections

1. What makes a cell distinct: a boundary, identity, state, ruleset, history, or all of these?
2. Can cells contain other cells recursively?
3. Can a cell move, split, merge, or be copied?
4. Are lines stable routes, temporary connections, living entities, or different classes of relationship?
5. Can a line exist without an endpoint being known?
6. Can a cell be connected to another through more than one layer of the Interline?
7. Are gates engineered, discovered, inherited, or naturally occurring?

## 19.3 Game geography and narrative

1. Is The Switchyard a single station complex, a whole district, or a place that changes as routes are discovered?
2. Is Brass Meridian a city, a region containing multiple cities, or a landscape-scale industrial formation?
3. How do Icodomes physically relate to the town and arena?
4. What is the one-way train arrival's practical and symbolic purpose?
5. What is the relationship between the arena spectacle and the hidden institution?
6. Does the Fairfax family understand the deeper system, exploit it, or only control a piece of it?

## 19.4 Platform identity

1. Should The Meridian Survey be the umbrella brand, a fictional institution that inspires the brand, or a separate layer of the setting?
2. Should The Interline be visible to users as a platform concept, or remain an in-world term?
3. Should OpenLock remain the technical codename in repositories even if the public-facing brand changes?
4. How much of the fictional language should appear in the real client UI, package system, and documentation?
5. Which terms should be shared between technical documentation and in-world fiction, and which should remain distinct?

---

# 20. Short handoff brief

For future conversations, the most compact accurate mental model is:

**OpenLock is the original codename for a connected platform family, not a game. Confluent Dreams is one game within that family.** The family connects shells, client surfaces, tools, games, simulations, creator workflows, persistent agents, and worlds. It should feel like one continuous environment, even when its parts are implemented separately and run natively on different devices.

The emotional goal is to return to beloved creative worlds and inhabit them again — not just preserve them as artifacts, but let people create, participate, and watch them continue to live. The aesthetic is industrial occult, dieselpunk, twilight, brass and violet, painterly, nostalgic, and historically layered rather than generic cyberpunk or generic future-tech.

The conceptual structure is increasingly about **cells and the lines between them**. Cells are locally coherent places, agents, packages, or services. Lines connect them. Nodes and gates let the connections converge or cross boundaries. The between-space can itself be a world.

The Bleach recollection likely combines **Reiraku's red thread in *Fade to Black*** with **the Valley of Screams and Senna's red ribbon in *Memories of Nobody***. Deadlock's transport routes historically used the names Hyperlines, then Shadowlines, and now Transit Lines; Ley Lines are a distinct occult concept, with Astral Gates and old Shadowline Nexus terminology nearby.

The naming direction that has resonated most is a credible, old institutional name around surveying and confluence. **The Meridian Survey** remains a strong but unapproved candidate. **The Interline** could name the hidden connective structure. **Brass Meridian** and **The Switchyard** are places in the fictional world, and **Confluent Dreams** is the game title.

Do not prematurely solve the institution's true purpose. Its scale, records, architecture, and relationship to the lines may be more compelling while partially unknown.

---

# 21. Source and reference register

The project descriptions below are drawn from the user's own explanations and the repository discussions in the conversation. External media/game references are linked separately.

## 21.1 User project repositories

- [dl-openshell](https://github.com/alacripose/dl-openshell) — public OpenLock/Deadlock shell and UI project.
- [secure-shell](https://github.com/alacripose/secure-shell) — private repository discussed as the wider portable platform/backend architecture.
- [ala-cities](https://github.com/alacripose/ala-cities) — deterministic city simulation and civic systems.
- [ala_civ_bots_prototype](https://github.com/alacripose/ala_civ_bots_prototype) — persistent embodied citizens / Ensouled Civilization prototype.
- [hero-retarget-workbench](https://github.com/alacripose/hero-retarget-workbench) — Blender add-on and asset workflow for Deadlock hero models.

## 21.2 Bleach references

- [Bleach Wiki — Bleach: Fade to Black](https://bleach.fandom.com/wiki/Bleach%3A_Fade_to_Black) — Reiraku, Ichigo and Renji searching for Rukia, red ribbon-like tracking thread.
- [Bleach Wiki — Bleach: Memories of Nobody](https://bleach.fandom.com/wiki/Bleach%3A_Memories_of_Nobody) — Valley of Screams, Blanks, Senna, and the story's ending.
- [Bleach Wiki — Memories of Nobody image gallery](https://bleach.fandom.com/wiki/Bleach%3A_Memories_of_Nobody/Image_Gallery) — visual sequence descriptions, including Senna's ribbon and its final appearance.
- [Wikipedia — Bleach: Memories of Nobody](https://en.wikipedia.org/wiki/Bleach%3A_Memories_of_Nobody) — broad plot synopsis and ending summary.

## 21.3 Deadlock references

- [The Deadlock Wiki — Zip-lines](https://deadlock.wiki/Zip-lines) — Hyperlines / Shadowlines / Transit Lines development terminology.
- [The Deadlock Wiki — Shadowline](https://deadlock.wiki/Shadowline) — early Shadowline context, Shadowline Nexus terminology, archived voice-line references, and the community's proposed relation to Ley Lines.
- [The Deadlock Wiki — The Binding of Oathkeeper / Transcription](https://deadlock.wiki/The_Binding_of_Oathkeeper/Transcription) — in-progress lore transcription where Dynamo mentions Ley Lines and Astral Gates.
- [The Deadlock Wiki — Development](https://deadlock.wiki/Development) — community-maintained development timeline for Citadel, Neon Prime, Shadowline, and Deadlock.
- [Deadlock Guru — Zipline](https://deadlock.guru/wiki/map/zipline/) — alternate community reference for route naming and map details.
- [Deadlore — Glossary](https://thedeadlocklore.com/lore/glossary) — lore definitions and cited in-game references for Astral Gates and Shadowline Nexus.
- [Deadlock Archive — The Astral Gate](https://www.deadlockarchive.com/en/chronicle/astral-gate/) — archive treatment of Astral Gates and the Bermuda Triangle nexus reference.

## 21.4 Source quality and interpretation notes

- The user's own project descriptions and stated decisions are treated as primary evidence of their intentions.
- Repository links are included as project references, but this document is not a new audit of current repository state.
- The Bleach references are secondary wiki / synopsis sources. The films themselves are the primary references.
- Deadlock development history and removed Shadowline content are documented largely through community-maintained archives and wikis. They are useful for reconstructing terminology, but they should not be represented as direct Valve statements unless supported by official material.
- The Ley Lines reference in *The Binding of Oathkeeper* comes from a transcription marked as work in progress. It establishes that the term appears in that story material; it does not prove that the complete cosmology is finalized.
- Any analogy between Bleach, Deadlock, the user's fictional world, and the platform's cell architecture is an interpretation intended to help organize the user's ideas. It is not a claim that the source franchises share a canon or technical model.

---

# 22. Closing synthesis

The most important idea to preserve from the thread is not any single candidate name. It is the relationship between **inhabited cells, the lines that connect them, and the places where those lines become visible**.

A city, a game, a citizen, a package, a creative tool, and a client surface can all be locally coherent while still belonging to a larger living whole. A station is where someone enters. A Switchyard is where routes meet. A gate is where a boundary can be crossed. A line is what connects places that would otherwise remain separate. An institution may attempt to map the system, even if it does not fully understand what it has found.

The user's remembered Bleach images give that system an emotional dimension: the red thread is not simply a transit route; it is a connection that can be followed. The Valley of Screams is not just a gap between worlds; it is a place where lost things accumulate. Senna's ribbon is not just an object; it is a surviving trace of a person and a relationship.

The Deadlock references add a useful vocabulary distinction between the routes inhabitants can ride and the hidden occult geography that may underlie them. The user's own projects add the practical counterpart: packages, devices, services, citizens, and worlds that remain distinct but participate in a connected architecture.

**The Meridian Survey** and **The Interline** are promising because they express two different sides of that idea: the institution that maps, and the structure being mapped. They remain proposals. The right public identity should feel as though it belongs on an old station sign or the door of a real surveying office — with the unsettling implication that the people inside have been measuring something far larger than ordinary geography for a very long time.
