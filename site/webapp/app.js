/* Gold Council WebApp — live data from Supabase (read-only, anon key).
   - Tab switching only.
   - Reads Telegram WebApp initData when opened inside Telegram; shows a clear
     "open inside Telegram" note when absent. NEVER fabricates a user.
   - Loads published signals + settlements + active FAQ from Supabase via
     ../assets/supabase.js and renders them. Journal stats are the honest
     DISTINCT-setup record (GC.distinctStats). No network calls to Telegram,
     no trading actions, no buy/sell/deposit/broker links.
   - Profile / referral counts have no server-side lookup yet, so they stay
     at their honest empty state — never invented.
   - Only actions: view, copy the invite link, contact Mohamed.
*/
(function () {
  "use strict";

  var tg = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp : null;
  var tgUser = null;
  if (tg) {
    try {
      tg.ready();
      if (tg.initDataUnsafe && tg.initDataUnsafe.user) {
        tgUser = tg.initDataUnsafe.user;
      }
    } catch (e) { /* opened outside Telegram or initData unavailable */ }
  }
  if (!tgUser) {
    var note = document.getElementById("telegram-note");
    if (note) note.hidden = false;
  }

  /* ---- tabs ---- */
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".tab"));
  tabs.forEach(function (btn) {
    btn.addEventListener("click", function () {
      tabs.forEach(function (b) {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      document.querySelectorAll(".panel").forEach(function (p) {
        p.classList.remove("active");
      });
      var panel = document.getElementById("panel-" + btn.getAttribute("data-tab"));
      if (panel) panel.classList.add("active");
    });
  });

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  }
  function statCard(value, label) {
    var d = el("div", "stat");
    d.appendChild(el("div", "value", String(value)));
    d.appendChild(el("div", "label", label));
    return d;
  }

  /* ---- copy invite link ---- */
  var copyBtn = document.getElementById("copy-invite");
  if (copyBtn) {
    copyBtn.addEventListener("click", function () {
      var link = document.getElementById("invite-link").textContent.trim();
      var status = document.getElementById("copy-status");
      function done(ok) {
        if (status) status.textContent = ok ? "تم النسخ." : "تعذر النسخ — انسخ الرابط يدويًا.";
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(link).then(function () { done(true); }, function () { done(false); });
      } else {
        var ta = document.createElement("textarea");
        ta.value = link;
        document.body.appendChild(ta);
        ta.select();
        try { done(document.execCommand("copy")); } catch (e) { done(false); }
        document.body.removeChild(ta);
      }
    });
  }

  /* ---- load live data from Supabase ---- */
  Promise.all([GC.publishedSignals(), GC.settlements(), GC.activeFaq()])
    .then(function (res) {
      render(res[0], res[1], res[2]);
    })
    .catch(function () {
      var m = document.getElementById("signals-meta");
      if (m) m.textContent = "تعذر تحميل البيانات — أعد فتح التطبيق لاحقًا.";
    });

  function render(published, settlements, faq) {
    /* footer — fetch time, not a build time */
    var gen = document.getElementById("generated-at");
    if (gen) {
      gen.textContent = "آخر تحديث للبيانات: " +
        new Date().toLocaleString("ar-EG", { timeZone: "Africa/Cairo" }) +
        " بتوقيت القاهرة — من قاعدة بيانات مجلس الذهب (Supabase).";
    }

    /* signals tab — published rows only, newest first */
    var list = document.getElementById("signals-list");
    var meta = document.getElementById("signals-meta");
    if (meta) {
      meta.textContent = published.length === 0
        ? "لا توجد توصيات منشورة بعد."
        : "توصيات منشورة: " + published.length;
    }
    if (list) {
      list.textContent = "";
      if (published.length === 0) {
        list.appendChild(el("p", "empty", "لا توجد توصيات منشورة بعد — التوصيات الحالية بانتظار المراجعة ولا تظهر هنا."));
      } else {
        published.forEach(function (s) {
          var card = el("div", "signal-card");
          var head = el("p");
          var dir = GC.DIR_AR[s.direction] || s.direction;
          var dirCls = s.direction === "short" ? "direction-sell" : "direction-buy";
          head.appendChild(el("span", dirCls, dir));
          head.appendChild(document.createTextNode(" " + s.symbol + " "));
          head.appendChild(el("span", "paper-tag", "ورقي"));
          card.appendChild(head);
          card.appendChild(el("p", null, "الدخول: " + s.entry + " | وقف الخسارة: " + s.stop_loss));
          card.appendChild(el("p", null, "الهدف 1: " + s.tp1 + " | الهدف 2: " + s.tp2));
          card.appendChild(el("p", "meta", "الحالة: " + (GC.RESULT_AR[s.status] || s.status) +
            " | الثقة: " + (s.confidence !== null && s.confidence !== undefined ? s.confidence + "%" : "—")));
          list.appendChild(card);
        });
      }
    }

    /* journal stats — distinct setups only, never row counts */
    var j = GC.distinctStats(published);
    var stats = document.getElementById("journal-stats");
    if (stats) {
      stats.textContent = "";
      stats.appendChild(statCard(j.closed, "صفقات مغلقة"));
      stats.appendChild(statCard(j.wins, "رابحة"));
      stats.appendChild(statCard(j.losses, "خاسرة"));
      stats.appendChild(statCard(j.win_rate + "%", "نسبة الفوز"));
      stats.appendChild(statCard(j.avg_r, "متوسط R"));
      if (!j.closed) {
        var n = el("p", "meta", "لا توجد صفقات مغلقة بعد — السجل يبدأ مع أول إغلاق، ويعرض الرابحة والخاسرة معًا.");
        n.style.gridColumn = "1 / -1";
        stats.appendChild(n);
      }
    }

    /* profile tab — real data only; no server-side lookup yet = honest empty state */
    var prof = document.getElementById("profile-body");
    if (prof) {
      prof.textContent = "";
      if (tgUser) {
        prof.appendChild(el("p", null, "أنت: " + (tgUser.first_name || "") + " " + (tgUser.last_name || "")));
      }
      prof.appendChild(el("p", "empty", "لا يوجد اشتراك مسجل بعد."));
      prof.appendChild(el("p", null, "أنت في قائمة الانتظار. للاشتراك تواصل مع محمد مباشرة — الدفع يدوي ولا يوجد دفع داخل البوت."));
    }
    var prog = document.getElementById("profile-progress");
    if (prog) {
      prog.textContent = "";
      prog.appendChild(statCard(0, "توصيات شوهدت"));
      prog.appendChild(statCard(0, "صفقات دخلتها"));
      prog.appendChild(statCard(0, "رابحة"));
      prog.appendChild(statCard(0, "خاسرة"));
      var pn2 = el("p", "meta", "لا يوجد سجل تقدم بعد — لا يوجد اشتراك مسجل.");
      pn2.style.gridColumn = "1 / -1";
      prog.appendChild(pn2);
    }

    /* support tab — FAQ from Supabase */
    var faqList = document.getElementById("faq-list");
    if (faqList) {
      faqList.textContent = "";
      if (!faq || faq.length === 0) {
        faqList.appendChild(el("p", "empty", "لا توجد أسئلة شائعة بعد."));
      } else {
        faq.forEach(function (item) {
          var box = el("div", "faq-item");
          box.appendChild(el("h3", null, item.question));
          box.appendChild(el("p", null, item.answer));
          faqList.appendChild(box);
        });
      }
    }

    /* referral tab — personal link from Telegram id; counts stay 0 (no lookup yet) */
    var invite = document.getElementById("invite-link");
    var inviteNote = document.getElementById("invite-note");
    if (tgUser && tgUser.id) {
      if (invite) invite.textContent = "https://t.me/GoldCouncil_bot?start=ref_" + tgUser.id;
      if (inviteNote) inviteNote.textContent = "رابطك الشخصي — شاركه وسيُحتسب المدعوون هنا.";
    } else {
      if (invite) invite.textContent = "https://t.me/GoldCouncil_bot?start=ref_<id>";
      if (inviteNote) inviteNote.textContent = "رابط قالب — يُخصَّص برقمك بعد فتح التطبيق من داخل تيليجرام.";
    }
    var ref = document.getElementById("referral-stats");
    if (ref) {
      ref.textContent = "";
      ref.appendChild(statCard(0, "مدعوون"));
      ref.appendChild(statCard(0, "أيام مكافأة"));
      var rn = el("p", "meta", "لا توجد دعوات مسجلة بعد.");
      rn.style.gridColumn = "1 / -1";
      ref.appendChild(rn);
    }
  }
})();
