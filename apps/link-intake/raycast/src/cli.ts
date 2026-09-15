import { getPreferenceValues } from "@raycast/api";
import { execFile } from "node:child_process";
import { homedir } from "node:os";

export type SyncPart = { status: "pending" | "synced" | "failed"; destination?: string; remote_file_id: string; remote_ref: string; last_attempt: string; last_error: string; synced_at: string };
export type SyncState = { status: "synced" | "partial" | "export_pending" | "not_configured" | "off" | "needs_decision" | "skipped"; master_sync?: SyncPart; destination_sync?: SyncPart; last_error?: string; last_attempt?: string; synced_at?: string };

export type Resolution = { action?: string; entity_key?: string; matched_entity?: string; match_confidence?: number; match_reasons?: string[]; contributing_record_ids?: string[]; candidate_label?: string; variant_of?: string; enriched_fields?: string[] };

export function resolutionLine(res?: Resolution, dest?: string): string {
  const name = destinationTitle(dest ?? "");
  if (!res || !res.action || res.action === "n/a") return "";
  if (res.action === "merged") return `merged with existing ${name} item`;
  if (res.action === "possible_duplicate") return `possible ${name} duplicate — review needed`;
  if (res.action === "created" && res.variant_of) return `new variant of an existing ${name} item`;
  return "";
}

export function syncLine(ex?: SyncState, res?: Resolution, dest?: string): string {
  const st = ex?.status ?? "export_pending";
  const tail = resolutionLine(res, dest);
  const t = tail ? ` · ${tail}` : "";
  if (st === "needs_decision") return `Saved locally ✓ · ${tail || "possible duplicate — review needed"}`;
  if (st === "synced") return `Saved locally ✓ · Google synced ✓${t}`;
  if (st === "off") return `Saved locally ✓ · Google export off${t}`;
  if (st === "skipped") return `Saved locally ✓ · Google skipped${t}`;
  if (st === "not_configured") return `Saved locally ✓ · Google not authorized${t}`;
  if (st === "partial") {
    const m = ex?.master_sync?.status === "synced";
    return `Saved locally ✓ · Master ${m ? "synced ✓" : "pending"} · Destination ${m ? "pending" : "synced ✓"}${t}`;
  }
  return `Saved locally ✓ · Google pending${t}`;
}

export type HistoryRow = {
  id: string; title: string; creator: string; platform: string; url: string; destination: string; destination_title: string;
  instruction: string; created_at: string; saved_at: string; saved: boolean; status: string; confidence: number;
  export_status: string; sync_line: string; google_ref: string;
  master_status: string; destination_status: string; last_error: string; resolution: string; resolution_label: string;
};

export type IntakeRecord = {
  id: string;
  created_at: string;
  saved_at?: string;
  status: "ready" | "needs_review" | "failed";
  source: { original_url: string; canonical_url: string; source_class: string; platform: string; title: string; creator: string; published_at: string };
  intent: { destination: string; user_instruction: string };
  context: { short_source_summary: string; caption_or_text: string; transcript: string; visual_notes: string };
  extraction: { takeaways?: string[]; focused_result: string; uncertainty?: string; structured_data: Record<string, string>; confidence: number };
  artifacts: { contact_sheet: string; media_unlocker_job_id: string; frames?: { file: string; t: string }[] };
  processing: { llm_backend: string; adapter: string };
  export?: SyncState;
  destination_resolution?: Resolution;
  errors: string[];
  duplicate_of: string[];
  exact_duplicate?: string;
};

export const DESTINATIONS: { value: string; title: string }[] = [
  { value: "wishlist", title: "Wishlist" },
  { value: "supplement_ideas", title: "Supplement Ideas" },
  { value: "design_inspo", title: "Design Inspo" },
  { value: "scholarships", title: "Scholarships" },
  { value: "personal_ig", title: "Personal Instagram Inspiration" },
  { value: "inbox", title: "Inbox / Unsorted" },
];

export function destinationTitle(value: string): string {
  return DESTINATIONS.find((d) => d.value === value)?.title ?? value;
}

function cliPath(): string {
  const p = getPreferenceValues<{ cliPath?: string }>().cliPath?.trim();
  return (p && p.length > 0 ? p : "~/.local/bin/linkintake").replace(/^~/, homedir());
}

export function runCli<T = IntakeRecord>(args: string[], timeoutMs = 10 * 60 * 1000): Promise<T> {
  return new Promise((resolve, reject) => {
    execFile(
      cliPath(),
      ["--json", ...args],
      { timeout: timeoutMs, maxBuffer: 32 * 1024 * 1024, env: { ...process.env, PATH: `/opt/homebrew/bin:/usr/local/bin:${homedir()}/.local/bin:/usr/bin:/bin` } },
      (err, stdout, stderr) => {
        const text = (stdout || "").trim();
        try {
          const parsed = JSON.parse(text.split("\n").pop() || "{}");
          if (parsed && parsed.error) return reject(new Error(parsed.error));
          if (err && !text) return reject(new Error(stderr || err.message));
          return resolve(parsed as T);
        } catch {
          return reject(new Error((stderr || text || err?.message || "linkintake failed").slice(0, 500)));
        }
      },
    );
  });
}
