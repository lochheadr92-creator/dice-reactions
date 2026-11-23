/**
 * Turns the player's ledger (free text per category, e.g. `Worn: coat, boots`) into something the
 * inventory screen can draw: items, equipment slots on a character figure, and grouped lists.
 *
 * This only reads what the ledger already says. It never invents an item, and an item it cannot
 * place on the figure stays in the grouped list.
 */

export type Slot = "head" | "body" | "hands" | "feet" | "mainHand" | "offHand" | "back" | "belt";

export type InvItem = {
  id: string;
  name: string;
  qty?: number;
  category: string;
  uncertain?: boolean;
};

export type InvGroup = { key: string; label: string; items: InvItem[] };

export type InventoryModel = {
  slots: Record<Slot, InvItem[]>;
  groups: InvGroup[];
  /** Carried things that fit no slot. */
  pockets: InvItem[];
  load?: string;
  empty: boolean;
};

export const SLOT_ORDER: Slot[] = ["head", "body", "hands", "feet", "mainHand", "offHand", "back", "belt"];

export const SLOT_LABEL: Record<Slot, string> = {
  head: "HEAD",
  body: "BODY",
  hands: "HANDS",
  feet: "FEET",
  mainHand: "MAIN HAND",
  offHand: "OFF HAND",
  back: "BACK",
  belt: "BELT",
};

const CATEGORY_ORDER = ["Worn", "Weapons", "Tools", "Carried", "Supplies", "Ammo", "Currency", "Stored", "Uncertain", "Notes"];

const CATEGORY_LABEL: Record<string, string> = {
  Worn: "WORN",
  Weapons: "WEAPONS",
  Tools: "TOOLS",
  Carried: "CARRIED",
  Supplies: "SUPPLIES",
  Ammo: "AMMO",
  Currency: "MONEY",
  Stored: "STORED AWAY",
  Uncertain: "NOT SURE ABOUT",
  Notes: "NOTES",
};

const NONE = /^(none|nothing|empty|n\/a|no|nil|unknown|—|-|–)$/i;

const RE = {
  head: /\b(hat|cap|helmet|hood|hardhat|beanie|crown|mask|goggles|glasses|bandana)\b/i,
  feet: /\b(boots?|shoes?|sandals?|socks?|greaves|trainers)\b/i,
  hands: /\b(gloves?|gauntlets?|mittens?)\b/i,
  back: /\b(backpack|rucksack|satchel|quiver|cloak|cape|knapsack|haversack)\b|\b(bag|pack)\b(?! of)/i,
  belt: /\b(belt|pouch|holster|sheath|scabbard|bandolier|keyring|keys)\b/i,
  body: /\b(coat|jacket|vest|armou?r|shirt|dress|robe|tunic|jumper|sweater|overalls|uniform|raincoat|trousers|pants|jeans|mail|apron|poncho)\b/i,
  weapon: /\b(knife|dagger|sword|axe|hatchet|pistol|gun|revolver|rifle|shotgun|bow|crossbow|club|bat|staff|spear|machete|crowbar|hammer|cudgel|baton|blade|cleaver)\b/i,
  offHand: /\b(torch|lantern|flashlight|lamp|shield|radio|map|compass)\b/i,
};

/** Split on commas, semicolons and "and", but not inside brackets. */
export function splitItems(value: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let cur = "";
  const text = String(value ?? "");
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (ch === "(" || ch === "[") depth++;
    if (ch === ")" || ch === "]") depth = Math.max(0, depth - 1);
    if (depth === 0 && (ch === "," || ch === ";" || ch === "\n")) {
      parts.push(cur);
      cur = "";
      continue;
    }
    cur += ch;
  }
  parts.push(cur);
  const out: string[] = [];
  for (const raw of parts) {
    for (const piece of raw.split(/\s+and\s+(?![^()]*\))/i)) {
      const s = piece
        .replace(/^[-•*\s]+/, "")
        .replace(/[.\s]+$/, "")
        .trim();
      if (s && !NONE.test(s)) out.push(s);
    }
  }
  return out;
}

