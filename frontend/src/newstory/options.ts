/**
 * Chronicle Creation — onboarding catalogs (Phase 0).
 *
 * Pure data + derived union types for the Quick / Guided / Advanced creation
 * flows. This module has NO side effects, NO React, and imports nothing from
 * the app — so wiring it up later cannot change current behaviour.
 *
 * Naming: the three creation experiences are a `CreationFlow`
 * ("quick" | "guided" | "advanced"). This is intentionally NOT called "mode",
 * because the ENGINE already uses `mode` to mean "basic" | "advanced"
 * simulation depth (see api.ts NewStory payload / backend).
 *
 * Closed catalogs (union types) are used for every Quick/Guided selection.
 * Free-text is reserved for Advanced/custom inputs only (custom premise,
 * custom genre/world concept, the Secret, and existing Advanced text fields).
 */

// --------------------------------------------------------------------------- //
// Shared shapes
// --------------------------------------------------------------------------- //

/** The creation experience a player is currently in. */
export type CreationFlow = "quick" | "guided" | "advanced";

/** Engine simulation depth (unchanged concept — distinct from CreationFlow). */
export type EngineMode = "basic" | "advanced";

/**
 * Every selectable option carries plain-language copy so the UI can show:
 *   1. label        — the name
 *   2. explanation  — what it changes, in plain language
 *   3. consequence  — an example of what to expect in play
 */
export type OptionCopy<V extends string = string> = {
  value: V;
  label: string;
  explanation: string;
  consequence: string;
};

// --------------------------------------------------------------------------- //
// QUICK START · Step 1 — World
// `genre` is the string sent to the backend (free-form there). "random" is
// resolved to a concrete world in the UI layer at selection time (Phase 2).
// --------------------------------------------------------------------------- //

export const QUICK_WORLDS = [
  {
    value: "fantasy",
    label: "Fantasy",
    genre: "fantasy",
    explanation: "Oaths, relics, and kingdoms in slow collapse.",
    consequence: "Expect: factions, old debts, and magic with a price.",
  },
  {
    value: "horror",
    label: "Horror",
    genre: "horror",
    explanation: "Isolation, dread, and false safety.",
    consequence: "Expect: scarce light, mounting panic, things that should not be.",
  },
  {
    value: "cyberpunk",
    label: "Cyberpunk",
    genre: "cyberpunk",
    explanation: "Neon cities, corporate power, bodies for sale.",
    consequence: "Expect: surveillance, debt, and tech that betrays you.",
  },
  {
    value: "post-apocalypse",
    label: "Post-Apocalypse",
    genre: "post-apocalyptic",
    explanation: "Scarcity, salvage, and trust as currency.",
    consequence: "Expect: shortages, hard trades, and dangerous strangers.",
  },
  {
    value: "modern",
    label: "Modern",
    genre: "modern",
    explanation: "The world as it is now — ordinary until it isn't.",
    consequence: "Expect: grounded stakes, social pressure, sudden escalation.",
  },
  {
    value: "mystery",
    label: "Mystery",
    genre: "detective",
    explanation: "Clues, lies, and a timeline that won't hold.",
    consequence: "Expect: suspects, secrets, and consequences for asking.",
  },
  {
    value: "random",
    label: "Random",
    genre: "", // resolved to a concrete world in the UI layer (Phase 2)
    explanation: "Let the engine choose your world.",
    consequence: "Expect: a surprise setting tuned to your choices.",
  },
] as const;

export type QuickWorldValue = (typeof QUICK_WORLDS)[number]["value"];

// --------------------------------------------------------------------------- //
// QUICK START · Step 2 — Character
// Maps to the top-level `role` string. "random" lets the engine decide.
// --------------------------------------------------------------------------- //

