import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import MovesPanel from "../src/MovesPanel";
import * as api from "../src/api";

jest.mock("../src/api", () => ({
  ...jest.requireActual("../src/api"),
  getMoves: jest.fn(),
  previewMove: jest.fn(),
}));

const unavailable = (kind: string, reason: string) => ({ kind, available: false, reason });

const MOVES = {
  turn_count: 3,
  moves: {
    challenge: {
      kind: "challenge", available: true, reason: null,
      audiences: [{ name: "Mrs. Vance" }],
      statements: [{ turn: 2, paragraph: 0, text: '"I never left the house," Mrs. Vance says.', speakers: ["Mrs. Vance"] }],
      passages: [{ turn: 1, paragraph: 0, text: "Muddy boot prints cross the hall." }],
      items: ["folded ticket stub"],
    },
    bargain: unavailable("bargain", "You have nothing to trade."),
    route: {
      kind: "route", available: true, reason: null, here: "the lobby", routes: [], people: [{ name: "Mr. Pell" }],
      places: ["the boiler room"], passages: [{ turn: 2, paragraph: 1, text: "A narrow passage descends toward the boiler room." }],
    },
    regard: unavailable("regard", "You need two other people here to work on."),
    build: unavailable("build", "You have nothing to spend."),
    signal: unavailable("signal", "Nobody here trusts you enough to settle a signal with."),
    teach: unavailable("teach", "Nobody here is willing to teach or learn from you."),
  },
};

function open(onSend = jest.fn()) {
  (api.getMoves as jest.Mock).mockResolvedValue(MOVES);
  render(<MovesPanel visible sessionId="s1" deviceId="d1" busy={false} onSend={onSend} onClose={jest.fn()} />);
  return onSend;
}

describe("MovesPanel", () => {
  beforeEach(() => jest.clearAllMocks());

  test("a move the scene cannot support is disabled and says why, with no form", async () => {
    open();
    await screen.findByTestId("move-challenge");
    expect(screen.getByTestId("move-bargain").props.accessibilityState?.disabled ?? screen.getByTestId("move-bargain").props.disabled).toBeTruthy();
    expect(screen.getByText("You have nothing to trade.")).toBeTruthy();
    expect(screen.queryByTestId("move-form-bargain")).toBeNull();
  });

  test("challenge sends exactly the statement, evidence and audience the player picked", async () => {
    const onSend = open();
    fireEvent.press(await screen.findByTestId("move-challenge"));
    expect(screen.getByTestId("move-send-btn").props.accessibilityState?.disabled ?? screen.getByTestId("move-send-btn").props.disabled).toBeTruthy();
    fireEvent.press(screen.getByTestId("mv-audience-mrs-vance"));
    fireEvent.press(screen.getByTestId("mv-subject-2-0"));
    fireEvent.press(screen.getByTestId("mv-evidence-1-0"));
    fireEvent.press(screen.getByTestId("mv-item-folded-ticket-stub"));
    fireEvent.press(screen.getByTestId("move-send-btn"));
    expect(onSend).toHaveBeenCalledWith({
      kind: "challenge",
      args: {
        audience: "Mrs. Vance",
        subject: { turn: 2, paragraph: 0, speaker: "Mrs. Vance" },
        evidence: [{ turn: 1, paragraph: 0 }, { item: "folded ticket stub" }],
        aloud: false,
      },
    });
  });

  test("route discovery needs a passage and a place, and previews through the server", async () => {
    const onSend = open();
    (api.previewMove as jest.Mock).mockResolvedValue({ kind: "route", can_commit: false, issues: ["Say where it leads."] });
    fireEvent.press(await screen.findByTestId("move-route"));
    fireEvent.press(screen.getByTestId("mv-via-2-1"));
    fireEvent.press(screen.getByTestId("mv-to-the-boiler-room"));
    fireEvent.press(screen.getByTestId("move-check-btn"));
    await waitFor(() => expect(api.previewMove).toHaveBeenCalledWith("s1", "d1", {
      kind: "route", op: "discover", args: { via: { turn: 2, paragraph: 1 }, to: "the boiler room" },
    }));
    expect(await screen.findByText("Say where it leads.")).toBeTruthy();
    // The server said no, so the panel refuses to send it.
    fireEvent.press(screen.getByTestId("move-send-btn"));
    expect(onSend).not.toHaveBeenCalled();
  });

  test("the same move gets the same action text and a different move does not", () => {
    const a = { kind: "route", op: "discover", args: { to: "x" } } as const;
    expect(api.moveActionText(a as any)).toBe(api.moveActionText({ ...a } as any));
    expect(api.moveActionText(a as any)).not.toBe(api.moveActionText({ ...a, args: { to: "y" } } as any));
  });
});
