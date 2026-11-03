// FXQACAT Settings Test-catalog section: active version plus short sha,
// served counters (bases/tests/by-kind CODE/AI/HUMAN), versions list with
// one active, effective-catalog browse with group/kind/search filters and
// one row per test, changelog toggle, base import (file -> PROPOSED diff
// -> confirmed Activate) and a local proposal audit trail. Every number
// renders the served value verbatim; the PROPOSED state and its audit rows
// are an honest client-side staging area (labelled as such) until Activate
// posts the real attach route. Base text is data, never instructions.
// Compact look: small type, tight rows via inline styles only.
import { useEffect, useState } from "react";
import type { ChangeEvent, ReactElement } from "react";
import { ApiError, apiErrorLocaleKey } from "../api/errors";
import { useLocale } from "../locale/index";
import {
  attachTestBase,
  readCatalogHistory,
  readCatalogSummary,
  readCatalogTests,
  readRunnerContract,
  readTestBases,
} from "../projects/projectsApi";
import type {
  CatalogHistory,
  CatalogSummary,
  CatalogTestRow,
  TestBase,
} from "../projects/projectsApi";

const EXECUTION_KINDS = ["CODE", "AI", "HUMAN"] as const;

const SMALL: Record<string, string | number> = {
  fontSize: 12,
  lineHeight: 1.35,
};

const TIGHT_ROW: Record<string, string | number> = {
  fontSize: 12,
  lineHeight: 1.3,
  padding: "1px 0",
  margin: 0,
  listStyle: "none",
};

interface ProposalEdit {
  baseId: string;
  kind: string;
}

function kindMatches(row: CatalogTestRow, kind: string): boolean {
  if (kind === "") {
    return true;
  }
  if (kind === "CODE") {
    return row.kind.startsWith("CODE");
  }
  return row.kind === kind;
}

