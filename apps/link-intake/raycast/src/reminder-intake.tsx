import { Action, ActionPanel, Alert, Color, confirmAlert, Detail, Icon, launchCommand, LaunchType, List, showToast, Toast, useNavigation } from "@raycast/api";
import { useEffect, useState } from "react";
import { DESTINATIONS, IntakeRecord, runCli } from "./cli";
import { Review } from "./intake-link";

// Thin view over `linkintake reminders …`. All sweep, report and clearing logic lives in the CLI.
type Item = {
  id: string; outcome: string; list: string; title: string; text: string; url: string; destination: string; destination_title: string;
  destination_confidence: number; instruction: string; reason: string; next_action: string; record_id: string; resolution: string; export_status: string;
};
type Rem = { reminder_id: string; list: string; title: string; links: { url: string; outcome: string; record_id: string }[]; eligible_to_clear: boolean; why_not: string; why?: string };
type Report = {
  run_id: string; started: string; finished: string; scheduled: boolean; status: string; error: string; markdown: string;
  counts: Record<string, number | Record<string, number>>; items: Item[]; attention: Item[];
  reconciliation: { summary: Record<string, number>; reminders: Rem[]; confirmation: string }; clear_decision: { action: string };
};
type ClearPreview = { run_id: string; will_complete: Rem[]; untouched: Rem[]; token: string };

const COLORS: Record<string, Color> = {
  AUTO_INGESTED: Color.Green, ALREADY_INGESTED: Color.Blue, REVIEW: Color.Yellow, DEFERRED: Color.Orange, QUEUED: Color.Orange,
  FAILED: Color.Red, SKIPPED_UNSUPPORTED: Color.SecondaryText, WOULD_INGEST: Color.Green,
};

async function step(title: string, args: string[], done: (r: unknown) => string) {
  const toast = await showToast({ style: Toast.Style.Animated, title });
  try {
    const r = await runCli<unknown>(args, 15 * 60 * 1000);
    toast.style = Toast.Style.Success;
    toast.title = done(r);
    return r;
  } catch (e) {
    toast.style = Toast.Style.Failure;
    toast.title = `${title.replace(/…$/, "")} failed`;
    toast.message = String((e as Error).message).slice(0, 200);
  }
}

function SweepActions({ reload }: { reload: () => void }) {
  const { push } = useNavigation();
  return (
    <ActionPanel.Section title="Reminder Sweep">
      <Action title="Run Reminder Sweep Now" icon={Icon.Play} onAction={() => step("Starting sweep…", ["reminders", "run", "--execute", "--background"], () => "Sweep started · report appears here when done").then(reload)} />
      <Action title="Preview Sweep" icon={Icon.Eye} onAction={() => push(<Preview />)} />
      <Action title="Review Sweep" icon={Icon.Document} shortcut={{ modifiers: ["cmd"], key: "d" }} onAction={() => push(<ReportDetail reload={reload} />)} />
      <Action title="Review Ambiguous" icon={Icon.QuestionMarkCircle} onAction={() => push(<Ambiguous reload={reload} />)} />
      <Action title="Retry Deferred" icon={Icon.ArrowClockwise} onAction={() => step("Retrying deferred…", ["reminders", "retry-deferred", "--background"], () => "Retry started").then(reload)} />
      <Action title="Clear Processed Reminders" icon={Icon.CheckCircle} onAction={() => push(<Clear reload={reload} />)} />
      <Action title="Keep Everything" icon={Icon.Lock} onAction={() => step("Keeping all reminders…", ["reminders", "clear", "--keep"], () => "Kept · no reminder changed").then(reload)} />
      <Action title="Open Intake History" icon={Icon.List} onAction={() => launchCommand({ name: "intake-history", type: LaunchType.UserInitiated })} />
      <Action title="Schedule Status" icon={Icon.Clock} onAction={() => push(<ScheduleStatus />)} />
      <Action title="Refresh" icon={Icon.RotateClockwise} shortcut={{ modifiers: ["cmd"], key: "r" }} onAction={reload} />
    </ActionPanel.Section>
  );
}

function ItemActions({ i, reload }: { i: Item; reload: () => void }) {
  const { push } = useNavigation();
  async function view() {
    try {
      push(<Review rec={await runCli<IntakeRecord>(["show", i.record_id])} />);
    } catch (e) {
      await showToast({ style: Toast.Style.Failure, title: "Could not load record", message: String((e as Error).message).slice(0, 200) });
    }
  }
  return (
    <>
      {i.record_id ? <Action title="View Saved Intake" icon={Icon.Eye} onAction={view} /> : null}
      {i.url ? <Action.OpenInBrowser title="Open Source URL" url={i.url} shortcut={{ modifiers: ["cmd"], key: "o" }} /> : null}
      {i.outcome === "REVIEW" && i.resolution !== "possible_duplicate" ? <ReviewActions i={i} reload={reload} /> : null}
    </>
  );
}

