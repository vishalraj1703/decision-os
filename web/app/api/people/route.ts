import { NextResponse } from "next/server";
import { fetchPeople } from "@/lib/auth";

// Public: the demo roster (names, teams, roles) for the login picker. No secrets.
export async function GET() {
  try {
    const people = await fetchPeople();
    return NextResponse.json(people.map(({ name, email, team, role }) => ({ name, email, team, role })));
  } catch {
    return NextResponse.json({ code: "BACKEND_DOWN", message: "The Decision OS backend is not running." }, { status: 502 });
  }
}
