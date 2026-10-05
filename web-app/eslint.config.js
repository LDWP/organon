import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      'max-lines': ['error', { max: 400, skipBlankLines: true, skipComments: true }],
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Use the helpers of src/api/client.js.' },
        { name: 'localStorage', message: 'Use src/shell/storagePreferences.js.' },
      ],
    },
  },
  {
    files: ['src/api/client.js', 'src/shell/storagePreferences.js'],
    rules: { 'no-restricted-globals': 'off' },
  },
])
