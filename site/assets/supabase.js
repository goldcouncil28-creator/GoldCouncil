/* Gold Council — Supabase read-only client (shared by the landing page and the WebApp).
   Public client: SUPABASE_URL + SUPABASE_PUBLISHABLE (the anon key).
   The publishable key is a PUBLIC key by design — it is safe to ship in
   client code. RLS is the protection: anon can SELECT only published
   signals, their settlements, and active FAQ. Nothing else is readable
   and nothing is writable. NEVER put the service_role (secret) key here. */
(function (global) {
  "use strict";
  var SUPABASE_URL = "https://xxbtrtdjijrhmcbzmxxm.supabase.co";
  var SUPABASE_PUBLISHABLE = "sb_publishable_gjUSvtuFnrY5kYEsSuo-RA_0hoielo8";

  function headers() {
    return {
      apikey: SUPABASE_PUBLISHABLE,
      Authorization: "Bearer " + SUPABASE_PUBLISHABLE,
      Accept: "application/json"
    };
  }
  function get(path) {
    return fetch(SUPABASE_URL + "/rest/v1/" + path, { headers: headers() })
      .then(function (r) {
        if (!r.ok) throw new Error("Supabase HTTP " + r.status);
        return r.json();
      });
  }
  function publishedSignals() {
    return get("signals?select=id,created_at,symbol,direction,entry,stop_loss,tp1,tp2,confidence,status,mode,review_status&review_status=eq.published&order=created_at.desc&limit=200");
  }
  /* Closed paper signals (any review_status) — the public journal.
     RLS (migration 0004) exposes only CLOSED rows (tp1/tp2/sl/expired);
     open/pending setups stay service-only. pnl_r is included: the
     journal shows real returns, not dashes. */
  function closedSignals() {
    return get("signals?select=id,created_at,symbol,direction,entry,stop_loss,tp1,tp2,confidence,status,pnl_r,mode,review_status&status=in.(tp1,tp2,sl,expired)&order=created_at.desc&limit=200");
  }
  function settlements() {
    return get("settlements?select=signal_id,outcome,exit_price,pnl_r,settled_at&order=settled_at.desc&limit=500");
  }
  function activeFaq() {
    return get("faq?select=question,answer&is_active=eq.true&order=sort_order");
  }
  function setupKey(s) {
    return [s.symbol, s.direction, Number(s.entry), Number(s.stop_loss), Number(s.tp1), Number(s.tp2)].join("|");
  }
  /* Honest journal stats: group by the FULL setup (symbol + direction +
     entry + stop + tp1 + tp2) and count each DISTINCT setup once — never
     row counts. A setup logged twice is still one setup. */
  function distinctStats(signals) {
    var seen = {}, wins = 0, losses = 0, sumR = 0, closed = 0, open = 0;
    signals.forEach(function (s) {
      var k = setupKey(s);
      if (seen[k]) return;
      seen[k] = true;
      if (s.status === "open") { open++; return; }
      closed++;
      if (s.status === "tp1" || s.status === "tp2") wins++;
      else if (s.status === "sl") losses++;
      if (typeof s.pnl_r === "number") sumR += s.pnl_r;
    });
    var n = wins + losses;
    return {
      total_setups: Object.keys(seen).length,
      open: open, closed: closed, wins: wins, losses: losses,
      win_rate: n ? Math.round(1000 * wins / n) / 10 : 0,
      avg_r: n ? Math.round(100 * sumR / n) / 100 : 0
    };
  }
  var DIR_AR = { long: "شراء", short: "بيع" };
  var RESULT_AR = { tp1: "🎯 هدف أول", tp2: "🎯🎯 هدف ثانٍ", sl: "⛔ وقف خسارة", open: "⏳ مفتوحة", expired: "⌛ منتهية" };
  global.GC = {
    publishedSignals: publishedSignals,
    closedSignals: closedSignals,
    settlements: settlements,
    activeFaq: activeFaq,
    distinctStats: distinctStats,
    setupKey: setupKey,
    DIR_AR: DIR_AR,
    RESULT_AR: RESULT_AR
  };
})(window);
