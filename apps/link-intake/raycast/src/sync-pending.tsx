import { closeMainWindow, showToast, Toast } from "@raycast/api";
import { runCli } from "./cli";

export default async function Command() {
  await closeMainWindow({ clearRootSearch: true });
  const toast = await showToast({ style: Toast.Style.Animated, title: "Syncing pending Link Intake records…" });
  try {
    const res = await runCli<{ synced: { id: string }[]; still_pending: { id: string; error: string }[]; remaining: number }>(["sync", "--limit", "10", "--budget", "60"]);
    toast.style = res.still_pending.length ? Toast.Style.Failure : Toast.Style.Success;
    toast.title = `Synced ${res.synced.length} · still pending ${res.remaining}`;
    toast.message = res.still_pending[0]?.error?.slice(0, 120) ?? "";
  } catch (e) {
    toast.style = Toast.Style.Failure;
    toast.title = "Sync failed";
    toast.message = String((e as Error).message).slice(0, 200);
  }
}
