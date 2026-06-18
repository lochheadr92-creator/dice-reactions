jest.mock("react-native-reanimated", () => require("react-native-reanimated/mock"));

jest.mock("react-native-safe-area-context", () => ({
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => {
    const mockReact = require("react");
    const { View } = require("react-native");
    return mockReact.createElement(View, { testID: "mock-safe-area-provider" }, children);
  },
  SafeAreaView: ({ children, ...props }: { children: React.ReactNode }) => {
    const mockReact = require("react");
    const { View } = require("react-native");
    return mockReact.createElement(View, props, children);
  },
  useSafeAreaInsets: () => ({ top: 0, right: 0, bottom: 0, left: 0 }),
}));

jest.mock("@expo/vector-icons", () => ({
  Ionicons: ({ name, ...props }: { name: string }) => {
    const mockReact = require("react");
    const { Text } = require("react-native");
    return mockReact.createElement(Text, props, name);
  },
}));