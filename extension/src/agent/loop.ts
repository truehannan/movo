// The agent loop, running entirely in the side panel (no backend).
// observe -> Jev decide (operation + target) -> derive text -> safety -> act
// (stale-checked) -> verify -> repeat. Emits concise activity events.

import { DecisionEngine, type Decision, type Observation, type Operation } from "./engine";
import { PageDriver } from "./pageDriver";

export type AgentStatus =
  | "running" | "thinking" | "acting" | "waiting" | "confirming"
  | "success" | "blocked" | "error" | "stopped";

export interface ActivityEvent {
  kind: "status" | "observed" | "action" | "verified" | "message" | "confirm" | "completed";
  text: string;
  status?: AgentStatus;
  verified?: boolean;
  outcome?: string;
  operation?: string;
  target?: string;
}

export interface LoopOptions {
  goal: string;
  maxSteps?: number;
  onEvent: (e: ActivityEvent) => void;
  confirm: (description: string, reason: string) => Promise<boolean>;
}

const CONSEQUENTIAL = /\b(buy|purchase|place order|checkout|pay|subscribe|delete|remove|deactivate|close account|send|publish|post|submit|transfer|withdraw|approve)\b/i;

function describe(d: Decision): string {
  const bits: string[] = [d.operation];
  if (d.targetIndex != null) bits.push(`→ [${d.targetIndex}]`);
  if (d.text) bits.push(`"${d.text.length > 40 ? d.text.slice(0, 37) + "…" : d.text}"`);
  return bits.join(" ");
}

// Client-side text derivation for TYPE_TEXT (kept simple; no second model).
// Prefer a quoted phrase in the goal, else a "search/find X" tail, else the goal.
function deriveText(goal: string): string {
  const q = goal.match(/"([^"]+)"|'([^']+)'/);
  if (q) return q[1] || q[2];
  const m = goal.match(/(?:search(?:\s+for)?|find|look up|type|enter)\s+(.+)$/i);
  if (m) return m[1].replace(/\s+(and|then)\s+.*$/i, "").trim().replace(/[.?!]$/, "");
  return goal;
}

function isStale(before: Observation, fresh: Observation, index: number | null): boolean {
  if (before.fingerprint && fresh.fingerprint && before.fingerprint !== fresh.fingerprint) return true;
  if (index == null) return false;
  const b = before.elements.find((e) => e.index === index);
  const f = fresh.elements.find((e) => e.index === index);
  if (!b || !f) return true;
  const label = (e: { name: string; value: string | null }) => (e.name || e.value || "").trim();
  if (b.role !== f.role || label(b) !== label(f) || f.disabled) return true;
  return false;
}

function verifyStep(op: Operation, before: Observation, after: Observation, text: string | null): boolean {
  const changed = before.fingerprint !== after.fingerprint;
  if (op === "WAIT" || op === "SCROLL_UP" || op === "SCROLL_DOWN") return true;
  if (op === "TYPE_TEXT" && text) {
    if (after.elements.some((e) => e.can_type && e.value && e.value.includes(text.slice(0, 20)))) return true;
  }
  if (changed) return true;
  if (op === "CLICK" || op === "SELECT") return false;
  return true;
}

export class AgentLoop {
  private stopped = false;
  private controller = new AbortController();

  constructor(private engine: DecisionEngine, private driver: PageDriver) {}

  stop(): void {
    this.stopped = true;
    this.controller.abort();
  }

  async run(opts: LoopOptions): Promise<void> {
    const { goal, onEvent, confirm } = opts;
    const maxSteps = opts.maxSteps ?? 50;
    const recent: string[] = [];
    const emit = (e: ActivityEvent) => onEvent(e);
    emit({ kind: "status", status: "running", text: "Starting" });

    try {
      for (let step = 0; step < maxSteps; step++) {
        if (this.stopped) return emit({ kind: "completed", status: "stopped", text: "Stopped by user", outcome: "stopped" });

        emit({ kind: "status", status: "thinking", text: "Reading page" });
        const before = await this.driver.observe();
        emit({ kind: "observed", text: `${before.elements.length} interactive elements` });

        const decision = await this.engine.decide(goal, before, recent, this.controller.signal);
        if (decision.operation === "TYPE_TEXT" && decision.targetIndex != null) {
          decision.text = deriveText(goal);
        }
        const target = decision.targetIndex != null ? before.elements.find((e) => e.index === decision.targetIndex) : undefined;
        const targetLabel = (target?.name || target?.value || "").trim();
        emit({ kind: "action", text: describe(decision), operation: decision.operation, target: targetLabel || undefined });

        if (decision.operation === "DONE") {
          return emit({ kind: "completed", status: "success", text: "Task completed", outcome: "success" });
        }
        if (decision.operation === "BLOCKED") {
          return emit({ kind: "completed", status: "blocked", text: "No supported action can make progress", outcome: "blocked" });
        }

        // Safety: consequential actions require confirmation.
        if ((decision.operation === "CLICK") && CONSEQUENTIAL.test(targetLabel)) {
          emit({ kind: "confirm", status: "confirming", text: `Confirm: ${describe(decision)}` });
          const ok = await confirm(describe(decision), `Consequential control: "${targetLabel}"`);
          if (!ok) return emit({ kind: "completed", status: "blocked", text: "Declined by user", outcome: "blocked" });
        }
        if (this.stopped) return emit({ kind: "completed", status: "stopped", text: "Stopped by user", outcome: "stopped" });

        // Act (stale-checked for mutations).
        emit({ kind: "status", status: "acting", text: describe(decision) });
        let ok = false;
        if (decision.operation === "SCROLL_DOWN") ok = await this.driver.scroll(600);
        else if (decision.operation === "SCROLL_UP") ok = await this.driver.scroll(-600);
        else if (decision.operation === "WAIT") { await sleep(150); ok = true; }
        else {
          const fresh = await this.driver.observe();
          if (isStale(before, fresh, decision.targetIndex)) {
            emit({ kind: "message", text: "Page changed; re-observing" });
            continue;
          }
          if (decision.targetIndex != null) await this.driver.highlight(decision.targetIndex);
          if (decision.operation === "CLICK") ok = await this.driver.click(decision.targetIndex!);
          else if (decision.operation === "TYPE_TEXT") ok = decision.text ? await this.driver.type(decision.targetIndex!, decision.text) : false;
          else if (decision.operation === "SELECT") ok = await this.driver.select(decision.targetIndex!, 0);
        }
        if (!ok) {
          emit({ kind: "message", text: "Action did not apply" });
          continue;
        }

        await sleep(120);
        const after = await this.driver.observe();
        const verified = verifyStep(decision.operation, before, after, decision.text);
        emit({ kind: "verified", verified, text: verified ? "verified" : "no observable change" });
        recent.push(describe(decision));
        if (recent.length > 8) recent.shift();
      }
      emit({ kind: "completed", status: "blocked", text: "Max steps reached", outcome: "blocked" });
    } catch (e) {
      if (this.stopped) return;
      emit({ kind: "completed", status: "error", text: e instanceof Error ? e.message : String(e), outcome: "error" });
    }
  }
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}
