/* Gold Council landing — journal + FAQ, live from Supabase (read-only, anon).
   No invented numbers, ever: stats are the honest DISTINCT-setup record
   computed from the published signals Supabase returns. With 0 closed
   setups the page shows the honest paper-phase empty state. */
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

  function statCard(value, label) {
    var d = el("div", "stat");
    d.appendChild(el("b", null, String(value)));
    d.appendChild(el("span", null, label));
    return d;
  }

  function renderJournal(signals, settlements) {
    var st = GC.distinctStats(signals);
    statsBox.textContent = "";
    statsBox.appendChild(statCard(st.closed, "صفقات مغلقة (مميزة)"));
    statsBox.appendChild(statCard(st.wins, "رابحة"));
    statsBox.appendChild(statCard(st.losses, "خاسرة"));
    var line = el("p", "micro");
    line.style.textAlign = "center";
    line.style.margin = "-8px 0 22px";
    line.innerHTML = "نسبة الفوز: <b style=\"color:var(--gold2)\">" +
      (st.closed ? st.win_rate + "%" : "—") + "</b> · متوسط العائد: <b style=\"color:var(--gold2)\">" +
      (st.closed ? fmtR(st.avg_r) : "—") + "</b>";
    statsBox.parentNode.insertBefore(line, statsBox.nextSibling);

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
      card.appendChild(el("h3", null, "لا توجد صفقات مغلقة بعد"));
      var p = el("p", null, "المجلس في مرحلة التداول الورقي — كل توصية تُسجَّل هنا بنتيجتها الفعلية، رابحة أو خاسرة، فور إغلاقها. لا نتائج معروضة قبل وقوعها.");
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
      hr.style.textAlign = "right";
      ["التاريخ", "الأداة", "الاتجاه", "الدخول", "النتيجة", "العائد"].forEach(function (h) {
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
          GC.DIR_AR[s.direction] || s.direction,
          String(s.entry),
          GC.RESULT_AR[s.status] || s.status,
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
      updatedEl.textContent = "مرحلة ورقية (Paper) — لا أموال حقيقية. آخر تحديث: " +
        new Date().toLocaleString("ar-EG", { timeZone: "Africa/Cairo" }) +
        " بتوقيت القاهرة — البيانات من قاعدة بيانات مجلس الذهب (Supabase).";
    }
  }

  function renderFaq(items) {
    faqBox.textContent = "";
    if (!items || items.length === 0) {
      faqBox.appendChild(el("p", "empty", "لا توجد أسئلة شائعة بعد."));
      return;
    }
    items.forEach(function (item) {
      var d = document.createElement("details");
      var s = document.createElement("summary");
      s.textContent = item.question;
      var p = document.createElement("p");
      p.textContent = item.answer;
      d.appendChild(s);
      d.appendChild(p);
      faqBox.appendChild(d);
    });
  }

  Promise.all([GC.publishedSignals(), GC.settlements()])
    .then(function (res) { renderJournal(res[0], res[1]); })
    .catch(function () {
      statsBox.textContent = "";
      bodyBox.textContent = "";
      bodyBox.appendChild(el("p", "empty", "تعذّر تحميل سجل النتائج — تحقق من اتصالك وأعد تحميل الصفحة."));
    });

  GC.activeFaq()
    .then(renderFaq)
    .catch(function () {
      faqBox.textContent = "";
      faqBox.appendChild(el("p", "empty", "تعذّر تحميل الأسئلة الشائعة — أعد تحميل الصفحة لاحقًا."));
    });
})();
