import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react-native";
import DuetPlay from "../app/duets/[id]";
import type { DuetComparison, DuetView } from "../src/api";

const mockGetDuet = jest.fn();
const mockDuetAction = jest.fn();
const mockGetComparison = jest.fn();
const mockShare = jest.fn();
const mockPropose = jest.fn();
const mockRespond = jest.fn();

jest.mock("expo-router", () => ({
  useRouter: () => ({ push: jest.fn() }),
  useLocalSearchParams: () => ({ id: "duet-1" }),
}));

jest.mock("../src/storage", () => ({ getDeviceId: async () => "dev-a" }));

jest.mock("../src/api", () => ({
  ApiError: require("../src/api-error").ApiError,
  getDuet: (...a: unknown[]) => mockGetDuet(...a),
  duetAction: (...a: unknown[]) => mockDuetAction(...a),
  endDuetChapter: jest.fn(),
  proposeDuetSignal: (...a: unknown[]) => mockPropose(...a),
  respondDuetSignal: (...a: unknown[]) => mockRespond(...a),
  getDuetComparison: (...a: unknown[]) => mockGetComparison(...a),
  shareDuetComparison: (...a: unknown[]) => mockShare(...a),
}));

function duet(over: Partial<DuetView> = {}): DuetView {
  return {
    id: "duet-1",
    title: "Two Lights",
    status: "active",
    you: { seat: "ferryman", label: "ferryman", character: { name: "Corin Hale", role: "ferryman", inventory: ["ferry pole"] } },
    other: { seat: "keeper", name: "Ines Rook", role: "signal keeper", joined: true },
    turn_count: 0,
    your_turn: true,
    waiting_for: null,
    history: [{ turn: 0, kind: "opening", text: "The harbour is dark." }],
    choices: [{ label: "A", text: "Check the tide table" }],
    known: { boat: "the ferry skiff is moored at the harbour" },
    signals: [],
    signal_window_open: false,
    chapter_ended: false,
    ...over,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
});

test("your turn shows choices and sends one request id for a retried action", async () => {
  mockGetDuet.mockResolvedValue({ duet: duet() });
  mockDuetAction.mockRejectedValueOnce(new Error("network")).mockResolvedValueOnce({ duet: duet({ your_turn: false, turn_count: 1, choices: [], waiting_for: "Ines Rook" }), replayed: false });
  render(<DuetPlay />);
  await screen.findByTestId("duet-your-turn");
  expect(screen.getByTestId("duet-inventory").props.children.join("")).toContain("ferry pole");
  fireEvent.press(screen.getByTestId("duet-choice-A"));
  await waitFor(() => expect(mockDuetAction).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.queryByTestId("duet-error")).toBeTruthy());
  fireEvent.press(screen.getByTestId("duet-choice-A"));
  await waitFor(() => expect(mockDuetAction).toHaveBeenCalledTimes(2));
  const [first, second] = mockDuetAction.mock.calls.map((c) => c[2]);
  expect(second.action_request_id).toBe(first.action_request_id);
  expect(second.expected_turn_count).toBe(0);
  await waitFor(() => expect(screen.getByTestId("duet-state")).toHaveTextContent("WAITING FOR INES ROOK"));
  expect(screen.queryByTestId("duet-input")).toBeNull();
});

test("waiting for the other player shows no choices and no input", async () => {
  mockGetDuet.mockResolvedValue({ duet: duet({ your_turn: false, choices: [], waiting_for: "Ines Rook" }) });
  render(<DuetPlay />);
  await waitFor(() => expect(screen.getByTestId("duet-state")).toHaveTextContent("WAITING FOR INES ROOK"));
  expect(screen.queryByTestId("duet-input")).toBeNull();
  expect(screen.queryByTestId("duet-choice-A")).toBeNull();
});

