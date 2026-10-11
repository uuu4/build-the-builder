// The bank's services for the final case, on Cloudflare Workers. Filled from the case's service contract and test customers.
export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/" || url.pathname === "/health") {
      return Response.json({ ok: true, service: "mock", time: new Date().toISOString() });
    }
    return Response.json({ ok: false, error: "unknown path " + url.pathname }, { status: 404 });
  },
};
