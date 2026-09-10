// Read-only Tribble Scribe reader, per the documented CE-repo method:
// snapshot db + -wal + -shm to a temp dir, open the snapshot read-only via
// node:sqlite, query, delete the snapshot. The live app is never touched.
import { DatabaseSync } from "node:sqlite";
import { copyFile, mkdtemp, rm } from "node:fs/promises";
import { tmpdir, homedir } from "node:os";
import { join } from "node:path";

const DB = join(homedir(), "Library/Application Support/Tribble Desktop/tribble.db");
const match = (process.argv[2] ?? "").toLowerCase();          // substring filter
const sinceMs = process.argv[3] ? Date.parse(process.argv[3]) : 0;
const wantTranscript = process.argv.includes("--transcript");

const dir = await mkdtemp(join(tmpdir(), "tribble-snapshot-"));
const snap = join(dir, "tribble.db");
await copyFile(DB, snap);
for (const s of ["-wal", "-shm"]) await copyFile(`${DB}${s}`, `${snap}${s}`).catch(() => {});
const db = new DatabaseSync(snap, { readOnly: true });
try {
  const rows = db.prepare(`
    SELECT m.id, m.title, m.date, m.start_at, m.platform, m.participants_json,
           d.content, d.summary_text, d.user_notes_content
    FROM meetings m JOIN meeting_details d ON d.meeting_id = m.id
    WHERE COALESCE(d.content, d.summary_text, '') <> ''
    ORDER BY m.date DESC`).all();
  const hits = rows.filter((r) => {
    let participants = [];
    try { participants = JSON.parse(r.participants_json ?? "[]"); } catch { /* skip */ }
    const hay = `${r.title ?? ""} ${JSON.stringify(participants)}`.toLowerCase();
    const ts = Date.parse(r.date ?? r.start_at ?? 0) || 0;
    return (!match || hay.includes(match)) && ts >= sinceMs;
  });
  for (const r of hits) {
    console.log(`\n===== MEETING ${r.id} | ${r.date} | ${r.title} | ${r.platform} =====`);
    try { console.log("PARTICIPANTS:", JSON.parse(r.participants_json ?? "[]").join(", ")); } catch { /* ignore */ }
    console.log((r.content || r.summary_text || "").slice(0, 12000));
    if (r.user_notes_content) console.log("USER NOTES:", r.user_notes_content.slice(0, 3000));
    if (wantTranscript) {
      const t = db.prepare("SELECT speaker, text FROM transcript_entries WHERE meeting_id = ? ORDER BY seq").all(r.id);
      console.log(`TRANSCRIPT (${t.length} rows, first 200):`);
      let last = "", buf = [];
      for (const e of t.slice(0, 200)) {
        if (e.speaker === last) buf[buf.length - 1] += " " + e.text;
        else { buf.push(`${e.speaker}: ${e.text}`); last = e.speaker; }
      }
      console.log(buf.join("\n").slice(0, 15000));
    }
  }
  console.log(`\n[${hits.length} matching meetings of ${rows.length} total]`);
} finally {
  db.close();
  await rm(dir, { recursive: true, force: true });
}
