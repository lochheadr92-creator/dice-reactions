import React from "react";
import { fireEvent, render, screen } from "@testing-library/react-native";
import InventoryPanel from "../src/InventoryPanel";
import { itemActionText, parseLedger, splitItems } from "../src/inventory";

describe("splitItems", () => {
  test("splits lists, keeps brackets together, drops empties", () => {
    expect(splitItems("flashlight, coat; rope and 3 bandages.")).toEqual(["flashlight", "coat", "rope", "3 bandages"]);
    expect(splitItems("knife (rusty, sharp), lantern")).toEqual(["knife (rusty, sharp)", "lantern"]);
    expect(splitItems("none")).toEqual([]);
    expect(splitItems("—")).toEqual([]);
    expect(splitItems("")).toEqual([]);
  });
});

describe("parseLedger", () => {
  const model = parseLedger({
    Worn: "wool coat, leather boots, cap",
    Weapons: "hatchet, pistol",
    Tools: "flashlight, lockpicks",
    Carried: "canvas satchel, keys, folded letter",
    Supplies: "3 bandages, water",
    Uncertain: "radio?",
    Load: "light",
  });

  test("puts worn and held things on the figure", () => {
    expect(model.slots.body.map((i) => i.name)).toEqual(["Wool coat"]);
    expect(model.slots.feet.map((i) => i.name)).toEqual(["Leather boots"]);
    expect(model.slots.head.map((i) => i.name)).toEqual(["Cap"]);
    expect(model.slots.mainHand.map((i) => i.name)).toEqual(["Hatchet"]);
    expect(model.slots.offHand.map((i) => i.name)).toEqual(["Flashlight"]);
    expect(model.slots.back.map((i) => i.name)).toEqual(["Canvas satchel"]);
    expect(model.slots.belt.map((i) => i.name)).toEqual(expect.arrayContaining(["Pistol", "Lockpicks", "Keys"]));
  });

  test("everything stays in a group list and nothing is invented", () => {
    const all = model.groups.flatMap((g) => g.items.map((i) => i.name)).sort();
    expect(all).toEqual(
      ["Cap", "Canvas satchel", "Flashlight", "Folded letter", "Hatchet", "Keys", "Leather boots", "Lockpicks", "Pistol", "Radio", "Water", "Wool coat", "Bandages"].sort()
    );
    expect(model.pockets.map((i) => i.name)).toEqual(["Folded letter"]);
    expect(model.groups.find((g) => g.key === "Supplies")?.items[0]).toMatchObject({ name: "Bandages", qty: 3 });
    expect(model.groups.find((g) => g.key === "Uncertain")?.items[0].uncertain).toBe(true);
    expect(model.load).toBe("light");
  });

  test("an empty or missing ledger is empty", () => {
    expect(parseLedger(null).empty).toBe(true);
    expect(parseLedger({ Carried: "nothing", Worn: "none" }).empty).toBe(true);
  });

  test("a bag of something is supplies, not a back slot", () => {
    const m = parseLedger({ Carried: "bag of rice" });
    expect(m.slots.back).toEqual([]);
    expect(m.pockets.map((i) => i.name)).toEqual(["Bag of rice"]);
  });
});

describe("InventoryPanel", () => {
  const ledger = { Worn: "wool coat", Weapons: "hatchet", Carried: "folded letter", Load: "light" };

  const noop = jest.fn();

  test("shows the figure with equipment and puts an item line in the action box when tapped", () => {
    const onAct = jest.fn();
    render(<InventoryPanel ledger={ledger} characterName="Mara" onAct={onAct} onClose={noop} onCheckInStory={jest.fn()} />);
    expect(screen.getByTestId("inventory-figure")).toBeTruthy();
    expect(screen.getByTestId("inventory-who")).toHaveTextContent("MARA");
    expect(screen.getByTestId("slot-body")).toHaveTextContent(/Wool coat/);
    expect(screen.getByTestId("slot-mainHand")).toHaveTextContent(/Hatchet/);
    expect(screen.getByTestId("slot-head")).toHaveTextContent(/empty/);
    expect(screen.queryByTestId("inventory-actions")).toBeNull();
    fireEvent.press(screen.getByTestId("slot-item-worn-0-wool-coat"));
    expect(onAct).toHaveBeenCalledTimes(1);                              // straight away, no second tap
    expect(onAct).toHaveBeenLastCalledWith("I take a close look at my wool coat.");
    expect(screen.getByTestId("inventory-actions")).toBeTruthy();
    fireEvent.press(screen.getByTestId("inv-act-use"));                  // a button swaps the line
    expect(onAct).toHaveBeenLastCalledWith("I use my wool coat.");
  });

  test("a plain item defaults to use, a weapon offers ready, and it still fills the box while a turn is running", () => {
    const onAct = jest.fn();
    const { rerender } = render(<InventoryPanel ledger={ledger} onAct={onAct} onClose={noop} onCheckInStory={jest.fn()} />);
    fireEvent.press(screen.getByTestId("inv-item-weapons-0-hatchet"));
    expect(onAct).toHaveBeenLastCalledWith("I use my hatchet.");
    expect(screen.getByTestId("inv-act-ready")).toBeTruthy();
    fireEvent.press(screen.getByTestId("inv-item-carried-0-folded-letter"));
    expect(screen.queryByTestId("inv-act-ready")).toBeNull();
    fireEvent.press(screen.getByTestId("inv-act-stow"));
    expect(onAct).toHaveBeenLastCalledWith("I put my folded letter away safely.");
    rerender(<InventoryPanel ledger={ledger} busy onAct={onAct} onClose={noop} onCheckInStory={jest.fn()} />);
    fireEvent.press(screen.getByTestId("inv-act-examine"));
    expect(onAct).toHaveBeenLastCalledWith("I take a close look at my folded letter.");
  });

  test("done closes the panel without sending anything", () => {
    const onClose = jest.fn();
    const onAct = jest.fn();
    render(<InventoryPanel ledger={ledger} onAct={onAct} onClose={onClose} onCheckInStory={jest.fn()} />);
    fireEvent.press(screen.getByTestId("inv-item-weapons-0-hatchet"));
    fireEvent.press(screen.getByTestId("inventory-done"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  test("an empty ledger still lets the player check in the story", () => {
    const check = jest.fn();
    render(<InventoryPanel ledger={{}} onAct={jest.fn()} onClose={jest.fn()} onCheckInStory={check} />);
    expect(screen.getByTestId("inventory-empty")).toBeTruthy();
    fireEvent.press(screen.getByTestId("ledger-check-action"));
    expect(check).toHaveBeenCalled();
  });

  test("action sentences read naturally for worn gear", () => {
    expect(itemActionText("stow", { id: "x", name: "Wool coat", category: "Worn" }, true)).toBe(
      "I check how my wool coat is sitting and whether it is holding up."
    );
  });
});