export const QUICK_CHARACTERS = [
  {
    value: "survivor",
    label: "Survivor",
    role: "a hardened survivor",
    explanation: "Someone who has already lived through the worst.",
    consequence: "Expect: resourcefulness, scars, and hard instincts.",
  },
  {
    value: "wanderer",
    label: "Wanderer",
    role: "a rootless wanderer",
    explanation: "A drifter with no fixed home or allegiance.",
    consequence: "Expect: outsider status, mobility, shallow ties.",
  },
  {
    value: "detective",
    label: "Detective",
    role: "an investigator",
    explanation: "Someone who reads people and uncovers truth.",
    consequence: "Expect: leads, leverage, and dangerous knowledge.",
  },
  {
    value: "soldier",
    label: "Soldier",
    role: "a soldier",
    explanation: "Trained for violence and chains of command.",
    consequence: "Expect: discipline, enemies, and orders that cost.",
  },
  {
    value: "outcast",
    label: "Outcast",
    role: "an outcast",
    explanation: "Cast out by society or your own people.",
    consequence: "Expect: distrust, freedom, and burned bridges.",
  },
  {
    value: "scholar",
    label: "Scholar",
    role: "a scholar",
    explanation: "Knowledge over force; curiosity over caution.",
    consequence: "Expect: insight, fragility, and forbidden answers.",
  },
  {
    value: "random",
    label: "Random",
    role: "", // engine decides
    explanation: "Let the engine choose who you are.",
    consequence: "Expect: a protagonist fitted to your world and tone.",
  },
] as const;

export type QuickCharacterValue = (typeof QUICK_CHARACTERS)[number]["value"];

// --------------------------------------------------------------------------- //
// QUICK START · Step 3 — Tone
// Maps to the existing `tone` value AND an auto `difficulty` default
// (difficulty is hidden in Quick Start; fully editable in Advanced).
// --------------------------------------------------------------------------- //

export const QUICK_TONES = [
  {
    value: "hopeful",
    label: "Hopeful",
    tone: "hopeful",
    difficulty: "standard",
    explanation: "The world can still be saved; people can still be reached.",
    consequence: "Expect: setbacks that recover, allies worth keeping.",
  },
  {
    value: "dark",
    label: "Dark",
    tone: "grim",
    difficulty: "hard",
    explanation: "Grim and uncertain; victories cost something.",
    consequence: "Expect: fewer safe routes, faster escalation.",
  },
  {
    value: "brutal",
    label: "Brutal",
    tone: "bleak",
    difficulty: "brutal",
    explanation: "Fragile survival; mistakes compound and death is quiet.",
    consequence: "Expect: scarcity, lasting wounds, causal death.",
  },
] as const;

export type QuickToneValue = (typeof QUICK_TONES)[number]["value"];

// --------------------------------------------------------------------------- //
// QUICK START · Step 4 — Story Hooks (3 required questions)
// These become persistent simulation inputs (Phase 1 seeding).
// --------------------------------------------------------------------------- //

/** "What do you want most?" */
export const HOOK_WANT = [
  { value: "redemption", label: "Redemption", explanation: "To make up for something.", consequence: "Expect: a past that demands atonement." },
  { value: "freedom", label: "Freedom", explanation: "To be free of control.", consequence: "Expect: cages, owners, and escape routes." },
  { value: "revenge", label: "Revenge", explanation: "To make someone pay.", consequence: "Expect: a target and a price for pursuing it." },
  { value: "wealth", label: "Wealth", explanation: "To gain resources and security.", consequence: "Expect: temptation, greed, and rivals." },
  { value: "safety", label: "Safety", explanation: "To find or protect a haven.", consequence: "Expect: threats to whatever you hold safe." },
  { value: "power", label: "Power", explanation: "To gain control over others or events.", consequence: "Expect: allies, enemies, and corruption." },
  { value: "knowledge", label: "Knowledge", explanation: "To uncover hidden truth.", consequence: "Expect: secrets that are dangerous to hold." },
  { value: "justice", label: "Justice", explanation: "To set something right.", consequence: "Expect: corruption, hard calls, and cost." },
] as const;
export type WantValue = (typeof HOOK_WANT)[number]["value"];

/** "What are you most afraid of?" */
export const HOOK_FEAR = [
  { value: "failure", label: "Failure", explanation: "Letting everything fall apart.", consequence: "Expect: high-stakes moments built around failing." },
  { value: "losing-control", label: "Losing control", explanation: "Becoming powerless over yourself or events.", consequence: "Expect: chaos and choices that slip away." },
  { value: "being-abandoned", label: "Being abandoned", explanation: "Being left behind by those you trust.", consequence: "Expect: loyalty tests and fragile bonds." },
  { value: "dying-alone", label: "Dying alone", explanation: "Ending with no one beside you.", consequence: "Expect: isolation pressure and meaningful company." },
  { value: "becoming-a-monster", label: "Becoming a monster", explanation: "Losing your humanity to survive.", consequence: "Expect: moral erosion and tempting cruelty." },
  { value: "being-forgotten", label: "Being forgotten", explanation: "Leaving no mark on the world.", consequence: "Expect: legacy stakes and the pull of recognition." },
] as const;
export type FearValue = (typeof HOOK_FEAR)[number]["value"];