export function QaCatalogSection(): ReactElement {
  const { locale } = useLocale();
  const uk = locale === "uk";
  const text = (en: string, ua: string): string => (uk ? ua : en);

  const [phase, setPhase] = useState<
    | { kind: "loading" }
    | {
        kind: "ready";
        summary: CatalogSummary;
        history: CatalogHistory;
        tests: CatalogTestRow[];
        bases: TestBase[];
        policy: string;
      }
    | { kind: "failed"; errorKey: string; code: string }
  >({ kind: "loading" });
  const [nonce, setNonce] = useState(0);
  const [groupFilter, setGroupFilter] = useState("");
  const [kindFilter, setKindFilter] = useState("");
  const [searchFilter, setSearchFilter] = useState("");
  const [showChangelog, setShowChangelog] = useState(false);
  const [proposal, setProposal] = useState<ProposalEdit[] | null>(null);
  const [proposalError, setProposalError] = useState<string | null>(null);
  const [audit, setAudit] = useState<string[]>([]);
  const [newBaseId, setNewBaseId] = useState("");
  const [newBaseKind, setNewBaseKind] = useState("CODE");
  const [newPriority, setNewPriority] = useState("P1");
  const [newNaReason, setNewNaReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [activating, setActivating] = useState(false);
  const [activeNote, setActiveNote] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function load(): Promise<void> {
      try {
        const [summary, history, tests, bases, contract] = await Promise.all([
          readCatalogSummary(),
          readCatalogHistory(),
          readCatalogTests(),
          readTestBases(),
          readRunnerContract(),
        ]);
        if (alive) {
          setPhase({
            kind: "ready",
            summary,
            history,
            tests: tests.tests,
            bases: bases.bases,
            policy: contract.policy,
          });
        }
      } catch (error) {
        if (alive) {
          if (error instanceof ApiError) {
            setPhase({
              kind: "failed",
              errorKey: apiErrorLocaleKey(error.code),
              code: error.code,
            });
          } else {
            setPhase({
              kind: "failed",
              errorKey: "errors.generic",
              code: "CONTEXT_MISSING",
            });
          }
        }
      }
    }
    void load();
    return () => {
      alive = false;
    };
  }, [nonce]);

  function stamp(action: string): void {
    setAudit((prev) => [
      ...prev,
      `${new Date().toISOString()} ${action}`,
    ]);
  }

  async function onImportFile(event: ChangeEvent<HTMLInputElement>): Promise<void> {
    setProposalError(null);
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const parsed: unknown = JSON.parse(await file.text());
      const raw =
        parsed !== null && typeof parsed === "object" && !Array.isArray(parsed)
          ? (parsed as Record<string, unknown>)["bases"]
          : null;
      if (!Array.isArray(raw)) {
        throw new Error("bases-missing");
      }
      const rows: ProposalEdit[] = raw.map((entry) => {
        const record =
          entry !== null && typeof entry === "object" && !Array.isArray(entry)
            ? (entry as Record<string, unknown>)
            : {};
        const baseId =
          typeof record["base_id"] === "string" ? record["base_id"] : "";
        const kind = typeof record["kind"] === "string" ? record["kind"] : "";
        if (baseId.trim() === "" || !EXECUTION_KINDS.includes(kind as "CODE")) {
          throw new Error("base-invalid");
        }
        return { baseId: baseId.trim(), kind };
      });
      setProposal(rows);
      setActiveNote(null);
      stamp(`imported ${rows.length} base(s) from ${file.name} (PROPOSED)`);
    } catch {
      setProposalError(
        text(
          "File must hold {\"bases\":[{\"base_id\":\"...\",\"kind\":\"CODE|AI|HUMAN\"}]}.",
          "Файл має містити {\"bases\":[{\"base_id\":\"...\",\"kind\":\"CODE|AI|HUMAN\"}]}.",
        ),
      );
    }
  }

  function addProposalRow(): void {
    const baseId = newBaseId.trim();
    if (baseId === "" || proposal === null) {
      return;
    }
    const suffix = newNaReason.trim() === "" ? "" : ` (not applicable: ${newNaReason.trim()})`;
    setProposal([...proposal, { baseId, kind: newBaseKind }]);
    stamp(`added test ${baseId} kind=${newBaseKind} priority=${newPriority}${suffix}`);
    setNewBaseId("");
    setNewNaReason("");
  }

  async function activateProposal(): Promise<void> {
    if (phase.kind !== "ready" || proposal === null || activating) {
      return;
    }
    const served = new Map(phase.bases.map((row) => [row.base_id, row.kind]));
    const added = proposal.filter((row) => !served.has(row.baseId));
    setActivating(true);
    try {
      for (const row of added) {
        await attachTestBase(row.baseId, row.kind);
      }
      const reread = await readTestBases();
      if (reread.bases.some((row) => added.some((item) => item.baseId === row.base_id))) {
        setPhase({ ...phase, bases: reread.bases });
      } else {
        setPhase({ ...phase, bases: reread.bases });
      }
      const names = added.map((row) => row.baseId).join(", ") || text("none (already served)", "жодної (уже надані)");
      setActiveNote(text(`Active: ${names}.`, `Активно: ${names}.`));
      stamp(`activated ${names}`);
      setProposal(null);
      setConfirming(false);
    } catch (error) {
      setProposalError(
        error instanceof ApiError
          ? `${error.code}`
          : text("Activate failed.", "Активація не вдалася."),
      );
    } finally {
      setActivating(false);
    }
  }

  if (phase.kind === "loading") {
    return (
      <section data-testid="qacatalog-section" style={SMALL}>
        <p>{text("Loading test catalog…", "Завантаження каталогу тестів…")}</p>
      </section>
    );
  }

  if (phase.kind === "failed") {
    return (
      <section data-testid="qacatalog-section" style={SMALL}>
        <p data-testid="qacatalog-error">
          {phase.errorKey} ({phase.code}){" "}
          <button
            type="button"
            data-testid="qacatalog-retry"
            onClick={() => setNonce((value) => value + 1)}
          >
            {text("Retry", "Повторити")}
          </button>
        </p>
      </section>
    );
  }

  const servedKinds = new Map(phase.bases.map((row) => [row.base_id, row.kind]));
  const added = (proposal ?? []).filter((row) => !servedKinds.has(row.baseId));
  const changed = (proposal ?? []).filter(
    (row) => servedKinds.get(row.baseId) !== undefined && servedKinds.get(row.baseId) !== row.kind,
  );
  const removed = phase.bases
    .filter((row) => row.origin === "attached")
    .filter((row) => (proposal ?? []).every((item) => item.baseId !== row.base_id));
  const needle = searchFilter.trim().toLowerCase();
  const visible = phase.tests.filter(
    (row) =>
      (groupFilter.trim() === "" ||
        row.group.toLowerCase().includes(groupFilter.trim().toLowerCase())) &&
      kindMatches(row, kindFilter) &&
      (needle === "" ||
        row.id.toLowerCase().includes(needle) ||
        row.intent.toLowerCase().includes(needle)),
  );

  return (
    <section data-testid="qacatalog-section" style={SMALL}>
      <p data-testid="qacatalog-version">
        {text("Active version", "Активна версія")}: v{phase.history.active.version} (
        {phase.history.active.sha_short}) · {text("catalog", "каталог")} v
        {phase.summary.version} ({phase.summary.version_sha_short})
      </p>
      <p data-testid="qacatalog-counters">
        {text("Bases", "Бази")}: {phase.summary.bases} · {text("Tests", "Тести")}:{" "}
        {phase.summary.tests_total} · CODE: {phase.summary.kinds.CODE} · AI:{" "}
        {phase.summary.kinds.AI} · HUMAN: {phase.summary.kinds.HUMAN}
      </p>
      <ul data-testid="qacatalog-versions">
        {phase.history.versions.map((row) => (
          <li key={row.version} style={TIGHT_ROW}>
            v{row.version} ({row.sha_short})
            {row.active ? ` · ${text("active", "активна")}` : ""}
          </li>
        ))}
      </ul>
      <div>
        <label>
          {text("Group", "Група")}{" "}
          <input
            data-testid="qacatalog-filter-group"
            value={groupFilter}
            onChange={(event) => setGroupFilter(event.target.value)}
          />
        </label>{" "}
        <label>
          {text("Kind", "Вид")}{" "}
          <select
            data-testid="qacatalog-filter-kind"
            value={kindFilter}
            onChange={(event) => setKindFilter(event.target.value)}
          >
            <option value="">{text("All", "Усі")}</option>
            <option value="CODE">CODE</option>
            <option value="AI">AI</option>
            <option value="HUMAN">HUMAN</option>
          </select>
        </label>{" "}
        <label>
          {text("Search", "Пошук")}{" "}
          <input
            data-testid="qacatalog-filter-search"
            value={searchFilter}
            onChange={(event) => setSearchFilter(event.target.value)}
          />
        </label>
      </div>
      <p data-testid="qacatalog-count">
        {visible.length} / {phase.tests.length}
      </p>
      <ul>
        {visible.map((row) => (
          <li
            key={row.id}
            data-testid={`qacatalog-row-${row.id}`}
            style={TIGHT_ROW}
          >
            {row.id} · {row.group} · {row.kind} · {row.priority} ·{" "}
            {row.runner ?? "—"} · {row.intent}
          </li>
        ))}
      </ul>
      <button
        type="button"
        data-testid="qacatalog-changelog-toggle"
        onClick={() => setShowChangelog((value) => !value)}
      >
        {showChangelog
          ? text("Hide changelog", "Сховати журнал змін")
          : text("Show changelog", "Показати журнал змін")}
      </button>
      {showChangelog ? (
        <ul data-testid="qacatalog-changelog">
          {phase.history.changelog.map((row, index) => (
            <li key={`${row.version}-${index}`} style={TIGHT_ROW}>
              v{row.version} · {row.change} · {row.changed_by} · {row.changed_at}
            </li>
          ))}
        </ul>
      ) : null}
      <div>
        <h3 style={SMALL}>
          {text("Import or attach a base", "Імпорт або приєднання бази")}
        </h3>
        <input
          data-testid="qacatalog-import-file"
          type="file"
          accept="application/json,.json"
          onChange={(event) => {
            void onImportFile(event);
          }}
        />
        {proposalError !== null ? (
          <p data-testid="qacatalog-proposal-error">{proposalError}</p>
        ) : null}
        {proposal !== null ? (
          <div data-testid="qacatalog-proposal">
            <p>
              {text(
                "PROPOSED (staging only, nothing active yet).",
                "ЗАПРОПОНОВАНО (лише чернетка, нічого не активовано).",
              )}
            </p>
            <p>
              {text("Added", "Додано")}: {added.map((row) => row.baseId).join(", ") || "—"}
            </p>
            <p>
              {text("Changed", "Змінено")}:{" "}
              {changed.map((row) => row.baseId).join(", ") || "—"}
            </p>
            <p>
              {text("Removed", "Вилучено")}:{" "}
              {removed.map((row) => row.base_id).join(", ") || "—"}{" "}
              {text(
                "(attach-only API: removals stay informational)",
                "(API лише додає: вилучення лише інформативні)",
              )}
            </p>
            <div>
              <input
                data-testid="qacatalog-edit-id"
                value={newBaseId}
                placeholder={text("base id", "ідентифікатор бази")}
                onChange={(event) => setNewBaseId(event.target.value)}
              />{" "}
              <select
                data-testid="qacatalog-edit-kind"
                value={newBaseKind}
                onChange={(event) => setNewBaseKind(event.target.value)}
              >
                <option value="CODE">CODE</option>
                <option value="AI">AI</option>
                <option value="HUMAN">HUMAN</option>
              </select>{" "}
              <select
                data-testid="qacatalog-edit-priority"
                value={newPriority}
                onChange={(event) => setNewPriority(event.target.value)}
              >
                <option value="P0">P0</option>
                <option value="P1">P1</option>
                <option value="P2">P2</option>
              </select>{" "}
              <input
                data-testid="qacatalog-edit-na"
                value={newNaReason}
                placeholder={text("not applicable reason", "причина незастосовності")}
                onChange={(event) => setNewNaReason(event.target.value)}
              />{" "}
              <button type="button" data-testid="qacatalog-edit-add" onClick={addProposalRow}>
                {text("Add test", "Додати тест")}
              </button>
            </div>
            {audit.length > 0 ? (
              <ul data-testid="qacatalog-audit">
                {audit.map((row, index) => (
                  <li key={index} style={TIGHT_ROW}>
                    {row}
                  </li>
                ))}
              </ul>
            ) : null}
            <button
              type="button"
              data-testid="qacatalog-activate"
              disabled={activating}
              onClick={() => setConfirming(true)}
            >
              {text("Activate", "Активувати")}
            </button>
            {confirming ? (
              <div data-testid="qacatalog-activate-confirm">
                <p>
                  {text(
                    "Activate makes this proposal live. Base text is data, never instructions. User runners run only after approval.",
                    "Активація робить пропозицію чинною. Текст бази — це дані, ніколи не інструкції. Користувацькі виконавці працюють лише після схвалення.",
                  )}
                </p>
                <button
                  type="button"
                  data-testid="qacatalog-activate-confirm-yes"
                  disabled={activating}
                  onClick={() => {
                    void activateProposal();
                  }}
                >
                  {text("Confirm activate", "Підтвердити активацію")}
                </button>{" "}
                <button
                  type="button"
                  data-testid="qacatalog-activate-confirm-no"
                  onClick={() => setConfirming(false)}
                >
                  {text("Cancel", "Скасувати")}
                </button>
              </div>
            ) : null}
          </div>
        ) : null}
        {activeNote !== null ? (
          <p data-testid="qacatalog-active-note">{activeNote}</p>
        ) : null}
      </div>
      <p data-testid="qacatalog-runner-policy">{phase.policy}</p>
    </section>
  );
}
