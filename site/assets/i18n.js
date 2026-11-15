/* Gold Council — language toggle (Arabic / English).
   Default Arabic. The visitor's choice is saved in localStorage (gc-lang).
   Static text: elements with data-i18n (plain) / data-i18n-html (markup).
   Dynamic text (journal + FAQ rendered by landing.js): GC_I18N.t(key).
   FAQ rows arrive from Supabase in Arabic; the 7 known Q&As are
   translated here by EXACT question match — anything unknown falls back
   to the Arabic text, never invented. */
(function (global) {
  "use strict";

  var STR = {
    ar: {
      title: "مجلس الذهب | Gold Council",
      meta_desc: "مجلس الذهب — تحليلات وتوصيات فوركس وذهب XAUUSD مبنية على قراءة جماعية للسوق.",
      nav_about: "عن المجلس",
      nav_method: "آلية العمل",
      nav_signal: "نموذج التوصية",
      nav_journal: "سجل النتائج",
      nav_faq: "الأسئلة الشائعة",
      nav_subscribe: "طلب الاشتراك",
      hero_title: "مش رأي محلل…<br><span>دي رؤية مجلس كامل.</span>",
      hero_lead: "توصيات فوركس وذهب <b dir=\"ltr\">XAUUSD</b> مبنية على تحليل جماعي من 35 محلل، بهدف تقديم رؤية أوضح للسوق وخطة تداول محددة قبل اتخاذ القرار.",
      hero_cta1: "اطلب الاشتراك الآن ↗",
      hero_cta2: "اكتشف آلية العمل",
      hero_micro: "بحد أقصى 3 توصيات يومياً · سجل نتائج واضح · إدارة مخاطر",
      stat_analysts: "محلل ضمن الرؤية الجماعية",
      stat_daily: "توصيات كحد أقصى يومياً",
      stat_clear: "وضوح تفاصيل كل توصية",
      method_h2: "تحليل منظم… وتوصية واضحة",
      method_p: "نركز على جودة الفرص ووضوح الخطة، لا على كثرة الإشارات.",
      card1_t: "تحليل جماعي",
      card1_p: "قراءة متعددة للسوق تجمع وجهات نظر المحللين قبل طرح التوصية.",
      card2_t: "خطة تداول متكاملة",
      card2_p: "دخول ووقف خسارة وأهداف، مع شرح الفكرة وصورة الشارت.",
      card3_t: "انتقائية في الفرص",
      card3_p: "بحد أقصى ثلاث توصيات يومياً لتجنب إغراق المشترك بالإشارات.",
      card4_t: "سجل نتائج مفتوح",
      card4_p: "عرض الصفقات الرابحة والخاسرة بوضوح، دون إخفاء النتائج السلبية.",
      card5_t: "إدارة للمخاطر",
      card5_p: "مستويات وقف خسارة وأهداف محددة، مع ضرورة الالتزام بحجم مخاطرة مناسب.",
      card6_t: "اشتراك بإشراف الأدمن",
      card6_p: "تفعيل يدوي للاشتراك من خلال مسؤول القناة بعد مراجعة الطلب.",
      signal_h2: "كل توصية… بكل تفاصيلها",
      signal_p: "مثال توضيحي لشكل بطاقة التوصية، وليس إشارة تداول حالية.",
      chart_note: "رسم واجهة تجريبي — لا يعرض بيانات سوق مباشرة.",
      row_tool: "الأداة",
      row_dir: "اتجاه الصفقة",
      row_entry: "نقطة الدخول",
      row_sl: "وقف الخسارة",
      row_tp: "الأهداف",
      row_analysis: "شرح وتحليل",
      steps_h2: "ابدأ في 3 خطوات",
      steps_p: "رحلة اشتراك واضحة وبسيطة.",
      step1_t: "أرسل طلبك",
      step1_p: "تواصل مع الأدمن للاستفسار عن تفاصيل الاشتراك.",
      step2_t: "تأكيد الاشتراك",
      step2_p: "يتم مراجعة الطلب وتأكيد طريقة الاشتراك يدوياً.",
      step3_t: "تفعيل الوصول",
      step3_p: "بعد التأكيد، يرسل لك الأدمن تعليمات الانضمام.",
      cta_h2: "جاهز تتابع السوق برؤية أوضح؟",
      cta_p: "تواصل مع الأدمن لمعرفة تفاصيل الاشتراك والتفعيل.",
      cta_btn: "تواصل مع محمد ↗",
      journal_h2: "سجل النتائج الحقيقي",
      journal_p: "كل صفقة مغلقة تُسجَّل هنا بنتيجتها الفعلية — رابحة أو خاسرة — دون إخفاء. الاستراتيجية بلا حافة مثبتة بعد — السجل معلن: الرابحة والخاسرة معًا.",
      faq_h2: "أسئلة شائعة",
      risk: "⚠️ <b>تنبيه مخاطر:</b> المحتوى لأغراض المعلومات والتحليل فقط، ولا يمثل ضماناً للربح أو توصية استثمارية شخصية. التداول ينطوي على مخاطر مرتفعة؛ لا تخاطر بأموال لا تتحمل خسارتها، وتأكد من فهمك للمخاطر قبل اتخاذ أي قرار.",
      foot_line: "35 محلل · رؤية واحدة للسوق",
      foot_rights: "© 2026 Gold Council. جميع الحقوق محفوظة.",
      j_loading_stat: "جارٍ تحميل السجل",
      j_loading_body: "جارٍ تحميل سجل النتائج من قاعدة بيانات مجلس الذهب…",
      faq_loading: "جارٍ تحميل الأسئلة الشائعة…",
      j_closed: "صفقات مغلقة (مميزة)",
      j_wins: "رابحة",
      j_losses: "خاسرة",
      j_winrate: "نسبة الفوز:",
      j_avgr: "متوسط العائد:",
      j_empty_h: "لا توجد صفقات مغلقة بعد",
      j_empty_p: "المجلس في مرحلة التداول الورقي — كل توصية تُسجَّل هنا بنتيجتها الفعلية، رابحة أو خاسرة، فور إغلاقها. لا نتائج معروضة قبل وقوعها.",
      j_err: "تعذّر تحميل سجل النتائج — تحقق من اتصالك وأعد تحميل الصفحة.",
      j_updated: "مرحلة ورقية (Paper) — لا أموال حقيقية. آخر تحديث: {date} بتوقيت القاهرة — البيانات من قاعدة بيانات مجلس الذهب (Supabase).",
      th_date: "التاريخ",
      th_tool: "الأداة",
      th_dir: "الاتجاه",
      th_entry: "الدخول",
      th_result: "النتيجة",
      th_pnl: "العائد",
      faq_empty: "لا توجد أسئلة شائعة بعد.",
      faq_err: "تعذّر تحميل الأسئلة الشائعة — أعد تحميل الصفحة لاحقًا."
    },
    en: {
      title: "Gold Council | Forex & Gold Signals",
      meta_desc: "Gold Council — forex and gold XAUUSD analysis and signals built on a collective read of the market.",
      nav_about: "About the Council",
      nav_method: "How It Works",
      nav_signal: "Sample Signal",
      nav_journal: "Results Journal",
      nav_faq: "FAQ",
      nav_subscribe: "Request Subscription",
      hero_title: "Not one analyst's opinion…<br><span>but a whole council's view.</span>",
      hero_lead: "Forex and gold <b dir=\"ltr\">XAUUSD</b> signals built on collective analysis from 35 analysts — a clearer view of the market and a defined trading plan before you decide.",
      hero_cta1: "Request Subscription Now ↗",
      hero_cta2: "Discover How It Works",
      hero_micro: "Max 3 signals per day · Transparent results journal · Risk management",
      stat_analysts: "analysts in the collective view",
      stat_daily: "signals max per day",
      stat_clear: "clarity on every signal's details",
      method_h2: "Structured analysis… a clear signal",
      method_p: "We focus on the quality of opportunities and the clarity of the plan, not on the number of signals.",
      card1_t: "Collective analysis",
      card1_p: "A multi-angle read of the market, combining the analysts' views before a signal is issued.",
      card2_t: "Complete trading plan",
      card2_p: "Entry, stop loss and targets, with the idea explained and a chart image.",
      card3_t: "Selective opportunities",
      card3_p: "At most three signals a day, so subscribers are never flooded with signals.",
      card4_t: "Open results journal",
      card4_p: "Winning and losing trades shown clearly, without hiding negative results.",
      card5_t: "Risk management",
      card5_p: "Defined stop-loss and target levels, with an appropriate risk size.",
      card6_t: "Admin-managed subscription",
      card6_p: "Manual subscription activation by the channel admin after reviewing the request.",
      signal_h2: "Every signal… with all its details",
      signal_p: "An illustrative example of what a signal card looks like — not a live trading signal.",
      chart_note: "Demo interface drawing — it does not show live market data.",
      row_tool: "Instrument",
      row_dir: "Trade direction",
      row_entry: "Entry point",
      row_sl: "Stop loss",
      row_tp: "Targets",
      row_analysis: "Explanation & analysis",
      steps_h2: "Start in 3 steps",
      steps_p: "A clear and simple subscription journey.",
      step1_t: "Send your request",
      step1_p: "Contact the admin to ask about subscription details.",
      step2_t: "Confirm subscription",
      step2_p: "Your request is reviewed and the subscription method is confirmed manually.",
      step3_t: "Activate access",
      step3_p: "After confirmation, the admin sends you the joining instructions.",
      cta_h2: "Ready to follow the market with a clearer view?",
      cta_p: "Contact the admin to learn the subscription details and activation.",
      cta_btn: "Contact Mohamed ↗",
      journal_h2: "The Real Results Journal",
      journal_p: "Every closed trade is recorded here with its actual result — winning or losing — nothing hidden. The strategy has no proven edge yet — the journal is public: winners and losers together.",
      faq_h2: "Frequently Asked Questions",
      risk: "⚠️ <b>Risk warning:</b> This content is for information and analysis purposes only. It is not a guarantee of profit or personal investment advice. Trading involves high risk; never risk money you cannot afford to lose, and make sure you understand the risks before making any decision.",
      foot_line: "35 analysts · One view of the market",
      foot_rights: "© 2026 Gold Council. All rights reserved.",
      j_loading_stat: "Loading the journal",
      j_loading_body: "Loading the results journal from the Gold Council database…",
      faq_loading: "Loading the FAQ…",
      j_closed: "closed trades (distinct)",
      j_wins: "wins",
      j_losses: "losses",
      j_winrate: "Win rate:",
      j_avgr: "Avg return:",
      j_empty_h: "No closed trades yet",
      j_empty_p: "The council is in the paper-trading phase — every signal is recorded here with its actual result, winning or losing, as soon as it closes. No results are shown before they happen.",
      j_err: "Could not load the results journal — check your connection and reload the page.",
      j_updated: "Paper phase — no real money. Last updated: {date} Cairo time — data from the Gold Council database (Supabase).",
      th_date: "Date",
      th_tool: "Instrument",
      th_dir: "Direction",
      th_entry: "Entry",
      th_result: "Result",
      th_pnl: "Return",
      faq_empty: "No frequently asked questions yet.",
      faq_err: "Could not load the FAQ — please reload the page later."
    }
  };

  /* FAQ translations, keyed by the EXACT Arabic question in Supabase.
     [question, answer] in English. Unknown questions fall back to Arabic. */
  var FAQ_EN = {
    "هل التوصيات تداول حقيقي أم تجريبي؟": [
      "Are the signals real trading or demo?",
      "All signals are currently paper (demo) trades, and marked as such on every card. We do not sell paid signals before a documented paper month with a public journal."
    ],
    "كم توصية في اليوم؟": [
      "How many signals per day?",
      "At most 3 signals per day — a ceiling, not a quota. A day with no clear opportunities may have no signal at all."
    ],
    "كيف تصدر التوصية؟": [
      "How is a signal issued?",
      "35 analysis agents vote, then the arbiter consolidates, the devil's advocate attacks, the risk manager calculates entry, stop and targets, and the evaluator only allows publication at 70/100 or more. Mohamed then reviews it before publication."
    ],
    "هل البوت يتداول نيابة عني؟": [
      "Does the bot trade on my behalf?",
      "No, never. Gold Council gives documented signals only — it never executes any trade and never connects to any broker."
    ],
    "كيف أشترك؟": [
      "How do I subscribe?",
      "Contact Mohamed directly; after the transfer he activates you manually from the control panel. Payment is manual — there is no payment inside the bot."
    ],
    "كيف أتابع نتائجي؟": [
      "How do I track my results?",
      "With /stats for your personal record and /history for past signals. The journal shows winners and losers together."
    ],
    "أين أناقش التوصيات؟": [
      "Where do I discuss the signals?",
      "In the discussion group linked to the channel. Its link reaches you with the welcome message."
    ]
  };

  var DIR = {
    ar: { long: "شراء", short: "بيع" },
    en: { long: "Buy", short: "Sell" }
  };
  var RESULT = {
    ar: { tp1: "🎯 هدف أول", tp2: "🎯🎯 هدف ثانٍ", sl: "⛔ وقف خسارة", open: "⏳ مفتوحة", expired: "⌛ منتهية" },
    en: { tp1: "🎯 Take Profit 1", tp2: "🎯🎯 Take Profit 2", sl: "⛔ Stop Loss", open: "⏳ Open", expired: "⌛ Expired" }
  };

  var current = "ar";
  try {
    var saved = localStorage.getItem("gc-lang");
    if (saved === "en" || saved === "ar") current = saved;
  } catch (e) { /* private mode: stay Arabic */ }

  function t(key) {
    return (STR[current] && STR[current][key]) || STR.ar[key] || key;
  }

  function applyStatic() {
    var els = document.querySelectorAll("[data-i18n]");
    for (var i = 0; i < els.length; i++) els[i].textContent = t(els[i].getAttribute("data-i18n"));
    var htmlEls = document.querySelectorAll("[data-i18n-html]");
    for (var j = 0; j < htmlEls.length; j++) htmlEls[j].innerHTML = t(htmlEls[j].getAttribute("data-i18n-html"));
    var meta = document.querySelector('meta[name="description"]');
    if (meta) meta.setAttribute("content", t("meta_desc"));
    document.title = t("title");
    var btn = document.getElementById("lang-toggle");
    if (btn) btn.textContent = current === "ar" ? "🌐 English" : "🌐 العربية";
  }

  function setLang(l) {
    if (l !== "ar" && l !== "en") return;
    current = l;
    try { localStorage.setItem("gc-lang", l); } catch (e) { /* ignore */ }
    document.documentElement.lang = l;
    document.documentElement.dir = l === "ar" ? "rtl" : "ltr";
    applyStatic();
    document.dispatchEvent(new CustomEvent("gc:lang", { detail: { lang: l } }));
  }

  function faqPair(question, answer) {
    if (current === "en" && FAQ_EN[question]) return FAQ_EN[question];
    return [question, answer];
  }

  /* The script loads at the end of <body>, so the DOM is already there. */
  document.documentElement.lang = current;
  document.documentElement.dir = current === "ar" ? "rtl" : "ltr";
  applyStatic();
  var btn0 = document.getElementById("lang-toggle");
  if (btn0) btn0.addEventListener("click", function () { setLang(current === "ar" ? "en" : "ar"); });

  global.GC_I18N = {
    get lang() { return current; },
    t: t,
    setLang: setLang,
    faqPair: faqPair,
    dirLabel: function (d) { return (DIR[current] && DIR[current][d]) || d; },
    resultLabel: function (s) { return (RESULT[current] && RESULT[current][s]) || s; }
  };
})(window);