/** "Who matters most to you?" */
export const HOOK_WHO_MATTERS = [
  { value: "child", label: "Child", explanation: "A child you must protect.", consequence: "Expect: an NPC whose safety drives stakes." },
  { value: "partner", label: "Partner", explanation: "A romantic or life partner.", consequence: "Expect: a bond that can be leveraged or lost." },
  { value: "friend", label: "Friend", explanation: "A close, trusted friend.", consequence: "Expect: loyalty arcs and shared history." },
  { value: "parent", label: "Parent", explanation: "A parent or guardian figure.", consequence: "Expect: obligation, debt, and old wounds." },
  { value: "mentor", label: "Mentor", explanation: "Someone who shaped you.", consequence: "Expect: guidance, expectations, betrayal risk." },
  { value: "nobody", label: "Nobody", explanation: "You stand alone.", consequence: "Expect: self-reliance and few social anchors." },
] as const;
export type WhoMattersValue = (typeof HOOK_WHO_MATTERS)[number]["value"];

// --------------------------------------------------------------------------- //
// ADVANCED · optional Narrative Hook Pool (closed catalogs)
// --------------------------------------------------------------------------- //

/** The Ghost — "What part of your past refuses to stay buried?" */
export const HOOK_GHOST = [
  { value: "betrayal", label: "Betrayal", explanation: "You were betrayed, or you betrayed someone.", consequence: "Expect: trust wounds resurfacing." },
  { value: "death", label: "Death", explanation: "A death you carry.", consequence: "Expect: grief and unfinished business." },
  { value: "failure", label: "Failure", explanation: "A failure that defined you.", consequence: "Expect: chances to repeat or redeem it." },
  { value: "crime", label: "Crime", explanation: "Something you did that broke the rules.", consequence: "Expect: pursuers and evidence." },
  { value: "secret", label: "Secret", explanation: "A buried truth about your past.", consequence: "Expect: pressure as it threatens to surface." },
  { value: "someone-abandoned", label: "Someone abandoned", explanation: "Someone you left behind.", consequence: "Expect: their return or your guilt." },
] as const;
export type GhostValue = (typeof HOOK_GHOST)[number]["value"];

/** The Dangerous Talent — "What are you unusually good at?" */
export const HOOK_TALENT = [
  { value: "fighting", label: "Fighting", explanation: "Violence is a tool you wield well.", consequence: "Expect: combat options and a reputation." },
  { value: "leadership", label: "Leadership", explanation: "People follow you.", consequence: "Expect: followers, responsibility, mutiny risk." },
  { value: "survival", label: "Survival", explanation: "You endure where others can't.", consequence: "Expect: edges in scarcity and the wild." },
  { value: "technology", label: "Technology", explanation: "Machines and systems obey you.", consequence: "Expect: hacks, fixes, and failures." },
  { value: "investigation", label: "Investigation", explanation: "You find what's hidden.", consequence: "Expect: leads others miss — and danger." },
  { value: "medicine", label: "Medicine", explanation: "You can heal and save.", consequence: "Expect: leverage, triage, and hard choices." },
  { value: "negotiation", label: "Negotiation", explanation: "You talk your way through.", consequence: "Expect: deals, debts, and double-crosses." },
] as const;
export type TalentValue = (typeof HOOK_TALENT)[number]["value"];

/** The Fatal Flaw — "What gets you into trouble?" */
export const HOOK_FLAW = [
  { value: "pride", label: "Pride", explanation: "You won't back down.", consequence: "Expect: escalations you could have avoided." },
  { value: "anger", label: "Anger", explanation: "You burn hot.", consequence: "Expect: bridges burned and rash acts." },
  { value: "curiosity", label: "Curiosity", explanation: "You have to know.", consequence: "Expect: doors you shouldn't open." },
  { value: "compassion", label: "Compassion", explanation: "You can't walk past suffering.", consequence: "Expect: detours and exploited mercy." },
  { value: "loyalty", label: "Loyalty", explanation: "You stay, even when you shouldn't.", consequence: "Expect: being used by those you trust." },
  { value: "fear", label: "Fear", explanation: "Fear can freeze or drive you.", consequence: "Expect: hesitation at the worst moments." },
] as const;
export type FlawValue = (typeof HOOK_FLAW)[number]["value"];

