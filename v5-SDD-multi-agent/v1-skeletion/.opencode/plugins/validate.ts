import type { Plugin } from "@opencode-ai/plugin";

function resolveFilePath(args: unknown): string | null {
  if (args == null || typeof args !== "object") return null;
  const a = args as Record<string, unknown>;
  return (a.filePath ?? a.file_path ?? a.file ?? a.path) as string | null;
}

function isKnowledgeArticle(filePath: string | null): boolean {
  if (!filePath) return false;
  const normalized = filePath.replace(/\\/g, "/");
  return (
    normalized.startsWith("knowledge/articles/") &&
    normalized.endsWith(".json")
  );
}

const plugin: Plugin = async ({ $, directory }) => {
  return {
    "tool.execute.after": async (input) => {
      const { tool: toolName, args } = input;

      if (toolName !== "write" && toolName !== "edit") return;

      const filePath = resolveFilePath(args);
      if (!isKnowledgeArticle(filePath)) return;

      const absPath = `${directory}/${filePath}`;

      try {
        const result =
          await $`python3 ${VALIDATE_SCRIPT} ${absPath}`.cwd(directory).nothrow();

        if (result.exitCode !== 0) {
          const errText =
            result.stderr.toString().trim() ||
            result.stdout.toString().trim();
          console.error(
            `[validate] ${filePath} 校验失败 (exit ${result.exitCode})`,
          );
          if (errText) console.error(`[validate] ${errText}`);
          return;
        }

        const stdout = result.stdout.toString().trim();
        if (stdout) console.log(`[validate] ${filePath}\n${stdout}`);
      } catch (err) {
        console.error(`[validate] ${filePath} 脚本执行异常:`, err);
      }
    },
  };
};

const VALIDATE_SCRIPT = "hooks/validate_json.py";

export default plugin;
