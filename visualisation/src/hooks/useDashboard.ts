"use client";

import { useContext } from "react";

import {
  DashboardContext,
  type DashboardContextValue,
} from "@/context/DashboardProvider";

/**
 * Access the dashboard context. Throws if used outside <DashboardProvider>,
 * so sections can rely on a non-null value.
 */
export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (ctx === null) {
    throw new Error("useDashboard must be used within a DashboardProvider");
  }
  return ctx;
}