/** The Line — "What won't you do?" */
export const HOOK_LINE = [
  { value: "kill-innocents", label: "Kill innocents", explanation: "You will not harm the innocent.", consequence: "Expect: dilemmas that test this." },
  { value: "betray-allies", label: "Betray allies", explanation: "You will not sell out your people.", consequence: "Expect: temptations to break faith." },
  { value: "torture", label: "Torture", explanation: "You will not torture.", consequence: "Expect: information you can't easily get." },
  { value: "lie", label: "Lie", explanation: "You hold to the truth.", consequence: "Expect: honesty creating friction." },
  { value: "abandon-people", label: "Abandon people", explanation: "You don't leave people behind.", consequence: "Expect: costly rescues and dead weight." },
  { value: "nothing-off-limits", label: "Nothing is off limits", explanation: "You'll do whatever it takes.", consequence: "Expect: freedom — and a darkening reputation." },
] as const;
export type LineValue = (typeof HOOK_LINE)[number]["value"];

// --------------------------------------------------------------------------- //
// GUIDED START · one contextual world question per world
// Concrete, imaginative questions that establish world tension before play.
// The chosen answer becomes a strong world seed (Phase 2 maps it to
// `custom_premise`). "random" has no guided question.
// --------------------------------------------------------------------------- //

export type GuidedQuestion = {
  question: string;
  options: OptionCopy[];
};

export const GUIDED_QUESTIONS: Partial<Record<QuickWorldValue, GuidedQuestion>> = {
  cyberpunk: {
    question: "What is the city's biggest problem?",
    options: [
      { value: "ai-controls-everything", label: "AI controls everything", explanation: "An intelligence runs the systems people depend on.", consequence: "Expect: surveillance, automated enforcement, blind spots." },
      { value: "water-is-poisoned", label: "Water is poisoned", explanation: "The basics of life are compromised.", consequence: "Expect: scarcity, sickness, black-market supply." },
      { value: "corporate-war", label: "Corporate war", explanation: "Megacorps fight openly for control.", consequence: "Expect: factions, collateral damage, shifting loyalty." },
      { value: "plague-outbreak", label: "Plague outbreak", explanation: "A spreading sickness grips the city.", consequence: "Expect: quarantine, panic, desperate choices." },
      { value: "nobody-remembers-yesterday", label: "Nobody remembers yesterday", explanation: "Memory itself is failing or stolen.", consequence: "Expect: unreliable truth, lost identity, hidden actors." },
    ],
  },
  fantasy: {
    question: "What is changing in the world?",
    options: [
      { value: "magic-is-dying", label: "Magic is dying", explanation: "The old power is draining away.", consequence: "Expect: desperation, relics, fading orders." },
      { value: "monsters-are-spreading", label: "Monsters are spreading", explanation: "The wild things are reclaiming the land.", consequence: "Expect: refugees, frontier dread, broken roads." },
      { value: "kingdoms-are-collapsing", label: "Kingdoms are collapsing", explanation: "Thrones and borders are failing.", consequence: "Expect: power vacuums, warlords, opportunity." },
      { value: "the-dead-are-returning", label: "The dead are returning", explanation: "Death is no longer final.", consequence: "Expect: grief weaponised, taboo, escalating dread." },
    ],
  },
  "post-apocalypse": {
    question: "What ended civilization?",
    options: [
      { value: "war", label: "War", explanation: "Humanity destroyed itself.", consequence: "Expect: ruins, militias, unexploded danger." },
      { value: "disease", label: "Disease", explanation: "A plague unmade the world.", consequence: "Expect: contamination, distrust, fragile enclaves." },
      { value: "ai", label: "AI", explanation: "Machines turned on their makers.", consequence: "Expect: hostile automation, dead networks, hiding." },
      { value: "climate-collapse", label: "Climate collapse", explanation: "The environment turned lethal.", consequence: "Expect: extreme weather, migration, resource war." },
      { value: "unknown-event", label: "Unknown event", explanation: "No one truly knows what happened.", consequence: "Expect: mystery, rumor, fragments of truth." },
    ],
  },
  horror: {
    question: "What is wrong with this place?",
    options: [
      { value: "something-is-hunting", label: "Something is hunting", explanation: "A predator stalks the dark.", consequence: "Expect: pursuit, dwindling safety, hard hiding." },
      { value: "reality-is-unraveling", label: "Reality is unraveling", explanation: "The rules of the world are breaking.", consequence: "Expect: distortion, dread, unreliable senses." },
      { value: "people-are-changing", label: "People are changing", explanation: "Those around you are becoming wrong.", consequence: "Expect: paranoia, betrayal, isolation." },
      { value: "the-place-is-cursed", label: "The place is cursed", explanation: "The location itself is malign.", consequence: "Expect: traps, history, escalating pressure." },
    ],
  },
  modern: {
    question: "What just went wrong in your life?",
    options: [
      { value: "you-witnessed-something", label: "You witnessed something", explanation: "You saw what you shouldn't have.", consequence: "Expect: pursuit, silence, dangerous knowledge." },
      { value: "someone-vanished", label: "Someone vanished", explanation: "A person close to you disappeared.", consequence: "Expect: a search, suspects, hidden truth." },
      { value: "you-owe-the-wrong-people", label: "You owe the wrong people", explanation: "A debt has come due.", consequence: "Expect: pressure, threats, hard bargains." },
      { value: "a-disaster-struck", label: "A disaster struck", explanation: "Sudden catastrophe upended everything.", consequence: "Expect: chaos, scarcity, rapid escalation." },
    ],
  },
  mystery: {
    question: "What case pulls you in?",
    options: [
      { value: "a-body-with-no-name", label: "A body with no name", explanation: "An unidentified victim starts the trail.", consequence: "Expect: identity puzzles, lies, dead ends." },
      { value: "a-disappearance", label: "A disappearance", explanation: "Someone is missing and time matters.", consequence: "Expect: leads, suspects, a ticking clock." },
      { value: "a-betrayal-within", label: "A betrayal within", explanation: "Someone close is not who they seem.", consequence: "Expect: trust erosion, hidden motives." },
      { value: "a-pattern-of-crimes", label: "A pattern of crimes", explanation: "Connected events point to one hand.", consequence: "Expect: escalation, profiling, exposure risk." },
    ],
  },
};

