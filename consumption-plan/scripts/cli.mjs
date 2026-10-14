import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";

/**
 * True when the module at `moduleUrl` is the script node was asked to run.
 *
 * Comparing `import.meta.url` with `file://${process.argv[1]}` fails in two
 * ordinary cases -- a skill installed as a symlink (node resolves the module's
 * real path; argv keeps the link) and a path containing a space (the URL encodes
 * it) -- and either way the script ran and printed nothing.
 */
export function isMain(moduleUrl) {
  if (!process.argv[1]) return false;
  try {
    return realpathSync(process.argv[1]) === fileURLToPath(moduleUrl);
  } catch {
    return false;
  }
}
