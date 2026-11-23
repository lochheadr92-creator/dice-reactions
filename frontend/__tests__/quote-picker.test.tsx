import React from "react";
import { fireEvent, render, screen } from "@testing-library/react-native";
import QuotePicker from "../src/QuotePicker";

test("pins a repeated phrase at the selected occurrence or the whole paragraph", () => {
  const save = jest.fn();
  render(<QuotePicker paragraph="Red bell. Red bell." onClose={jest.fn()} onSave={save} />);
  fireEvent.press(screen.getByText("Pin whole paragraph"));
  expect(save).toHaveBeenCalledWith();
  fireEvent.press(screen.getAllByText("Red")[1]);
  fireEvent.press(screen.getAllByText("bell.")[1]);
  fireEvent.press(screen.getByText("Pin selected quote"));
  expect(save).toHaveBeenLastCalledWith("Red bell.", 1);
});