function ReviewActions({ i, reload }: { i: Item; reload: () => void }) {
  return (
    <ActionPanel.Section title="Decide">
      {i.destination !== "inbox" ? (
        <Action title={`Approve as ${i.destination_title}`} icon={Icon.Check} onAction={() => step("Ingesting…", ["reminders", "review", "--approve", i.id, "--execute"], () => "Ingested").then(reload)} />
      ) : null}
      <ActionPanel.Submenu title="Ingest As…" icon={Icon.ArrowRight}>
        {DESTINATIONS.map((d) => (
          <Action key={d.value} title={d.title} onAction={() => step("Ingesting…", ["reminders", "review", "--dest", i.id, d.value, "--execute"], () => `Ingested → ${d.title}`).then(reload)} />
        ))}
      </ActionPanel.Submenu>
      <Action title="Skip" icon={Icon.XMarkCircle} onAction={() => step("Skipping…", ["reminders", "review", "--skip", i.id], () => "Skipped · reminder left untouched").then(reload)} />
    </ActionPanel.Section>
  );
}

function ItemRow({ i, reload }: { i: Item; reload: () => void }) {
  return (
    <List.Item
      title={i.title || i.url}
      subtitle={`${i.list} · ${i.destination_title}`}
      keywords={[i.url, i.list, i.reason]}
      accessories={[{ tag: { value: i.outcome.replace("_", " "), color: COLORS[i.outcome] }, tooltip: `${i.reason}\n${i.next_action}` }]}
      actions={
        <ActionPanel>
          <ItemActions i={i} reload={reload} />
          <SweepActions reload={reload} />
        </ActionPanel>
      }
    />
  );
}

export default function ReminderIntake() {
  const [rep, setRep] = useState<Report>();
  const [error, setError] = useState<string>();
  const load = () => runCli<Report>(["reminders", "report"]).then((r) => (setRep(r), setError(undefined))).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
  }, []);
  const s = rep?.reconciliation.summary;
  const c = rep?.counts;
  const saved = rep?.items.filter((i) => i.outcome === "AUTO_INGESTED" || i.outcome === "ALREADY_INGESTED") ?? [];
  return (
    <List isLoading={!rep && !error} navigationTitle="Reminder Intake" searchBarPlaceholder="Filter this sweep…">
      {error ? (
        <List.EmptyView icon={Icon.Tray} title={error.includes("no Reminder sweep") ? "No sweep yet" : "Report unavailable"} description={error}
          actions={<ActionPanel><SweepActions reload={load} /></ActionPanel>} />
      ) : null}
      {rep && s && c ? (
        <List.Section title={`Latest sweep · ${new Date(rep.finished).toLocaleString()}${rep.scheduled ? " · scheduled" : ""}`}>
          <List.Item
            icon={rep.status === "ok" ? { source: Icon.CheckCircle, tintColor: Color.Green } : { source: Icon.Warning, tintColor: Color.Red }}
            title={rep.error || `${c.new_candidates} new · ${c.auto_ingested} saved · ${c.already_ingested} known · ${c.needs_review} review · ${c.deferred} deferred`}
            subtitle={`${s.reminders_found} URL reminders · ${s.eligible_to_clear} eligible to clear · ${s.remain_untouched} stay`}
            accessories={[{ tag: { value: `clear: ${rep.clear_decision?.action ?? "pending"}` } }]}
            actions={<ActionPanel><SweepActions reload={load} /></ActionPanel>}
          />
        </List.Section>
      ) : null}
      {rep?.attention.length ? (
        <List.Section title="Needs attention">{rep.attention.map((i) => <ItemRow key={i.id} i={i} reload={load} />)}</List.Section>
      ) : null}
      {saved.length ? <List.Section title="Saved this sweep">{saved.map((i) => <ItemRow key={i.id} i={i} reload={load} />)}</List.Section> : null}
    </List>
  );
}

function ReportDetail({ reload }: { reload: () => void }) {
  const [md, setMd] = useState<string>();
  useEffect(() => {
    runCli<Report>(["reminders", "report"]).then((r) => setMd(r.markdown)).catch((e) => setMd(`**Report unavailable**\n\n${e.message}`));
  }, []);
  return <Detail isLoading={!md} markdown={md ?? ""} actions={<ActionPanel><SweepActions reload={reload} /></ActionPanel>} />;
}

