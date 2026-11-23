// A production NODE_ENV inherited from the shell removes React.act and breaks every render test.
process.env.NODE_ENV = "test";

module.exports = {
  preset: "jest-expo",
  testMatch: ["**/?(*.)+(test).[jt]s?(x)"],
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  transformIgnorePatterns: [
    "node_modules/(?!((jest-)?react-native|@react-native|react-native|expo(nent)?|@expo(nent)?/.*|@expo/.*|expo-router|@react-navigation/.*|@sentry/react-native|native-base|react-native-svg))",
  ],
};