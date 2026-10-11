// The bank's services for the final case, on Cloudflare Workers.
// Generic part (written before the case opened): customer lookup, request log, write ledger, JSON replies.
// Case part (filled from the case's service contract and test customers): ID_FIELD, CUSTOMERS and ROUTES below.

// ---- case part -------------------------------------------------------------------------------------------
const ID_FIELD = "customer_id";          // the field every request names the customer with (from the contract)
const CUSTOMERS = [                      // from the test customers file
  // { customer_id: "c1", first_name: "...", ... }
];
const ROUTES = {                         // path -> handler(body, customer, helpers); one entry per service in the contract
  // "/verify_identity": (b, c, h) => ({ ok: true, ... }),
};
// ----------------------------------------------------------------------------------------------------------

const LEDGER = new Map();                // customer id -> writes this isolate has seen (promises, notes, ...)
let SEQ = 0;

function reply(obj, status = 200) {
  return new Response(JSON.stringify(obj), { status, headers: { "content-type": "application/json" } });
}

function findCustomer(body, url) {
  const id = (body && body[ID_FIELD]) || url.searchParams.get(ID_FIELD);
  return CUSTOMERS.find((c) => String(c[ID_FIELD]) === String(id)) || null;
}

function record(customer, kind, data) {
  const id = String(customer[ID_FIELD]);
  const entry = { n: ++SEQ, kind, at: new Date().toISOString(), ...data };
  if (!LEDGER.has(id)) LEDGER.set(id, []);
  LEDGER.get(id).push(entry);
  return entry;
}

function writes(customer, kind) {
  return (LEDGER.get(String(customer[ID_FIELD])) || []).filter((e) => !kind || e.kind === kind);
}

function norm(s) {
  return String(s ?? "").trim().toLowerCase().replace(/\s+/g, " ");
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";
    if (path === "/" || path === "/health") {
      return reply({ ok: true, service: "bank mock", routes: Object.keys(ROUTES), customers: CUSTOMERS.length });
    }
    if (path === "/_ledger") {               // for us, not in the contract: what was written, per customer
      return reply(Object.fromEntries(LEDGER));
    }
    let body = {};
    if (request.method !== "GET") {
      try { body = await request.json(); } catch { body = {}; }
    }
    const handler = ROUTES[path];
    console.log(JSON.stringify({ path, method: request.method, body }));
    if (!handler) return reply({ ok: false, error: "unknown service " + path }, 404);
    const customer = findCustomer(body, url);
    try {
      const out = await handler(body, customer, { url, record, writes, norm });
      return out instanceof Response ? out : reply(out);
    } catch (e) {
      console.log("handler error", path, String(e));
      return reply({ ok: false, error: "service error" }, 500);
    }
  },
};
