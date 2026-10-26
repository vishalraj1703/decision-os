import type { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";
import { timingSafeEqual } from "crypto";

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

export interface Person { id: string; name: string; email: string; team: string; role: "manager" | "employee" }

export async function fetchPeople(): Promise<Person[]> {
  const r = await fetch(`${BACKEND_URL}/people`, { cache: "no-store" });
  if (!r.ok) throw new Error("backend unavailable");
  return r.json();
}

function sameSecret(a: string, b: string): boolean {
  const x = Buffer.from(a);
  const y = Buffer.from(b);
  return x.length === y.length && timingSafeEqual(x, y);
}

// Basic session auth (spec 9): two roles, no SSO. Demo accounts come from the backend roster
// and share one demo password from the environment.
export const authOptions: NextAuthOptions = {
  session: { strategy: "jwt", maxAge: 60 * 60 * 12 },
  pages: { signIn: "/login" },
  providers: [
    CredentialsProvider({
      name: "Demo account",
      credentials: { email: { label: "Email", type: "email" }, password: { label: "Password", type: "password" } },
      async authorize(creds) {
        const expected = process.env.DEMO_PASSWORD ?? "";
        if (!creds?.email || !creds?.password || !expected || !sameSecret(creds.password, expected)) return null;
        const people = await fetchPeople();
        const p = people.find((x) => x.email.toLowerCase() === creds.email.toLowerCase());
        if (!p) return null;
        return { id: p.id, name: p.name, email: p.email, role: p.role, team: p.team } as never;
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        const u = user as unknown as Person;
        token.role = u.role;
        token.team = u.team;
      }
      return token;
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as Record<string, unknown>).role = token.role;
        (session.user as Record<string, unknown>).team = token.team;
      }
      return session;
    },
  },
};

export type SessionUser = { name: string; email: string; role: "manager" | "employee"; team: string };
