import { getServerSession } from "next-auth";
import { redirect } from "next/navigation";
import { authOptions } from "@/lib/auth";
import EmployeeDashboard from "@/components/EmployeeDashboard";

export default async function MePage() {
  const session = await getServerSession(authOptions);
  if (!session?.user) redirect("/login");
  return <EmployeeDashboard />;
}
