import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions, SessionUser } from "@/lib/auth";
import ManagerDashboard from "@/components/ManagerDashboard";

export default async function ManagerPage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login");
  if ((session.user as SessionUser).role !== "manager") redirect("/me");
  return <ManagerDashboard />;
}
