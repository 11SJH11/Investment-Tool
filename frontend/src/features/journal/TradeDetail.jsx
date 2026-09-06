import { useEffect, useState } from "react";
import { api, backendFileUrl } from "../../api/client";
import SymbolSearch from "../../components/SymbolSearch";
import { formatInZone, isoToZonedInput, zonedInputToIso } from "../../utils/timezones";
import { moneyCurrency, pct, resultTone, rrValue, rValue, sourceLabels } from "./journalUtils";

const timeframes = ["1m", "5m", "15m", "30m", "1H", "4H"];

function numericOrNull(v) { return v === "" || v == null ? null : Number(v); }

export default function TradeDetail({ trade, onChanged, onClose, timeZone = "America/New_York" }) {
  const [draft, setDraft] = useState(trade);
  const [edit, setEdit] = useState(null);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { setDraft(trade); if (edit) setEdit(makeEdit(trade, timeZone)); }, [trade, timeZone]);
  if (!trade || !draft) return null;

  const saveNotes = async () => {
    setSaving(true); setError("");
    try {
      const updated = await api.updateJournalTrade(trade.id, {
        analysis: draft.analysis, entry_notes: draft.entry_notes, management: draft.management,
        learning: draft.learning, notes: draft.notes, timeframe_notes: draft.timeframe_notes || {},
      });
      onChanged?.(updated);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const saveTrade = async () => {
    setSaving(true); setError("");
    try {
      const payload = {
        source: edit.source, account: edit.account, ticker: edit.ticker.toUpperCase(), direction: edit.direction,
        opened_at: zonedInputToIso(edit.opened_at, timeZone),
        closed_at: zonedInputToIso(edit.closed_at, timeZone),
        entry_price: numericOrNull(edit.entry_price), exit_price: numericOrNull(edit.exit_price),
        quantity: null, position_amount: numericOrNull(edit.position_amount), position_currency: edit.position_currency || "USD", stop_loss: numericOrNull(edit.stop_loss),
        take_profit: numericOrNull(edit.take_profit), fees: numericOrNull(edit.fees) ?? 0,
        pnl_override: numericOrNull(edit.pnl_override), override_reason: edit.override_reason || "",
        trade_type: edit.trade_type || "", setup: edit.setup || "", market_condition: edit.market_condition || "",
        entry_timeframe: edit.entry_timeframe || "", timeframe_alignment: edit.timeframe_alignment || "",
        dxy: edit.dxy || "", session_time: edit.session_time || "", tf_type: edit.tf_type || "", wick: edit.wick || "",
      };
      const updated = await api.updateJournalTrade(trade.id, payload);
      setEdit(null); onChanged?.(updated);
    } catch (e) { setError(e.message); }
    finally { setSaving(false); }
  };

  const upload = async (slot, file) => {
    if (!file) return;
    setUploading(slot); setError("");
    try { await api.uploadJournalAttachment("trade", trade.id, slot, file); onChanged?.(); }
    catch (e) { setError(e.message); }
    finally { setUploading(""); }
  };
  const removeImage = async (id) => { await api.deleteJournalAttachment(id); onChanged?.(); };
  const setTf = (tf, value) => setDraft({ ...draft, timeframe_notes: { ...(draft.timeframe_notes || {}), [tf]: value } });
  const attachments = trade.attachments || [];

  return <section className="mt-5 rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
    <div className="flex flex-wrap items-start justify-between gap-3 border-b border-stone-100 pb-4">
      <div><div className="flex gap-2 text-xs text-stone-500"><span>{sourceLabels[trade.source]}</span><span>·</span><span>{trade.account}</span></div><h3 className="mt-1 text-2xl font-semibold">{trade.ticker} · {trade.setup || trade.trade_type || "Trade"}</h3><p className="mt-1 text-sm text-stone-500">{trade.direction.toUpperCase()} · {trade.opened_at ? formatInZone(trade.opened_at, timeZone) : "No entry time"} · <span className={resultTone(trade.result)}>{trade.result?.toUpperCase() || "OPEN"}</span></p></div>
      <div className="flex flex-wrap gap-2"><button onClick={onClose} className="rounded-md border border-stone-300 bg-white px-4 py-2 text-sm">Close details</button><button onClick={() => setEdit(edit ? null : makeEdit(trade, timeZone))} className="rounded-md border border-stone-300 bg-white px-4 py-2 text-sm">{edit ? "Cancel edit" : "Edit trade"}</button><button onClick={saveNotes} disabled={saving} className="rounded-md bg-stone-900 px-4 py-2 text-sm text-white">{saving ? "Saving…" : "Save notes"}</button></div>
    </div>
    {error && <p className="mt-3 text-sm text-red-700">{error}</p>}

    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
      <Metric label="Result" value={trade.result?.toUpperCase() || "OPEN"} tone={resultTone(trade.result)} />
      <Metric label="P&L" value={moneyCurrency(trade.pnl_amount, trade.position_currency || "USD")} />
      <Metric label="P&L %" value={pct(trade.pnl_pct)} />
      <Metric label="Planned R:R" value={rrValue(trade.planned_rr)} />
      <Metric label="Realised R" value={rValue(trade.r_multiple)} />
      <Metric label="P&L source" value={trade.pnl_source === "manual_override" ? "Broker override" : trade.pnl_source === "computed" ? "Calculated" : "—"} />
    </div>

    {edit && <div className="mt-5 rounded-lg border border-stone-200 bg-stone-50 p-4">
      <div className="flex items-center justify-between"><div><h4 className="font-semibold">Edit original trade</h4><p className="mt-1 text-xs text-stone-500">Changing entry, exit, stop, target, position value, fees or direction recalculates P&L, planned R:R and realised R.</p></div><button onClick={saveTrade} disabled={saving} className="rounded-md bg-stone-900 px-4 py-2 text-sm text-white">{saving ? "Saving…" : "Save trade changes"}</button></div>
      <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <Field label="Source"><select className="input" value={edit.source} onChange={(e) => setEdit({ ...edit, source: e.target.value })}><option value="live_manual">Live · manual</option><option value="paper_manual">Paper · manual</option><option value="replay">Replay</option><option value="backtest">Backtest</option></select></Field>
        <Field label="Account"><input className="input" value={edit.account} onChange={(e) => setEdit({ ...edit, account: e.target.value })} /></Field>
        <Field label="Pair / ticker"><SymbolSearch value={edit.ticker} onChange={(v) => setEdit({ ...edit, ticker: v.toUpperCase() })} onSelect={(item) => setEdit({ ...edit, ticker: item.ticker })} placeholder="AAPL / XAUUSD" /></Field>
        <Field label="Direction"><select className="input" value={edit.direction} onChange={(e) => setEdit({ ...edit, direction: e.target.value })}><option value="long">Long</option><option value="short">Short</option></select></Field>
        <Field label={`Entry time (${timeZone === "America/New_York" ? "ET" : timeZone})`}><input type="datetime-local" className="input" value={edit.opened_at} onChange={(e) => setEdit({ ...edit, opened_at: e.target.value })} /></Field>
        <Field label={`Exit time (${timeZone === "America/New_York" ? "ET" : timeZone})`}><input type="datetime-local" className="input" value={edit.closed_at} onChange={(e) => setEdit({ ...edit, closed_at: e.target.value })} /></Field>
        <Field label="Entry"><Num value={edit.entry_price} set={(v) => setEdit({ ...edit, entry_price: v })} /></Field>
        <Field label="Stop"><Num value={edit.stop_loss} set={(v) => setEdit({ ...edit, stop_loss: v })} /></Field>
        <Field label="Target / take profit"><Num value={edit.take_profit} set={(v) => setEdit({ ...edit, take_profit: v })} /></Field>
        <Field label="Actual exit price"><Num value={edit.exit_price} set={(v) => setEdit({ ...edit, exit_price: v })} /></Field>
        <Field label="Amount invested / position value"><Num value={edit.position_amount} set={(v) => setEdit({ ...edit, position_amount: v })} /></Field>
        <Field label="Position currency"><input className="input uppercase" maxLength="6" value={edit.position_currency} onChange={(e) => setEdit({ ...edit, position_currency: e.target.value.toUpperCase() })} /></Field>
        <Field label="Calculated quantity"><div className="input flex items-center bg-white text-stone-600">{calcQuantity(edit)}</div></Field>
        <Field label="Fees"><Num value={edit.fees} set={(v) => setEdit({ ...edit, fees: v })} /></Field>
        <Field label="Broker P&L override"><Num value={edit.pnl_override} set={(v) => setEdit({ ...edit, pnl_override: v })} /></Field>
        <Field label="Override reason"><input className="input" value={edit.override_reason} onChange={(e) => setEdit({ ...edit, override_reason: e.target.value })} /></Field>
        <Field label="Type"><input className="input" value={edit.trade_type} onChange={(e) => setEdit({ ...edit, trade_type: e.target.value })} /></Field>
        <Field label="Setup"><input className="input" value={edit.setup} onChange={(e) => setEdit({ ...edit, setup: e.target.value })} /></Field>
        <Field label="Market condition"><input className="input" value={edit.market_condition} onChange={(e) => setEdit({ ...edit, market_condition: e.target.value })} /></Field>
        <Field label="Entry TF"><input className="input" value={edit.entry_timeframe} onChange={(e) => setEdit({ ...edit, entry_timeframe: e.target.value })} /></Field>
        <Field label="TF alignment"><input className="input" value={edit.timeframe_alignment} onChange={(e) => setEdit({ ...edit, timeframe_alignment: e.target.value })} /></Field>
        <Field label="DXY"><input className="input" value={edit.dxy} onChange={(e) => setEdit({ ...edit, dxy: e.target.value })} /></Field>
        <Field label="Session"><input className="input" value={edit.session_time} onChange={(e) => setEdit({ ...edit, session_time: e.target.value })} /></Field>
        <Field label="TF Type"><input className="input" value={edit.tf_type} onChange={(e) => setEdit({ ...edit, tf_type: e.target.value })} /></Field>
        <Field label="Wick"><input className="input" value={edit.wick} onChange={(e) => setEdit({ ...edit, wick: e.target.value })} /></Field>
      </div>
    </div>}

    <div className="mt-5 grid gap-4 md:grid-cols-2 xl:grid-cols-3">{timeframes.map((tf) => {
      const images = attachments.filter((a) => a.slot === tf);
      return <div key={tf} className="rounded-lg border border-stone-200 p-3"><div className="flex items-center justify-between"><h4 className="font-mono font-semibold">{tf}</h4><label className="cursor-pointer text-xs text-blue-700 hover:underline">{uploading === tf ? "Uploading…" : "+ screenshot"}<input type="file" accept="image/*" className="hidden" onChange={(e) => upload(tf, e.target.files?.[0])} /></label></div>
        <textarea rows="3" className="input mt-2 resize-y" value={draft.timeframe_notes?.[tf] || ""} onChange={(e) => setTf(tf, e.target.value)} placeholder={`What did you see on ${tf}?`} />
        {images.map((img) => <div key={img.id} className="group relative mt-2 overflow-hidden rounded-md border"><img src={backendFileUrl(img.url)} className="max-h-56 w-full object-contain bg-stone-950" /><button onClick={() => removeImage(img.id)} className="absolute right-2 top-2 rounded bg-black/70 px-2 py-1 text-xs text-white opacity-0 group-hover:opacity-100">Remove</button></div>)}
      </div>;
    })}</div>

    <div className="mt-6 grid gap-5 md:grid-cols-2">
      <Note title="Analysis" value={draft.analysis} onChange={(v) => setDraft({ ...draft, analysis: v })} placeholder="What was happening? Direction, context, AOI, confluences…" />
      <Note title="Entry" value={draft.entry_notes} onChange={(v) => setDraft({ ...draft, entry_notes: v })} placeholder="Why exactly did you enter here?" />
      <Note title="Management" value={draft.management} onChange={(v) => setDraft({ ...draft, management: v })} placeholder="How did you manage the position?" />
      <Note title="Learning" value={draft.learning} onChange={(v) => setDraft({ ...draft, learning: v })} placeholder="What should you repeat or change next time?" />
    </div>
  </section>;
}

function calcQuantity(t) { const entry = Number(t.entry_price); const amount = Number(t.position_amount); if (!(entry > 0) || !(amount > 0)) return t.quantity == null ? "—" : Number(t.quantity).toFixed(8).replace(/0+$/, "").replace(/\.$/, ""); return (amount / entry).toFixed(8).replace(/0+$/, "").replace(/\.$/, ""); }
function makeEdit(t, timeZone) { return { ...t, opened_at: isoToZonedInput(t.opened_at, timeZone), closed_at: isoToZonedInput(t.closed_at, timeZone), entry_price: t.entry_price ?? "", exit_price: t.exit_price ?? "", quantity: t.quantity ?? "", position_amount: t.position_amount ?? (t.entry_price && t.quantity ? Number(t.entry_price) * Number(t.quantity) : ""), position_currency: t.position_currency || "USD", stop_loss: t.stop_loss ?? "", take_profit: t.take_profit ?? "", fees: t.fees ?? 0, pnl_override: t.pnl_override ?? "", override_reason: t.override_reason ?? "" }; }
function Num({ value, set }) { return <input type="number" step="any" className="input" value={value} onChange={(e) => set(e.target.value)} />; }
function Field({ label, children }) { return <label className="block"><span className="mb-1 block text-xs font-medium text-stone-500">{label}</span>{children}</label>; }
function Metric({ label, value, tone = "" }) { return <div className="rounded-lg bg-stone-50 p-3"><p className="text-xs uppercase tracking-wide text-stone-500">{label}</p><p className={`mt-1 font-semibold ${tone}`}>{value}</p></div>; }
function Note({ title, value, onChange, placeholder }) { return <label><span className="mb-2 block font-semibold">{title}</span><textarea rows="5" className="input resize-y" value={value || ""} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} /></label>; }
