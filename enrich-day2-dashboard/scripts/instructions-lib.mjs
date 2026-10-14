// Shared helpers for the schema 1.10 field instructions: loading them, addressing a document with
// their JSON-Pointer wildcards, and asking "who may write this field?".
//
// The instructions JSON is the contract (llm.md says so too). Its `writePolicy` decides who may
// fill a field; this skill never second-guesses it with a hand-kept list.
import { readFileSync, existsSync } from "node:fs";
import path from "node:path";

const DEFAULT_BASE_URL = "https://agenticgtm.alpha.uipath.host/day2-v6/";

/** Load the field instructions: --instructions, else the dashboard repo's copy, else the deployed route. */
export async function loadInstructions({ instructions, repo, baseUrl } = {}) {
  if (instructions && !/^https?:/.test(instructions)) {
    return { json: JSON.parse(readFileSync(instructions, "utf8")), from: instructions };
  }
  if (!instructions && repo) {
    const p = path.join(repo, "src/data/day2-dashboard-field-instructions-v1.10.json");
    if (existsSync(p)) return { json: JSON.parse(readFileSync(p, "utf8")), from: p };
  }
  const root = (baseUrl ?? DEFAULT_BASE_URL).replace(/\/?$/, "/");
  const url = instructions ?? `${root}llm-guide/day2-dashboard-field-instructions-v1.10.json`;
  // The host's WAF rejects generic script user agents; a curl-style UA passes.
  const res = await fetch(url, { headers: { "User-Agent": "curl/8.7.1" } });
  if (!res.ok) throw new Error(`fetch ${url} -> ${res.status}`);
  return { json: await res.json(), from: url };
}

const unescapeSegment = (s) => s.replaceAll("~1", "/").replaceAll("~0", "~");

/** Expand an instruction pointer (with `*` array wildcards) to the document nodes it addresses. */
export function resolve(doc, pointer) {
  let nodes = [{ value: doc, at: "" }];
  if (pointer === "") return nodes;
  for (const raw of pointer.split("/").slice(1)) {
    const seg = unescapeSegment(raw);
    const next = [];
    for (const n of nodes) {
      if (n.value === undefined || n.value === null) continue;
      if (seg === "*") {
        if (Array.isArray(n.value)) n.value.forEach((v, i) => next.push({ value: v, at: `${n.at}/${i}` }));
      } else if (Array.isArray(n.value) && /^\d+$/.test(seg)) {
        // A concrete pointer such as /risks/2/severity addresses one array element.
        if (+seg < n.value.length) next.push({ value: n.value[+seg], at: `${n.at}/${seg}` });
      } else if (typeof n.value === "object" && !Array.isArray(n.value) && seg in n.value) {
        next.push({ value: n.value[seg], at: `${n.at}/${seg}` });
      }
    }
    nodes = next;
  }
  return nodes;
}

/** The descriptor for a concrete document pointer such as /risks/2/severity (numbers match `*`). */
export function descriptorFor(fields, concretePointer) {
  const generic = concretePointer.split("/").map((seg, i) => (i > 0 && /^\d+$/.test(seg) ? "*" : seg)).join("/");
  return { pointer: generic, spec: fields[generic] };
}

/**
 * Who may write a field, from the app's own `writePolicy` and `requirement`:
 *   evidence  -> the skill, from a dated source
 *   attest    -> the skill only on an explicit statement by a named person (never inferred)
 *   human     -> never the skill; the account team authors it (the report may offer a suggestion)
 *   skip      -> system-managed, preserve-only, constant or unused: leave exactly as found
 */
export function whoMayFill(spec, pointer = "") {
  if (!spec) return "skip";
  // `requirement: not_used` means "no publication requirement", not "never rendered". Three cases:
  //  - no tab reads the field: skip;
  //  - the UI edits it (`relationships`): fill it like any other field;
  //  - the slides draw it and the UI edits it, but its instructions allow only approved or verified legacy content
  //    (`goals`, `cadenceGoals`): a person approves the content, so the skill proposes it and never writes it unasked.
  if (spec.requirement === "not_used") {
    if (tabOf(pointer) === "No tab today") return "skip";
    if (spec.uiVisibility !== "editable") return ["evidence_required", "attestation_allowed"].includes(spec.writePolicy) ? "human" : "skip";
  }
  switch (spec.writePolicy) {
    case "evidence_required": return "evidence";
    case "attestation_allowed": return "attest";
    case "human_only": return "human";
    default: return "skip"; // system_managed, preserve_only, constant
  }
}

/** Which deck surface reads a top-level key (llm.md, "How your JSON becomes the deck"). */
const TAB_BY_TOP_KEY = {
  schemaVersion: "Cover", customerName: "Cover", reviewTier: "Cover", reviewAsOfDate: "Cover", dataClassification: "Cover",
  accountTeam: "Background", supportTier: "Background", renewalDate: "Background", deploymentType: "Background",
  bottomLineStatus: "Background", background: "Background", goals: "Background", risks: "Background",
  functionalNeeds: "Background", renewalEconomics: "Background",
  pipelineOpportunities: "Sales Plan", salesPlan: "Sales Plan",
  consumptionPlan: "Consumption Plan",
  cadenceGoals: "Stakeholders & Actions", stakeholdersActions: "Stakeholders & Actions",
  relationships: "Stakeholders & Actions", stakeholderGaps: "Stakeholders & Actions",
};
export function tabOf(pointer) {
  if (pointer === "/renewalEconomics/assurance") return "Consumption Plan"; // the Consumption Plan's assurance card
  const top = pointer.split("/")[1];
  return TAB_BY_TOP_KEY[top] ?? "No tab today";
}

/** True for a value that renders as a gap: "", null, or an empty array. `false` and 0 are values. */
export const isEmpty = (v) => v === "" || v === null || v === undefined || (Array.isArray(v) && v.length === 0);

/** A short human label for a record so a gap row can say which record it belongs to. */
export function recordLabel(record) {
  if (!record || typeof record !== "object") return "";
  for (const k of ["name", "risk", "customerName", "label", "need", "offering", "useCases", "element", "tier", "key"]) {
    if (typeof record[k] === "string" && record[k].trim()) return record[k].trim().slice(0, 48);
  }
  return "";
}
