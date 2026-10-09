import { DashboardProvider } from "@/context/DashboardProvider";
import { DashboardShell } from "./DashboardShell";

export default function Page() {
  return (
    <DashboardProvider>
      <DashboardShell />
    </DashboardProvider>
  );
}
