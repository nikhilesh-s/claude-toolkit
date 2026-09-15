import {
  Action,
  ActionPanel,
  Alert,
  Clipboard,
  Color,
  confirmAlert,
  Detail,
  Form,
  Icon,
  popToRoot,
  showToast,
  Toast,
  useNavigation,
} from "@raycast/api";
import type { LaunchProps } from "@raycast/api";
import { useEffect, useRef, useState } from "react";
import { DESTINATIONS, destinationTitle, IntakeRecord, runCli } from "./cli";

type Draft = { url: string; destination: string; instruction: string };

// Deep link with a prefilled draft skips the form and runs straight away, e.g.
// raycast://extensions/nikhilesh-s/link-intake/intake-link?context={"url":"…","destination":"personal_ig","instruction":"…"}
export default function Command(props: LaunchProps<{ launchContext?: Partial<Draft> }>) {
  const ctx = props.launchContext;
  if (ctx?.url && ctx.destination && ctx.instruction) {
    return <Processing draft={{ url: ctx.url, destination: ctx.destination, instruction: ctx.instruction }} />;
  }
  return <IntakeForm />;
}

function IntakeForm(props: { draft?: Draft; reprocessId?: string }) {
  const { push } = useNavigation();
  const [url, setUrl] = useState(props.draft?.url ?? "");
  const [urlError, setUrlError] = useState<string | undefined>();
  const [instruction, setInstruction] = useState(props.draft?.instruction ?? "");

  useEffect(() => {
    if (props.draft?.url) return;
    Clipboard.readText().then((t) => {
      const s = (t ?? "").trim();
      if (/^https?:\/\/\S+$/i.test(s)) setUrl(s);
    });
  }, []);

  function submit(values: { url: string; destination: string; instruction: string }) {
    const u = values.url.trim();
    if (!/^https?:\/\/\S+$/i.test(u)) {
      setUrlError("Paste a full http(s) URL");
      return;
    }
    push(<Processing draft={{ url: u, destination: values.destination, instruction: values.instruction.trim() }} reprocessId={props.reprocessId} />);
  }

  return (
    <Form
      navigationTitle="Intake Link"
      actions={
        <ActionPanel>
          <Action.SubmitForm title="Process Link" icon={Icon.Bolt} onSubmit={submit} />
        </ActionPanel>
      }
    >
      <Form.TextField id="url" title="URL" placeholder="https://…" value={url} error={urlError} onChange={(v) => { setUrl(v); setUrlError(undefined); }} autoFocus={!url} />
      <Form.Dropdown id="destination" title="Destination" defaultValue={props.draft?.destination} storeValue={!props.draft}>
        {DESTINATIONS.map((d) => (
          <Form.Dropdown.Item key={d.value} value={d.value} title={d.title} />
        ))}
      </Form.Dropdown>
      <Form.TextArea id="instruction" title="What do you want extracted?" placeholder="I like the cinematic wide shots and pacing near the beginning." value={instruction} onChange={setInstruction} autoFocus={!!url} />
    </Form>
  );
}

function Processing({ draft, reprocessId }: { draft: Draft; reprocessId?: string }) {
  const { push, pop } = useNavigation();
  const [error, setError] = useState<string>();
  const started = useRef(false); // effects can fire twice; never spawn two extractions for one submit
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const args = reprocessId
      ? ["reprocess", reprocessId, "--dest", draft.destination, "--instruction", draft.instruction]
      : ["ingest", draft.url, "--dest", draft.destination, "--instruction", draft.instruction];
    runCli(args)
      .then((rec) => {
        pop();
        push(<Review rec={rec} />);
      })
      .catch((e) => setError(String(e.message ?? e)));
  }, []);
  const md = error
    ? `# Processing failed\n\n\`\`\`\n${error}\n\`\`\`\n\nCheck \`linkintake doctor\` in a terminal.`
    : `# Processing…\n\n**${destinationTitle(draft.destination)}** · ${draft.url}\n\n> ${draft.instruction}\n\nFetching source, building context, extracting what you asked for. Reels take ~20–60 s.`;
  return <Detail isLoading={!error} markdown={md} navigationTitle="Processing" />;
}

