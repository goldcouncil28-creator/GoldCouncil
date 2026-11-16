/* Gold Council landing — journal + FAQ, live from Supabase (read-only, anon).
   No invented numbers, ever: stats are the honest DISTINCT-setup record
   computed from the CLOSED paper signals Supabase returns (migration
   0004 exposes closed rows only; open/pending setups stay hidden).
   The journal auto-refreshes every hour so an open page stays current.
   With 0 closed setups the page shows the honest paper-phase empty state. */
(function () {
  "use strict";

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function fmtR(v) {
    if (v === null || v === undefined) return "—";
    var n = Number(v);
    return (n > 0 ? "+" : "") + n.toFixed(2) + "R";
  }

  var statsBox = document.getElementById("journal-stats");
  var bodyBox = document.getElementById("journal-body");
  var updatedEl = document.getElementById("journal-updated");
  var faqBox = document.getElementById("faq-list");
  var T = function (k) { return GC_I18N.t(k); };

  /* Cached live data, so a language switch re-renders without refetching. */
  var lastSignals = null, lastSettlements = null, lastFaq = null;
  var winRateLine = null; /* one persistent line under the journal stats */
  document.addEventListener("gc:lang", function () {
    if (lastSignals) renderJournal(lastSignals, lastSettlements || []);
    if (lastFaq) renderFaq(lastFaq);
  });

  function statCard(value, label) {
    var d = el("div", "stat");
    d.appendChild(el("b", null, String(value)));
    d.appendChild(el("span", null, label));
    return d;
  }

  function renderJournal(signals, settlements) {
    lastSignals = signals;
    lastSettlements = settlements || [];
    var st = GC.distinctStats(signals);
    statsBox.textContent = "";
    statsBox.appendChild(statCard(st.closed, T("j_closed")));
    statsBox.appendChild(statCard(st.wins, T("j_wins")));
    statsBox.appendChild(statCard(st.losses, T("j_losses")));
    if (!winRateLine) {
      winRateLine = el("p", "micro");
      winRateLine.style.textAlign = "center";
      winRateLine.style.margin = "-8px 0 22px";
      statsBox.parentNode.insertBefore(winRateLine, statsBox.nextSibling);
    }
    winRateLine.innerHTML = T("j_winrate") + " <b style=\"color:var(--gold2)\">" +
      (st.closed ? st.win_rate + "%" : "—") + "</b> · " + T("j_avgr") + " <b style=\"color:var(--gold2)\">" +
      (st.closed ? fmtR(st.avg_r) : "—") + "</b>";

    bodyBox.textContent = "";
    var seen = {}, rows = [];
    signals.forEach(function (s) {
      var k = GC.setupKey(s);
      if (seen[k] || s.status === "open") return;
      seen[k] = true;
      rows.push(s);
    });
    if (rows.length === 0) {
      var card = el("div", "card");
      card.style.textAlign = "center";
      card.style.maxWidth = "640px";
      card.style.margin = "auto";
      card.appendChild(el("h3", null, T("j_empty_h")));
      var p = el("p", null, T("j_empty_p"));
      card.appendChild(p);
      bodyBox.appendChild(card);
    } else {
      var wrap = el("div");
      wrap.style.overflowX = "auto";
      var table = document.createElement("table");
      table.style.width = "100%";
      table.style.borderCollapse = "collapse";
      table.style.fontSize = "14px";
      var thead = document.createElement("thead");
      var hr = document.createElement("tr");
      hr.style.color = "var(--muted)";
      hr.style.textAlign = GC_I18N.lang === "en" ? "left" : "right";
      [T("th_date"), T("th_tool"), T("th_dir"), T("th_entry"), T("th_result"), T("th_pnl")].forEach(function (h) {
        var th = document.createElement("th");
        th.style.padding = "10px";
        th.textContent = h;
        hr.appendChild(th);
      });
      thead.appendChild(hr);
      table.appendChild(thead);
      var tbody = document.createElement("tbody");
      rows.forEach(function (s) {
        var tr = document.createElement("tr");
        var cells = [
          (s.created_at || "").slice(0, 10),
          s.symbol,
          GC_I18N.dirLabel(s.direction),
          String(s.entry),
          GC_I18N.resultLabel(s.status),
          fmtR(s.pnl_r)
        ];
        cells.forEach(function (c, i) {
          var td = document.createElement("td");
          td.style.padding = "10px";
          if (i === 1 || i === 3 || i === 5) td.dir = "ltr";
          td.textContent = c;
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      wrap.appendChild(table);
      bodyBox.appendChild(wrap);
    }
    if (updatedEl) {
      var locale = GC_I18N.lang === "en" ? "en-GB" : "ar-EG";
      updatedEl.textContent = T("j_updated").replace("{date}",
        new Date().toLocaleString(locale, { timeZone: "Africa/Cairo" }));
    }
  }

  function renderFaq(items) {
    lastFaq = items;
    faqBox.textContent = "";
    if (!items || items.length === 0) {
      faqBox.appendChild(el("p", "empty", T("faq_empty")));
      return;
    }
    items.forEach(function (item) {
      var pair = GC_I18N.faqPair(item.question, item.answer);
      var d = document.createElement("details");
      var s = document.createElement("summary");
      s.textContent = pair[0];
      var p = document.createElement("p");
      p.textContent = pair[1];
      d.appendChild(s);
      d.appendChild(p);
      faqBox.appendChild(d);
    });
  }

  function loadJournal() {
    Promise.all([GC.closedSignals(), GC.settlements()])
      .then(function (res) { renderJournal(res[0], res[1]); })
      .catch(function () {
        statsBox.textContent = "";
        bodyBox.textContent = "";
        bodyBox.appendChild(el("p", "empty", T("j_err")));
      });
  }
  loadJournal();
  /* Hourly auto-refresh: the data is live on every load already; this
     keeps an open page current without a manual reload. */
  setInterval(loadJournal, 3600000);

  GC.activeFaq()
    .then(renderFaq)
    .catch(function () {
      faqBox.textContent = "";
      faqBox.appendChild(el("p", "empty", T("faq_err")));
    });
})();
