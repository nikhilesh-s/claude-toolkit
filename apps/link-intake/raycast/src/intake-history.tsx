import { Action, ActionPanel, Color, Icon, List, showToast, Toast, useNavigation } from "@raycast/api";
import { useEffect, useState } from "react";
import { DESTINATIONS, HistoryRow, IntakeRecord, runCli } from "./cli";
import { Review } from "./intake-link";

function when(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function statusTag(r: HistoryRow): { text: string; color: Color } {
  if (!r.saved) return { text: "Not saved", color: Color.SecondaryText };
  if (r.export_status === "needs_decision") return { text: "Possible duplicate", color: Color.Yellow };
  if (r.export_status === "synced") return { text: "Saved ✓ Google ✓", color: Color.Green };
  if (r.export_status === "partial") return { text: r.master_status === "synced" ? "Master ✓ · dest pending" : "Master pending · dest ✓", color: Color.Orange };
  if (r.export_status === "off" || r.export_status === "skipped") return { text: "Saved ✓ local", color: Color.Green };
  return { text: "Saved ✓ · Google pending", color: Color.Orange };
}

function resolutionTag(r: HistoryRow): { text: string; color: Color } | null {
  if (r.resolution === "merged") return { text: "merged", color: Color.Blue };
  if (r.resolution === "possible_duplicate") return { text: "review", color: Color.Yellow };
  return null;
}

export default function History() {
  const [rows, setRows] = useState<HistoryRow[]>();
  const [error, setError] = useState<string>();
  const [dest, setDest] = useState("all");
  const { push } = useNavigation();
  async function retry(r: HistoryRow) {
    const toast = await showToast({ style: Toast.Style.Animated, title: "Retrying Google sync…" });
    try {
      const rec = await runCli<IntakeRecord>(["sync", r.id]);
      toast.style = rec.export?.status === "synced" ? Toast.Style.Success : Toast.Style.Failure;
      toast.title = rec.export?.status ?? "done";
      toast.message = rec.export?.last_error?.slice(0, 120) ?? "";
      load();
    } catch (e) {
      toast.style = Toast.Style.Failure;
      toast.title = "Retry failed";
      toast.message = String((e as Error).message).slice(0, 200);
    }
  }
  const load = () => runCli<HistoryRow[]>(["list", "--limit", "60"]).then(setRows).catch((e) => setError(String(e.message ?? e)));
  useEffect(() => {
    load();
  }, []);
  async function open(r: HistoryRow) {
    try {
      const rec = await runCli<IntakeRecord>(["show", r.id]);
      push(<Review rec={rec} />);
    } catch (e) {
      await showToast({ style: Toast.Style.Failure, title: "Could not load record", message: String((e as Error).message).slice(0, 200) });
    }
  }
  return (
    <List
      isLoading={!rows && !error}
      searchBarPlaceholder="Search history by title, URL, destination…"
      navigationTitle="Intake History"
      searchBarAccessory={
        <List.Dropdown tooltip="Destination" storeValue onChange={setDest}>
          <List.Dropdown.Item title="All destinations" value="all" />
          {DESTINATIONS.map((d) => (
            <List.Dropdown.Item key={d.value} title={d.title} value={d.value} />
          ))}
        </List.Dropdown>
      }
    >
      {error ? <List.EmptyView icon={Icon.Warning} title="History unavailable" description={error} /> : null}
      {rows?.length === 0 ? <List.EmptyView icon={Icon.Tray} title="Nothing yet" description="Saved and reviewed links will show up here." /> : null}
      {rows?.filter((r) => dest === "all" || r.destination === dest).map((r) => {
        const tag = statusTag(r);
        const rtag = resolutionTag(r);
        return (
          <List.Item
            key={r.id}
            icon={r.saved ? { source: Icon.CheckCircle, tintColor: tag.color } : Icon.Circle}
            title={r.title || r.url}
            subtitle={`${r.platform} · ${r.destination_title}${r.bulk_origin ? ` · bulk:${r.bulk_origin}${r.bulk_container ? "/" + r.bulk_container : ""}` : ""} · ${r.instruction.slice(0, 40)}${r.instruction.length > 40 ? "…" : ""}`}
            keywords={[r.url, r.destination_title, r.instruction, r.creator, r.id]}
            accessories={[
              ...(rtag ? [{ tag: { value: rtag.text, color: rtag.color }, tooltip: r.resolution_label || r.resolution }] : []),
              { tag: { value: tag.text, color: tag.color }, tooltip: r.last_error || r.sync_line },
              ...(r.saved && r.confidence ? [{ text: `${Math.round(r.confidence * 100)}%`, tooltip: "confidence" }] : []),
              { date: new Date(r.saved_at || r.created_at), tooltip: r.saved ? `saved ${when(r.saved_at)}` : `processed ${when(r.created_at)}` },
            ]}
            actions={
              <ActionPanel>
                <Action title="Open Saved Item" icon={Icon.Eye} onAction={() => open(r)} />
                <Action.OpenInBrowser title="Open Original URL" url={r.url} shortcut={{ modifiers: ["cmd"], key: "o" }} />
                <Action.CopyToClipboard title="Copy URL" content={r.url} shortcut={{ modifiers: ["cmd"], key: "c" }} />
                {r.google_ref ? <Action.OpenInBrowser title="Open in Google" url={r.google_ref} shortcut={{ modifiers: ["cmd"], key: "g" }} /> : null}
                {r.saved && ["export_pending", "partial", "not_configured"].includes(r.export_status) ? <Action title="Retry Google Sync" icon={Icon.Cloud} onAction={() => retry(r)} /> : null}
                {r.last_error ? <Action title="Show Sync Error" icon={Icon.Warning} onAction={() => showToast({ style: Toast.Style.Failure, title: r.export_status, message: r.last_error.slice(0, 250) })} /> : null}
                <Action title="Refresh" icon={Icon.ArrowClockwise} shortcut={{ modifiers: ["cmd"], key: "r" }} onAction={load} />
              </ActionPanel>
            }
          />
        );
      })}
    </List>
  );
}
