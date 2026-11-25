import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

const jsxUsesVars = {
  meta: { type: "problem", schema: [] },
  create(context) {
    function markUsed(name, node) {
      context.sourceCode.markVariableAsUsed(name, node);
    }
    return {
      JSXOpeningElement(node) {
        const element = node.name;
        if (element.type === "JSXIdentifier" && /^[A-Z]/.test(element.name)) {
          markUsed(element.name, node); // <Button />
        } else if (element.type === "JSXMemberExpression") {
          let object = element.object;
          while (object.type === "JSXMemberExpression") object = object.object;
          markUsed(object.name, node); // <Dialog.Root />
        }
      },
    };
  },
};

export default [
  { ignores: ["dist/", "node_modules/"] },
  js.configs.recommended,
  reactHooks.configs.flat.recommended,
  jsxA11y.flatConfigs.recommended,
  {
    files: ["**/*.{js,jsx}"],
    plugins: { local: { rules: { "jsx-uses-vars": jsxUsesVars } } },
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser },
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      "local/jsx-uses-vars": "error",
      "no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["*.config.js"],
    languageOptions: { globals: { ...globals.node } },
  },
];
