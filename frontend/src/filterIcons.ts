import { CalendarDays, ChartNoAxesCombined, Layers3, SlidersHorizontal, Target, TrendingUp } from "lucide-react";

export const FILTER_ICONS = [
  { name: "trend", label: "Growth", Icon: TrendingUp },
  { name: "target", label: "Target", Icon: Target },
  { name: "chart", label: "Chart", Icon: ChartNoAxesCombined },
  { name: "calendar", label: "Calendar", Icon: CalendarDays },
  { name: "layers", label: "Layers", Icon: Layers3 },
  { name: "sliders", label: "Sliders", Icon: SlidersHorizontal },
] as const;

export type FilterIconName = typeof FILTER_ICONS[number]["name"];

export function filterIcon(name?: string) {
  return FILTER_ICONS.find((icon) => icon.name === name) ?? FILTER_ICONS[0];
}
