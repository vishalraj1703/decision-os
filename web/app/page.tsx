import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions, SessionUser } from "@/lib/auth";

export default async function Home() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login");
  redirect((session.user as SessionUser).role === "manager" ? "/manager" : "/me");
}
