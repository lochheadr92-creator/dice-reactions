// https://docs.expo.dev/guides/using-eslint/
// eslint-config-expo/flat exports a config ARRAY; defineConfig flattens it so
// the array is not nested as a single (invalid) config object.
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*'],
  },
]);
