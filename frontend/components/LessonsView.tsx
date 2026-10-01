"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  approveLesson,
  listLessons,
  proposeLessons,
  rejectLesson,
  retireLesson,
  type Lesson,
} from "@/lib/api";

function targetLabel(target: string): string {
  return target.replace(/_/g, " ");
}

export default function LessonsView() {
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ id: string; text: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLessons(await listLessons());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load lessons.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function run(action: () => Promise<unknown>, done?: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await action();
      if (done) setMessage(done);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "That did not work. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function findNew() {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const result = await proposeLessons();
      setMessage(
        result.count === 0
          ? "No new patterns yet. Lessons need at least 3 similar corrections."
          : `${result.count} new lesson${result.count === 1 ? "" : "s"} proposed. Nothing changes until you approve it.`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not look for lessons.");
    } finally {
      setBusy(false);
    }
  }

  const proposed = lessons.filter((l) => l.status === "proposed");
  const approved = lessons.filter((l) => l.status === "approved");
  const closed = lessons.filter((l) => l.status === "rejected" || l.status === "retired");

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto px-6 py-6 lg:px-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold">Lessons</h2>
          <p className="mt-1 max-w-2xl text-sm text-hap-muted">
            What HAP has learned from your corrections. HAP proposes a lesson when you correct the same kind of
            decision several times. A lesson only takes effect after you approve it, and approved lessons guide the
            analyst chat. They never change scores, rules or workbook numbers.
          </p>
        </div>
        <button
          onClick={() => void findNew()}
          disabled={busy}
          className="rounded-md bg-hap-orange px-4 py-2 text-sm font-semibold text-black disabled:opacity-50"
        >
          Look for new lessons
        </button>
      </div>

      {message && <p className="mb-4 rounded-md border border-hap-border px-3 py-2 text-sm text-hap-muted">{message}</p>}
      {error && (
        <p role="alert" className="mb-4 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {error}
        </p>
      )}
      {loading && <p className="text-sm text-hap-muted">Loading…</p>}

      {!loading && lessons.length === 0 && (
        <p className="rounded-md border border-hap-border px-4 py-6 text-center text-sm text-hap-muted">
          No lessons yet. Keep reviewing analyses and rating chat answers; once you have corrected the same kind of
          decision a few times, press &quot;Look for new lessons&quot;.
        </p>
      )}

      {proposed.length > 0 && (
        <section className="mb-8">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-hap-orange">
            Waiting for your decision ({proposed.length})
          </h3>
          <div className="space-y-3">
            {proposed.map((lesson) => (
              <article key={lesson.id} className="rounded-lg border border-hap-border bg-hap-panel p-4">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-hap-muted">
                  <span className="rounded bg-hap-panel-elevated px-2 py-0.5">{targetLabel(lesson.target)}</span>
                  <span>{lesson.analysis_type.replace(/_/g, " ")}</span>
                  <span>based on {lesson.support_count} cases</span>
                </div>
                <h4 className="mt-2 text-sm font-semibold">{lesson.title}</h4>
                {editing?.id === lesson.id ? (
                  <textarea
                    value={editing.text}
                    onChange={(event) => setEditing({ id: lesson.id, text: event.target.value })}
                    rows={5}
                    maxLength={1200}
                    className="mt-2 w-full resize-y rounded-md border border-hap-border bg-hap-panel-elevated px-3 py-2 text-sm outline-none focus:border-hap-orange"
                  />
                ) : (
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{lesson.text}</p>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    disabled={busy}
                    onClick={() =>
                      void run(
                        () => approveLesson(lesson.id, editing?.id === lesson.id ? { text: editing.text } : undefined),
                        "Lesson approved. The analyst chat will use it from now on.",
                      ).then(() => setEditing(null))
                    }
                    className="rounded-md bg-hap-orange px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-50"
                  >
                    {editing?.id === lesson.id ? "Approve edited lesson" : "Approve"}
                  </button>
                  {editing?.id === lesson.id ? (
                    <button onClick={() => setEditing(null)} className="px-3 py-1.5 text-xs text-hap-muted hover:text-foreground">
                      Cancel edit
                    </button>
                  ) : (
                    <button
                      onClick={() => setEditing({ id: lesson.id, text: lesson.text })}
                      className="rounded-md border border-hap-border px-3 py-1.5 text-xs text-hap-muted hover:text-foreground"
                    >
                      Edit wording
                    </button>
                  )}
                  <button
                    disabled={busy}
                    onClick={() => void run(() => rejectLesson(lesson.id), "Lesson rejected. HAP will not propose it again.")}
                    className="rounded-md border border-hap-border px-3 py-1.5 text-xs text-hap-muted hover:text-red-300 disabled:opacity-50"
                  >
                    Reject
                  </button>
                </div>
              </article>
            ))}
          </div>
        </section>
      )}

      {approved.length > 0 && (
        <section className="mb-8">
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-hap-success">
            Active lessons ({approved.length})
          </h3>
          <div className="space-y-3">
            {approved.map((lesson) => (
              <article key={lesson.id} className="rounded-lg border border-hap-border bg-hap-panel p-4">
                <div className="flex flex-wrap items-center gap-2 text-[11px] text-hap-muted">
                  <span className="rounded bg-hap-panel-elevated px-2 py-0.5">{targetLabel(lesson.target)}</span>
                  <span>{lesson.analysis_type.replace(/_/g, " ")}</span>
                  {lesson.decided_at && <span>approved {lesson.decided_at.slice(0, 10)}</span>}
                </div>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">{lesson.text}</p>
                <button
                  disabled={busy}
                  onClick={() => void run(() => retireLesson(lesson.id), "Lesson retired.")}
                  className="mt-3 rounded-md border border-hap-border px-3 py-1.5 text-xs text-hap-muted hover:text-foreground disabled:opacity-50"
                >
                  Retire
                </button>
              </article>
            ))}
          </div>
        </section>
      )}

      {closed.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-hap-muted">
            Rejected or retired ({closed.length})
          </h3>
          <ul className="space-y-1 text-xs text-hap-muted">
            {closed.map((lesson) => (
              <li key={lesson.id}>
                [{lesson.status}] {lesson.title} ({targetLabel(lesson.target)})
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
