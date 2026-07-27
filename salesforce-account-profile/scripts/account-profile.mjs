#!/usr/bin/env node
import { CONTRACTS } from "./constants.mjs";
import { executeAdvancedPublic } from "./advanced-execution.mjs";
import { executeCertification } from "./certification.mjs";
import { executeConversational } from "./orchestrator.mjs";
import {
  readJsonInput,
  redactDeep,
  SafetyError,
  writeJsonOutput,
} from "./security.mjs";
import { execute } from "./workflow.mjs";

const CONVERSATIONAL_COMMANDS = new Set([
  "doctor",
  "start",
  "continue",
  "status",
  "abort",
]);
const ADVANCED_COMMANDS = new Set([
  "preflight",
  "resolve",
  "profile",
  "render",
]);
const CERTIFICATION_COMMANDS = new Set([
  "prepare-sandbox-certification",
  "certify-sandbox",
  "prepare-production-approval",
  "approve-production",
]);
const COMMANDS = new Set([
  ...CONVERSATIONAL_COMMANDS,
  ...ADVANCED_COMMANDS,
  ...CERTIFICATION_COMMANDS,
]);

export function parseArguments(argv) {
  const [command, ...rest] = argv;
  if (!COMMANDS.has(command)) {
    throw new SafetyError(
      "UNKNOWN_COMMAND",
      "Command must be doctor, start, continue, status, abort, preflight, resolve, profile, render, prepare-sandbox-certification, certify-sandbox, prepare-production-approval, or approve-production",
    );
  }
  let inputPath;
  let outputPath;
  for (let index = 0; index < rest.length; index += 2) {
    const flag = rest[index];
    const value = rest[index + 1];
    if (!value || !["--input", "--output"].includes(flag)) {
      throw new SafetyError("INVALID_ARGUMENTS", "Only --input <path> and --output <path> are accepted");
    }
    if (flag === "--input") inputPath = value;
    if (flag === "--output") outputPath = value;
  }
  return { command, inputPath, outputPath };
}

export async function main({
  argv = process.argv.slice(2),
  stdin = process.stdin,
  stdout = process.stdout,
  stderr = process.stderr,
  dependencies = {},
} = {}) {
  try {
    const { command, inputPath, outputPath } = parseArguments(argv);
    const input = await readJsonInput(inputPath, stdin);
    const result = CONVERSATIONAL_COMMANDS.has(command)
      ? await executeConversational(command, input, dependencies)
      : CERTIFICATION_COMMANDS.has(command)
        ? await executeCertification(command, input)
        : ADVANCED_COMMANDS.has(command)
          && ["resolve", "profile"].includes(command)
          ? await executeAdvancedPublic(command, input, dependencies)
          : await execute(command, input, dependencies);
    await writeJsonOutput(outputPath, result, stdout);
    return 0;
  } catch (error) {
    const safe = error instanceof SafetyError ? error : new SafetyError("INTERNAL_ERROR", "Unexpected internal failure");
    stderr.write(`${JSON.stringify(redactDeep({
      schema_version: CONTRACTS.error,
      error: { code: safe.code, message: safe.message },
    }))}\n`);
    return 2;
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  process.exitCode = await main();
}