function toItem(raw: string, category: string, index: number): InvItem {
  let name = raw;
  let qty: number | undefined;
  const lead = name.match(/^(\d+)\s*(?:x|×)?\s+(.+)$/i);
  const trail = name.match(/^(.+?)\s*(?:x|×)\s*(\d+)$/i);
  if (lead) {
    qty = parseInt(lead[1], 10);
    name = lead[2];
  } else if (trail) {
    name = trail[1];
    qty = parseInt(trail[2], 10);
  }
  const uncertain = category === "Uncertain" || /\?\s*$/.test(name);
  name = name.replace(/\?\s*$/, "").trim();
  return {
    id: `${category.toLowerCase()}-${index}-${name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "")}`,
    name: name.charAt(0).toUpperCase() + name.slice(1),
    qty: qty && qty > 1 ? qty : undefined,
    category,
    uncertain: uncertain || undefined,
  };
}

function emptySlots(): Record<Slot, InvItem[]> {
  return { head: [], body: [], hands: [], feet: [], mainHand: [], offHand: [], back: [], belt: [] };
}

export function isWeapon(item: InvItem): boolean {
  return item.category === "Weapons" || RE.weapon.test(item.name);
}

export function parseLedger(ledger: Record<string, unknown> | null | undefined): InventoryModel {
  const slots = emptySlots();
  const groups: InvGroup[] = [];
  const pockets: InvItem[] = [];
  const src = ledger || {};
  const keys = Object.keys(src);
  const ordered = [
    ...CATEGORY_ORDER.filter((k) => keys.includes(k)),
    ...keys.filter((k) => !CATEGORY_ORDER.includes(k) && k !== "Load"),
  ];

  for (const key of ordered) {
    const items = splitItems(String(src[key] ?? "")).map((raw, i) => toItem(raw, key, i));
    if (items.length === 0) continue;
    groups.push({ key, label: CATEGORY_LABEL[key] || key.toUpperCase(), items });
    if (key === "Uncertain" || key === "Notes" || key === "Currency" || key === "Ammo" || key === "Supplies" || key === "Stored") continue;
    for (const item of items) {
      const placed = place(slots, item, key);
      if (!placed && key === "Carried") pockets.push(item);
    }
  }

  const load = String(src["Load"] ?? "").trim();
  return {
    slots,
    groups,
    pockets,
    load: load && !NONE.test(load) ? load : undefined,
    empty: groups.length === 0,
  };
}

function place(slots: Record<Slot, InvItem[]>, item: InvItem, category: string): boolean {
  const n = item.name;
  if (category === "Worn") {
    for (const s of ["head", "feet", "hands", "back", "belt", "body"] as Slot[]) {
      if (RE[s as "head"].test(n)) {
        slots[s].push(item);
        return true;
      }
    }
    slots.body.push(item);
    return true;
  }
  if (category === "Weapons" || RE.weapon.test(n)) {
    if (RE.offHand.test(n) && /shield/i.test(n)) {
      slots.offHand.push(item);
      return true;
    }
    (slots.mainHand.length === 0 ? slots.mainHand : slots.belt).push(item);
    return true;
  }
  if (RE.offHand.test(n)) {
    (slots.offHand.length === 0 ? slots.offHand : slots.belt).push(item);
    return true;
  }
  if (RE.back.test(n) && slots.back.length === 0) {
    slots.back.push(item);
    return true;
  }
  if (RE.belt.test(n)) {
    slots.belt.push(item);
    return true;
  }
  if (category === "Tools") {
    slots.belt.push(item);
    return true;
  }
  return false;
}

/** The sentence sent to the story when the player picks an action on an item. */
export type ItemAction = "examine" | "use" | "ready" | "stow" | "set_down";

export function itemActions(item: InvItem, equipped: boolean): { key: ItemAction; label: string }[] {
  const out: { key: ItemAction; label: string }[] = [
    { key: "examine", label: "EXAMINE" },
    { key: "use", label: "USE" },
  ];
  if (isWeapon(item) || item.category === "Tools") out.push({ key: "ready", label: "READY" });
  out.push({ key: "stow", label: equipped && item.category === "Worn" ? "CHECK FIT" : "PUT AWAY" });
  out.push({ key: "set_down", label: "SET DOWN" });
  return out;
}

export function itemActionText(action: ItemAction, item: InvItem, equipped: boolean): string {
  const name = item.name.toLowerCase();
  switch (action) {
    case "examine":
      return `I take a close look at my ${name}.`;
    case "use":
      return `I use my ${name}.`;
    case "ready":
      return `I get my ${name} ready to use.`;
    case "stow":
      return equipped && item.category === "Worn" ? `I check how my ${name} is sitting and whether it is holding up.` : `I put my ${name} away safely.`;
    case "set_down":
      return `I set my ${name} down here.`;
  }
}