function Preview() {
  const [pv, setPv] = useState<{ would_process: Item[]; new: Item[]; urls_discovered: number; previously_accounted: number; over_cap: number }>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    runCli<typeof pv>(["reminders", "run"], 5 * 60 * 1000).then(setPv).catch((e) => setError(String(e.message ?? e)));
  }, []);
  const rows = pv ? [...pv.new.filter((i) => i.outcome !== "QUEUED"), ...pv.would_process.map((i) => ({ ...i, outcome: i.outcome === "QUEUED" ? "WOULD_INGEST" : i.outcome }))] : [];
  return (
    <List isLoading={!pv && !error} navigationTitle="Preview Sweep (dry run: nothing changes)">
      {error ? <List.EmptyView icon={Icon.Warning} title="Preview failed" description={error} /> : null}
      {pv ? (
        <List.Section title={`${pv.urls_discovered} URLs · ${pv.previously_accounted} already accounted for${pv.over_cap ? ` · ${pv.over_cap} over the per-run cap` : ""}`}>
          {rows.map((i) => (
            <List.Item key={i.id + i.outcome} title={i.title || i.url} subtitle={`${i.list} · ${i.destination_title}`}
              accessories={[{ tag: { value: i.outcome.replace("_", " "), color: COLORS[i.outcome] }, tooltip: i.reason }]}
              actions={<ActionPanel><Action.OpenInBrowser title="Open Source URL" url={i.url} /></ActionPanel>} />
          ))}
        </List.Section>
      ) : null}
    </List>
  );
}

function Ambiguous({ reload }: { reload: () => void }) {
  const [rows, setRows] = useState<Item[]>();
  const [error, setError] = useState<string>();
  const load = () => runCli<Item[]>(["reminders", "review"]).then(setRows).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
  }, []);
  const both = () => (load(), reload());
  return (
    <List isLoading={!rows && !error} navigationTitle="Review Ambiguous">
      {error ? <List.EmptyView icon={Icon.Warning} title="Review unavailable" description={error} /> : null}
      {rows?.length === 0 ? <List.EmptyView icon={Icon.CheckCircle} title="Nothing to review" /> : null}
      {rows?.map((i) => <ItemRow key={i.id} i={i} reload={both} />)}
    </List>
  );
}

function Clear({ reload }: { reload: () => void }) {
  const { pop } = useNavigation();
  const [pv, setPv] = useState<ClearPreview>();
  const [error, setError] = useState<string>();
  useEffect(() => {
    runCli<ClearPreview>(["reminders", "clear"]).then(setPv).catch((e) => setError(String(e.message ?? e)));
  }, []);
  const line = (r: Rem, why = "") => `- **[${r.list}]** ${r.title || "(no title)"}${why ? ` — _${why}_` : ` — ${r.links.length} link(s)`}`;
  const md = error
    ? `**Clear preview failed**\n\n${error}`
    : pv
      ? [`# Clear Processed Reminders`, `Preview only — nothing has changed. Eligible reminders are **marked complete, never deleted**.`,
         `## ${pv.will_complete.length} will be marked complete`, pv.will_complete.map((r) => line(r)).join("\n") || "_none_",
         `## ${pv.untouched.length} will remain untouched`, pv.untouched.map((r) => line(r, r.why || r.why_not)).join("\n") || "_none_"].join("\n\n")
      : "";
  async function confirm() {
    if (!pv?.token) return;
    const ok = await confirmAlert({
      title: `Mark ${pv.will_complete.length} reminders complete?`,
      message: "Only reminders whose links were all ingested or already known. Nothing is deleted. Review, deferred and failed reminders stay untouched.",
      primaryAction: { title: "Mark Complete", style: Alert.ActionStyle.Destructive },
    });
    if (!ok) return;
    const r = (await step("Marking complete…", ["reminders", "clear", "--confirm", pv.token], (x) => `Marked ${(x as { completed: unknown[] }).completed.length} complete`)) as unknown;
    if (r) (reload(), pop());
  }
  return (
    <Detail isLoading={!pv && !error} markdown={md}
      actions={
        <ActionPanel>
          {pv?.token ? <Action title={`Mark ${pv.will_complete.length} Reminders Complete`} icon={Icon.CheckCircle} onAction={confirm} /> : null}
          <Action title="Keep Everything" icon={Icon.Lock} onAction={() => step("Keeping all reminders…", ["reminders", "clear", "--keep"], () => "Kept · no reminder changed").then(() => (reload(), pop()))} />
        </ActionPanel>
      }
    />
  );
}

function ScheduleStatus() {
  const [st, setSt] = useState<Record<string, unknown>>();
  useEffect(() => {
    runCli<Record<string, unknown>>(["reminders", "schedule", "status"]).then(setSt).catch((e) => setSt({ error: String(e.message ?? e) }));
  }, []);
  const md = st ? ["# Weekly Reminder Sweep", ...Object.entries(st).map(([k, v]) => `- **${k}**: \`${typeof v === "string" ? v : JSON.stringify(v)}\``),
    "", "Install or change it from a terminal (never automatic): `linkintake reminders schedule install --weekday sun --time 19:00`"].join("\n") : "";
  return <Detail isLoading={!st} markdown={md} />;
}