// --------------------------------------------------------------------------- //
// "Improve existing options" copy (Advanced Builder).
// Plain-language explanation + example consequence for the existing Advanced
// catalogs (PRESSURE_OPTIONS and the intensity/social CONTENT_ROWS in
// new-story.tsx). Keyed by the SAME values already used there so Phase 4 can
// attach this copy without changing those source-of-truth value lists.
// --------------------------------------------------------------------------- //

export const PRESSURE_COPY: Record<string, { explanation: string; consequence: string }> = {
  starvation: { explanation: "Food is running out.", consequence: "Expect: weakness, theft, desperate trades." },
  infection: { explanation: "Disease or wounds threaten the body.", consequence: "Expect: spread, quarantine, hard triage." },
  war: { explanation: "Organized violence shapes the region.", consequence: "Expect: fronts, conscription, collateral loss." },
  predators: { explanation: "Something hunts the living.", consequence: "Expect: ambushes, fear, unsafe travel." },
  "political collapse": { explanation: "Governments are failing; power vacuums spread.", consequence: "Expect: faction conflict, corruption, local warlords." },
  insanity: { explanation: "Minds and reality are coming apart.", consequence: "Expect: unreliable perception, dread, breakdown." },
  "extreme weather": { explanation: "The environment turns hostile.", consequence: "Expect: exposure, blocked routes, shelter pressure." },
  "AI surveillance": { explanation: "You are watched and tracked.", consequence: "Expect: traced movement, predictive enforcement." },
  "supernatural corruption": { explanation: "Reality is becoming unstable.", consequence: "Expect: strange phenomena, altered locations, escalating dread." },
  scarcity: { explanation: "Resources are difficult to obtain.", consequence: "Expect: hard choices, shortages, trade pressure." },
  "civil unrest": { explanation: "The social order is fraying.", consequence: "Expect: riots, crackdowns, shifting allegiances." },
};

export const CONTENT_COPY: Record<string, { explanation: string; consequence: string }> = {
  gore: { explanation: "How graphically violence is described.", consequence: "Higher: visceral injury detail; lower: restrained framing." },
  psychological_horror: { explanation: "How much dread and mental strain the world applies.", consequence: "Higher: paranoia, unreliable perception, mounting fear." },
  scarcity: { explanation: "How hard resources are to obtain.", consequence: "Higher: shortages, trade pressure, survival math." },
  cruelty: { explanation: "How harshly NPCs and factions can behave.", consequence: "Higher: exploitation, ruthless actors, betrayal." },
  moral_ambiguity: { explanation: "How clear-cut right and wrong are.", consequence: "Higher: no clean choices; everyone has reasons." },
  relationships: {
    explanation: "Depth of social and emotional dynamics (engine system, not flavor).",
    consequence: "Affects NPC memory, trust, leverage, jealousy, and delayed consequences.",
  },
};
