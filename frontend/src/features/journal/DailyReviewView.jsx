import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { today } from "./journalUtils";

function newReview() {
  return {
    review_date: today(), account: "Main", focus_goal: "", market_condition: "",
    emotional_state: "", process: "", pair: "", session: "", setups: "",
    learnings: "", psychology: "", mistakes: "", did_well: "", improve: "",
    actionable_steps: "", thoughts: "",
  };
}

export default function DailyReviewView() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState(() => newReview());
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  async function load() {
    setError("");
    try {
      const response = await api.dailyReviews();
      setItems(Array.isArray(response?.items) ? response.items : []);
    } catch (err) {
      setError(err.message || "Could not load daily reviews.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, []);

  async function save(event) {
    event.preventDefault();
    setSaving(true); setError(""); setMessage("");
    try {
      const saved = await api.saveDailyReview(form);
      setForm((current) => ({ ...current, ...saved }));
      setMessage(`Saved review for ${saved.review_date}.`);
      await load();
    } catch (err) {
      setError(err.message || "Could not save daily review.");
    } finally {
      setSaving(false);
    }
  }

  function choose(item) {
    setForm({ ...newReview(), ...item });
    setMessage(""); setError("");
  }

  function reset() {
    setForm(newReview());
    setMessage(""); setError("");
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
      <form onSubmit={save} className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-xl font-semibold">Daily review</h3>
            <p className="mt-1 text-sm text-stone-500">Review the session, process, psychology and what you want to improve next time.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <input type="date" className="input w-40" value={form.review_date || ""} onChange={(e) => setForm({ ...form, review_date: e.target.value })} />
            <input className="input w-36" value={form.account || ""} onChange={(e) => setForm({ ...form, account: e.target.value })} placeholder="Account" />
            <button type="button" onClick={reset} className="rounded-md border border-stone-300 px-3 py-2 text-sm">New</button>
          </div>
        </div>

        {message && <p className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">{message}</p>}
        {error && <p className="mt-3 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">{error}</p>}

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <Field label="Today's focus and goal"><textarea rows="3" className="input resize-y" value={form.focus_goal || ""} onChange={(e) => setForm({ ...form, focus_goal: e.target.value })} /></Field>
          <Field label="Market condition"><input className="input" value={form.market_condition || ""} onChange={(e) => setForm({ ...form, market_condition: e.target.value })} placeholder="Trending / ranging / countertrend…" /></Field>
          <Field label="Emotional state"><input className="input" value={form.emotional_state || ""} onChange={(e) => setForm({ ...form, emotional_state: e.target.value })} /></Field>
          <Field label="Process"><input className="input" value={form.process || ""} onChange={(e) => setForm({ ...form, process: e.target.value })} placeholder="Did I follow the plan?" /></Field>
          <Field label="Pair(s)"><input className="input" value={form.pair || ""} onChange={(e) => setForm({ ...form, pair: e.target.value })} /></Field>
          <Field label="Session"><input className="input" value={form.session || ""} onChange={(e) => setForm({ ...form, session: e.target.value })} /></Field>
          <Field label="Setups"><input className="input" value={form.setups || ""} onChange={(e) => setForm({ ...form, setups: e.target.value })} /></Field>
          <Field label="Learnings"><textarea rows="3" className="input resize-y" value={form.learnings || ""} onChange={(e) => setForm({ ...form, learnings: e.target.value })} /></Field>
        </div>

        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <Long label="Psychology / how I felt after" field="psychology" form={form} setForm={setForm} />
          <Long label="Mistakes" field="mistakes" form={form} setForm={setForm} />
          <Long label="What I did well" field="did_well" form={form} setForm={setForm} />
          <Long label="What I need to improve" field="improve" form={form} setForm={setForm} />
          <Long label="Actionable steps" field="actionable_steps" form={form} setForm={setForm} />
          <Long label="Thoughts" field="thoughts" form={form} setForm={setForm} />
        </div>

        <div className="mt-5 flex justify-end">
          <button disabled={saving} className="rounded-md bg-stone-900 px-5 py-2 text-sm text-white disabled:opacity-50">{saving ? "Saving…" : "Save daily review"}</button>
        </div>
      </form>

      <aside className="rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
        <h3 className="font-semibold">Recent reviews</h3>
        {loading && <p className="mt-3 text-sm text-stone-500">Loading reviews…</p>}
        {!loading && !items.length && <p className="mt-3 text-sm text-stone-500">No daily reviews yet. The form on the left is ready for your first one.</p>}
        <div className="mt-3 space-y-2">
          {items.map((item) => (
            <button type="button" key={item.id} onClick={() => choose(item)} className="block w-full rounded-md border border-stone-100 p-3 text-left hover:bg-stone-50">
              <p className="font-medium">{item.review_date}</p>
              <p className="mt-1 text-xs text-stone-500">{item.market_condition || "No market condition"} · {item.session || "No session"}</p>
              <p className="mt-2 line-clamp-2 text-xs text-stone-600">{item.learnings || item.thoughts || "No notes"}</p>
            </button>
          ))}
        </div>
      </aside>
    </div>
  );
}

function Field({ label, children }) {
  return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>;
}
function Long({ label, field, form, setForm }) {
  return <Field label={label}><textarea rows="4" className="input resize-y" value={form[field] || ""} onChange={(e) => setForm({ ...form, [field]: e.target.value })} /></Field>;
}