function statusTag(rec: IntakeRecord) {
  const map: Record<string, { color: Color; text: string }> = {
    ready: { color: Color.Green, text: "Ready" },
    needs_review: { color: Color.Orange, text: "Needs review" },
    failed: { color: Color.Red, text: "Failed" },
  };
  return map[rec.status] ?? { color: Color.SecondaryText, text: rec.status };
}

function fieldList(rec: IntakeRecord): [string, string][] {
  return Object.entries(rec.extraction.structured_data || {}).filter(([, v]) => v);
}

function Details({ rec }: { rec: IntakeRecord }) {
  const s = rec.source, e = rec.extraction, c = rec.context;
  const frames = rec.artifacts.frames?.length ? rec.artifacts.frames.map((f) => `${f.t || "?"} · ${f.file}`).join("  ·  ") : "";
  const md = [
    `## Full details`,
    e.focused_result || "_(no extraction)_",
    c.visual_notes ? `### Frame-by-frame visual notes\n${c.visual_notes}` : "",
    frames ? `### Sampled frames (approx. time)\n${frames}` : "",
    c.short_source_summary ? `### Source context\n${c.short_source_summary}` : "",
    c.caption_or_text ? `### Caption / page text\n${c.caption_or_text.slice(0, 3000)}` : "",
    c.transcript ? `### Transcript\n${c.transcript.slice(0, 4000)}` : "",
    `### Technical\n- record: \`${rec.id}\`\n- backend: ${rec.processing?.llm_backend || "—"}\n- adapter: ${rec.processing?.adapter || "—"}\n- job: ${rec.artifacts.media_unlocker_job_id || "—"}\n- canonical: ${s.canonical_url}`,
    rec.errors?.length ? `### Notes\n${rec.errors.map((x) => `- ${x}`).join("\n")}` : "",
  ]
    .filter(Boolean)
    .join("\n\n");
  return (
    <Detail
      navigationTitle="Details"
      markdown={md}
      actions={
        <ActionPanel>
          <Action.CopyToClipboard title="Copy Full Result" content={e.focused_result || ""} />
          <Action.OpenInBrowser title="Open Original URL" url={s.original_url} />
        </ActionPanel>
      }
    />
  );
}

