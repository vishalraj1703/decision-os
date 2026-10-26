// Server-side proxy: the browser never talks to FastAPI directly. The session decides who
// the user is; FastAPI trusts that identity only because it carries the internal token.
import { getServerSession } from "next-auth";
import { NextRequest, NextResponse } from "next/server";
import { authOptions, BACKEND_URL } from "@/lib/auth";

const ALLOWED = /^(state|extract|items\/[\w-]+\/(status|resolve)|contradictions\/[\w-]+\/resolve|meetings\/[\w-]+\/source|notifications(\/read)?|admin\/(run-check|clock|reset|seed-demo)|health|demo-notes)$/;

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const session = await getServerSession(authOptions);
  if (!session?.user?.email) return NextResponse.json({ code: "UNAUTHENTICATED", message: "Please sign in." }, { status: 401 });
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!ALLOWED.test(joined)) return NextResponse.json({ code: "NOT_FOUND", message: "Not found." }, { status: 404 });
  const url = `${BACKEND_URL}/${joined}${req.nextUrl.search}`;
  const init: RequestInit = {
    method: req.method,
    headers: {
      "content-type": "application/json",
      "x-internal-token": process.env.INTERNAL_API_TOKEN ?? "",
      "x-user-email": session.user.email,
    },
    cache: "no-store",
  };
  if (req.method !== "GET") init.body = await req.text();
  try {
    const r = await fetch(url, init);
    const body = await r.text();
    return new NextResponse(body, { status: r.status, headers: { "content-type": r.headers.get("content-type") ?? "application/json" } });
  } catch {
    return NextResponse.json({ code: "BACKEND_DOWN", message: "The Decision OS backend is not running." }, { status: 502 });
  }
}

export { forward as GET, forward as POST, forward as PATCH };
