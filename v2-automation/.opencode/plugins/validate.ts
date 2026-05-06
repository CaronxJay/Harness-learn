import type { Plugin } from "@opencode-ai/plugin";

const PATTERN = /^knowledge\/articles\/.*\.json$/;

export const server: Plugin = async ({ $ }) => {
  return {
    "tool.execute.after": async (input) => {
      if (input.tool !== "write" && input.tool !== "edit") return;

      const filePath = input.args?.file_path || input.args?.filePath;
      if (!filePath || typeof filePath !== "string") return;
      if (!PATTERN.test(filePath)) return;

      try {
        await $.nothrow()`python3 hooks/validate_json.py ${filePath}`;
      } catch {
        // suppress unexpected shell errors to avoid blocking the agent
      }
    },
  };
};