test("after the chapter only your own account shows until both agree", async () => {
  const ended = duet({ status: "chapter_ended", chapter_ended: true, your_turn: false, choices: [] });
  mockGetDuet.mockResolvedValue({ duet: ended });
  const mine: DuetComparison = {
    ended: true,
    you_shared: null,
    both_shared: false,
    accounts: [{ seat: "ferryman", mine: true, character: { name: "Corin Hale", role: "ferryman" }, entries: [] }],
  };
  mockGetComparison.mockResolvedValue(mine);
  render(<DuetPlay />);
  await screen.findByTestId("duet-share-yes");
  expect(screen.queryByTestId("duet-account-keeper")).toBeNull();
  mockShare.mockResolvedValue({ ...mine, you_shared: true });
  fireEvent.press(screen.getByTestId("duet-share-yes"));
  await screen.findByTestId("duet-share-state");
  expect(screen.queryByTestId("duet-account-keeper")).toBeNull();
});

test("both opted in shows two accounts", async () => {
  mockGetDuet.mockResolvedValue({ duet: duet({ status: "chapter_ended", chapter_ended: true, your_turn: false, choices: [] }) });
  mockGetComparison.mockResolvedValue({
    ended: true,
    you_shared: true,
    both_shared: true,
    accounts: [
      { seat: "ferryman", mine: true, character: { name: "Corin Hale", role: "ferryman" }, entries: [] },
      { seat: "keeper", mine: false, character: { name: "Ines Rook", role: "signal keeper" }, entries: [] },
    ],
  });
  render(<DuetPlay />);
  await screen.findByTestId("duet-account-keeper");
  expect(screen.getByTestId("duet-account-ferryman")).toBeTruthy();
});


test("signals can be offered before the first lamp, answered by the other seat, and a faint flash is sent as faint", async () => {
  mockGetDuet.mockResolvedValue({ duet: duet({ signal_window_open: true, signals: [{ id: "sg1", count: 3, meaning: "the soldiers are coming", status: "proposed", mine: false }] }) });
  mockRespond.mockResolvedValue({ duet: duet({ signal_window_open: true, signals: [{ id: "sg1", count: 3, meaning: "the soldiers are coming", status: "agreed", mine: false }] }) });
  mockPropose.mockResolvedValue({ duet: duet({ signal_window_open: true }) });
  mockDuetAction.mockResolvedValue({ duet: duet({ your_turn: false, turn_count: 1, choices: [], waiting_for: "Ines Rook" }), replayed: false });
  render(<DuetPlay />);
  await screen.findByTestId("duet-signals");
  expect(screen.getByTestId("duet-signal-3")).toHaveTextContent(/3 flashes: the soldiers are coming/);
  fireEvent.press(screen.getByTestId("duet-signal-accept-3"));
  await waitFor(() => expect(mockRespond).toHaveBeenCalledWith("dev-a", "duet-1", "sg1", true));
  fireEvent.changeText(screen.getByTestId("duet-signal-count"), "2");
  fireEvent.changeText(screen.getByTestId("duet-signal-meaning"), "all clear");
  fireEvent.press(screen.getByTestId("duet-signal-offer-btn"));
  await waitFor(() => expect(mockPropose).toHaveBeenCalledTimes(1));
  expect(mockPropose.mock.calls[0][2]).toMatchObject({ count: 2, meaning: "all clear" });
  fireEvent.press(screen.getByTestId("duet-faint-toggle"));
  fireEvent.press(screen.getByTestId("duet-choice-A"));
  await waitFor(() => expect(mockDuetAction).toHaveBeenCalledTimes(1));
  expect(mockDuetAction.mock.calls[0][2].clarity).toBe("faint");
});

test("once the first lamp is lit the offer form is gone", async () => {
  mockGetDuet.mockResolvedValue({ duet: duet({ turn_count: 1, signal_window_open: false, signals: [] }) });
  render(<DuetPlay />);
  await screen.findByTestId("duet-your-turn");
  expect(screen.queryByTestId("duet-signals")).toBeNull();
});
