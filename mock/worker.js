// Freya Bank's statement services for the final case, on Cloudflare Workers.
// Table-driven: every answer, HTTP status and delay comes from test-customers.json (the bank's test environment).
// Paths and request field names come from the bank's IVR integration document (section 6): SERVICES and FIELDS below.
import DATA from "./test-customers.json";

// ---- from the integration document ------------------------------------------------------------------------
const SERVICES = {                       // service name -> path (method: POST with a JSON body; GET query also read)
  "cards.list": "/cards.list",
  "cards.balance": "/cards.balance",
  "statement.week.get": "/statement.week.get",
  "statement.week.decide": "/statement.week.decide",
  "statement.week.change": "/statement.week.change",
  "contact.email.get": "/contact.email.get",
  "statement.pdf.send": "/statement.pdf.send",
};
const FIELDS = {                         // request field names
  customer: ["customerNo", "customerNumber"],
  card: ["cardNumber"],
  week: ["newStatementWeek"],
};
// What the bank answers when it has no record (unknown customer or card). Shape of the test data's error answers.
function notFound(what) {
  return { http: 404, response: { data: null, result: { returnCode: "0", messageText: what + " not found", code: "0", message: what + " not found", type: "E", details: null } } };
}
// ----------------------------------------------------------------------------------------------------------

const CUSTOMERS = DATA.customers;
const BY_PATH = Object.fromEntries(Object.entries(SERVICES).map(([name, path]) => [path, name]));

function pick(body, names) {
  for (const n of names) if (body[n] !== undefined && body[n] !== null && body[n] !== "") return String(body[n]);
  return null;
}

function last4(s) {
  return String(s || "").replace(/\D/g, "").slice(-4);
}

// The entry under a card key: exact masked number first, then the one key with the same last four digits.
function byCard(table, card) {
  if (!table || card === null) return null;
  if (table[card]) return table[card];
  const same = Object.keys(table).filter((k) => last4(k) && last4(k) === last4(card));
  return same.length === 1 ? table[same[0]] : null;
}

function answer(name, body) {
  const custNo = pick(body, FIELDS.customer);
  const c = CUSTOMERS.find((x) => String(x.customerNo) === custNo);
  if (!c) return notFound("customer");
  let e = c.services[name];
  if (!e) return notFound("service record");
  if (e.http === undefined) {                       // keyed by card
    e = byCard(e, pick(body, FIELDS.card));
    if (!e) return notFound("card");
  }
  if (e.http === undefined) {                       // keyed by the requested week
    const w = pick(body, FIELDS.week);
    e = w !== null ? e[String(Number(w))] || e[w] : null;
    if (!e) return notFound("week");
  }
  return e;
}

function reply(e) {
  return new Response(JSON.stringify(e.response ?? e.yanit ?? null), { status: e.http, headers: { "content-type": "application/json; charset=utf-8" } });
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (path === "/" || path === "/health") {
      return Response.json({ ok: true, service: "Freya Bank statement services (mock)", services: SERVICES, customers: CUSTOMERS.length });
    }
    const name = BY_PATH[path];
    let body = Object.fromEntries(url.searchParams);
    if (request.method !== "GET") {
      try { body = { ...body, ...(await request.json()) }; } catch { /* no JSON body */ }
    }
    console.log(JSON.stringify({ path, name, body }));
    if (!name) return Response.json({ error: "unknown path " + path }, { status: 404 });
    const e = answer(name, body);
    const wait = Number(e.gecikmeSaniye ?? e.delaySeconds ?? 0);
    if (wait > 0) await new Promise((r) => setTimeout(r, wait * 1000));
    return reply(e);
  },
};
