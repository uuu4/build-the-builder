// Freya Bank's statement services for the final case, on Cloudflare Workers.
// Paths, request envelope and error bodies: the bank's service contract (2026-10-01), sections 1-6.
// Every answer, HTTP status and delay for the test customers: test-customers.json, served exactly.
import DATA from "./test-customers.json";

const BASE = "/voice/v1/";
const CUSTOMERS = DATA.customers;

// how each service finds its answer (test-customers.md) and what it answers when there is no record (contract section 4 and 6)
const SERVICES = {
  "cards.list":            { by: ["customer"],         required: ["customerNo"],              missing: [404, "FB_IVR_CHANNEL_102", "WARNING", "Müşteriye ait geçerli kart bilgisi bulunamadı."] },
  "cards.balance":         { by: ["card"],             required: ["cardNumber"],              missing: [404, "FB_IVR_CHANNEL_120", "WARNING", "Kart bakiye servisi hatası: kart bulunamadı"] },
  "statement.week.get":    { by: ["card"],             required: ["cardNumber"],              missing: [404, "FB_IVR_CHANNEL_121", "WARNING", "Ekstre haftası servisi hatası: kart bulunamadı"] },
  "statement.week.decide": { by: ["card", "week"],     required: ["cardNumber", "newStatementWeek", "statementDay"], missing: [400, "INVALID_ARGUMENTS_ERROR", "ERROR", "no statement preview for this card and week"] },
  "statement.week.change": { by: ["card", "week"],     required: ["cardNumber", "newStatementWeek", "statementDay"], missing: [400, "INVALID_ARGUMENTS_ERROR", "ERROR", "no statement change for this card and week"] },
  "contact.email.get":     { by: ["customer"],         required: ["customerNo", "intAddressInfoType"], missing: [400, "INVALID_ARGUMENTS_ERROR", "ERROR", "customer not found"] },
  "statement.pdf.send":    { by: ["customer"],         required: ["customerNo", "cardNumber", "currencyType", "statementDate", "emailAddress"], missing: [404, "FB_IVR_CHANNEL_107", "WARNING", "Pdf dokümanı bulunamadı"] },
};

const CORS = { "Access-Control-Allow-Origin": "*" };
let SEQ = 0;

function guid() {
  return (Date.now().toString(16) + (++SEQ).toString(16).padStart(6, "0")).padStart(32, "0").slice(-32);
}

function errorBody(code, type, message) {
  const g = guid();
  return { result: { guid: g, returnCode: code, messageText: message, code, message, type, details: { guid: g, rootCause: type === "ERROR" ? "TechnicalError" : "NotFoundException", errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } };
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json; charset=utf-8", ...CORS } });
}

const empty = (v) => v === undefined || v === null || String(v).trim() === "";
// the panel's "Test API Request" sends variables unfilled, e.g. "{{customerNumber}}"
const isTemplate = (v) => typeof v === "string" && (v.includes("{{") || v.includes("%7B%7B"));

function customerOf(data, cardNumber) {
  if (!empty(data.customerNo)) return CUSTOMERS.find((c) => String(c.customerNo) === String(data.customerNo).trim()) || null;
  // services called with a card only: the customer whose card list holds that card
  return CUSTOMERS.find((c) => ["cards.balance", "statement.week.get", "statement.week.decide", "statement.week.change"]
    .some((s) => c.services[s] && c.services[s][cardNumber])) || null;
}

function answer(name, data) {
  const svc = SERVICES[name];
  for (const f of svc.required) {
    if (empty(data[f])) return { http: 400, response: errorBody("INVALID_ARGUMENTS_ERROR", "ERROR", f + " cannot be empty") };
  }
  const miss = { http: svc.missing[0], response: errorBody(svc.missing[1], svc.missing[2], svc.missing[3]) };
  const card = empty(data.cardNumber) ? null : String(data.cardNumber).trim();
  const c = customerOf(data, card);
  if (!c) return miss;
  let e = c.services[name];
  if (!e) return miss;
  if (svc.by.includes("card") && e.http === undefined) e = e[card];
  if (!e) return miss;
  if (svc.by.includes("week") && e.http === undefined) e = e[String(Number(data.newStatementWeek))];
  if (!e || e.http === undefined) return miss;
  return e;
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: { ...CORS, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "*" } });
    }
    if (url.pathname === "/" || url.pathname === "/health") {
      return json({ ok: true, service: "Freya Bank statement services (mock)", base: BASE, services: Object.keys(SERVICES), customers: CUSTOMERS.length });
    }
    const name = url.pathname.startsWith(BASE) ? url.pathname.slice(BASE.length).replace(/\/+$/, "") : null;
    if (!name || !SERVICES[name]) return json(errorBody("NOT_FOUND", "ERROR", "unknown service " + url.pathname), 404);
    if (request.method !== "POST") return json(errorBody("INVALID_ARGUMENTS_ERROR", "ERROR", "use POST"), 400);
    let body = {};
    try { body = await request.json(); } catch { body = {}; }
    let data = (body && typeof body.data === "object" && body.data) ? body.data : {};
    if (Object.values(data).some(isTemplate)) {                 // panel test: answer for the first test customer and card
      const c = CUSTOMERS[0], cn = c.services["cards.list"].response.data.cards[0].cardNumber;
      data = { customerNo: c.customerNo, cardNumber: cn, newStatementWeek: 2, intAddressInfoType: "E", ...Object.fromEntries(Object.entries(data).filter(([, v]) => !isTemplate(v))) };
    }
    console.log(JSON.stringify({ service: name, data }));
    const e = answer(name, data);
    const wait = Number(e.delaySeconds ?? e.gecikmeSaniye ?? 0);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait * 1000));
    return json(e.response ?? e.yanit ?? null, e.http);
  },
};