function Review({ rec }: { rec: IntakeRecord }) {
  const { push } = useNavigation();
  const s = rec.source, e = rec.extraction, c = rec.context;
  const fields = fieldList(rec);
  const takeaways = e.takeaways?.length ? e.takeaways : [];
  const md = [
    `## ${s.title || s.original_url}`,
    s.creator ? `*${s.creator}* · ${s.platform}` : `*${s.platform}*`,
    rec.artifacts.contact_sheet ? `![preview](${rec.artifacts.contact_sheet})` : "",
    `> ${rec.intent.user_instruction}`,
    c.short_source_summary ? c.short_source_summary : "",
    takeaways.length ? `### Takeaways\n${takeaways.map((t) => `- ${t}`).join("\n")}` : `### Extracted\n${e.focused_result || "_(no extraction — see Details)_"}`,
    e.uncertainty ? `> ⚠️ ${e.uncertainty}` : "",
    rec.exact_duplicate ? `> ⚠️ A successful save already exists for this URL, destination and instruction (\`${rec.exact_duplicate}\`). Saving again needs confirmation.` : "",
    rec.duplicate_of?.length && !rec.exact_duplicate ? `_ℹ︎ Same source saved before with a different intent (${rec.duplicate_of.length}). That's expected._` : "",
    rec.status === "failed" && rec.errors?.length ? `### Errors\n${rec.errors.map((x) => `- ${x}`).join("\n")}` : "",
    `_Full details, frame notes and source text: ⌘⇧D_`,
  ]
    .filter(Boolean)
    .join("\n\n");
  const tag = statusTag(rec);

  async function save() {
    if (rec.exact_duplicate) {
      const ok = await confirmAlert({ title: "Save duplicate?", message: "Same URL + destination + instruction already exists.", primaryAction: { title: "Save Anyway", style: Alert.ActionStyle.Destructive } });
      if (!ok) return;
    }
    const toast = await showToast({ style: Toast.Style.Animated, title: "Saving…" });
    try {
      const saved = await runCli(["save", rec.id, ...(rec.exact_duplicate ? ["--force"] : [])]);
      const ex = saved.export ?? {};
      const exported = ex.status === "exported";
      toast.style = Toast.Style.Success;
      toast.title = exported ? "Saved and exported" : "Saved · export pending";
      toast.message = exported
        ? destinationTitle(rec.intent.destination)
        : `${destinationTitle(rec.intent.destination)} · Claude exports it to Drive later (linkintake exports)`;
      if (ex.destination?.url) toast.primaryAction = { title: "Copy Destination Link", onAction: () => Clipboard.copy(ex.destination!.url!) };
      await popToRoot({ clearSearchBar: true });
    } catch (err) {
      toast.style = Toast.Style.Failure;
      toast.title = "Save failed";
      toast.message = String((err as Error).message).slice(0, 200);
    }
  }

  const draft: Draft = { url: s.original_url, destination: rec.intent.destination, instruction: rec.intent.user_instruction };
  return (
    <Detail
      navigationTitle="Review"
      markdown={md}
      metadata={
        <Detail.Metadata>
          <Detail.Metadata.TagList title="Status">
            <Detail.Metadata.TagList.Item text={tag.text} color={tag.color} />
            <Detail.Metadata.TagList.Item text={`${Math.round((e.confidence || 0) * 100)}%`} />
          </Detail.Metadata.TagList>
          <Detail.Metadata.Label title="Destination" text={destinationTitle(rec.intent.destination)} />
          <Detail.Metadata.Label title="Source" text={`${s.platform} · ${s.source_class}`} />
          <Detail.Metadata.Link title="Original" target={s.original_url} text={s.original_url.replace(/^https?:\/\//, "").slice(0, 40)} />
          {fields.length ? <Detail.Metadata.Separator /> : null}
          {fields.slice(0, 8).map(([k, v]) => (
            <Detail.Metadata.Label key={k} title={k.replace(/_/g, " ")} text={v.length > 80 ? v.slice(0, 77) + "…" : v} />
          ))}
        </Detail.Metadata>
      }
      actions={
        <ActionPanel>
          <Action title="Save" icon={Icon.Check} onAction={save} />
          <Action title="Show Full Details" icon={Icon.Document} shortcut={{ modifiers: ["cmd", "shift"], key: "d" }} onAction={() => push(<Details rec={rec} />)} />
          <Action title="Edit Instruction" icon={Icon.Pencil} shortcut={{ modifiers: ["cmd"], key: "e" }} onAction={() => push(<IntakeForm draft={draft} reprocessId={rec.id} />)} />
          <Action title="Change Destination" icon={Icon.Folder} shortcut={{ modifiers: ["cmd"], key: "d" }} onAction={() => push(<IntakeForm draft={draft} reprocessId={rec.id} />)} />
          <Action title="Reprocess" icon={Icon.ArrowClockwise} shortcut={{ modifiers: ["cmd"], key: "r" }} onAction={() => push(<Processing draft={draft} reprocessId={rec.id} />)} />
          <Action.OpenInBrowser title="Open Original URL" url={s.original_url} shortcut={{ modifiers: ["cmd"], key: "o" }} />
          <Action.CopyToClipboard title="Copy Extracted Result" content={e.focused_result || ""} shortcut={{ modifiers: ["cmd", "shift"], key: "c" }} />
        </ActionPanel>
      }
    />
  );
}
