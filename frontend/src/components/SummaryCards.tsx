import { Banknote, BriefcaseBusiness, Layers, ListOrdered, WalletCards } from "lucide-react";
import { memo, useMemo } from "react";
import type { PortfolioSnapshot } from "../api";
import { formatMoneyPrivacy } from "../format";

type Props = {
  snapshot: PortfolioSnapshot;
  displayCurrency: string;
  displayRate: number;
  hideAbsoluteValues?: boolean;
};

export const SummaryCards = memo(function SummaryCards({
  snapshot,
  displayCurrency,
  displayRate,
  hideAbsoluteValues = false,
}: Props) {
  const cards = useMemo(
    () => [
      {
        label: "Net Worth",
        value: formatMoneyPrivacy(snapshot.total_net_worth * displayRate, displayCurrency, hideAbsoluteValues),
        icon: WalletCards,
      },
      {
        label: "Invested",
        value: formatMoneyPrivacy(snapshot.total_invested * displayRate, displayCurrency, hideAbsoluteValues),
        icon: BriefcaseBusiness,
      },
      {
        label: "Cash",
        value: formatMoneyPrivacy(snapshot.total_cash * displayRate, displayCurrency, hideAbsoluteValues),
        icon: Banknote,
      },
      { label: "Holdings", value: snapshot.holdings.length.toString(), icon: Layers },
      { label: "Open Orders", value: snapshot.open_orders.length.toString(), icon: ListOrdered },
    ],
    [displayCurrency, displayRate, hideAbsoluteValues, snapshot],
  );

  return (
    <section className="summary-grid">
      {cards.map((card) => {
        const Icon = card.icon;
        return (
          <article className="summary-card" key={card.label}>
            <div>
              <span>{card.label}</span>
              <strong>{card.value}</strong>
            </div>
            <Icon size={22} aria-hidden="true" />
          </article>
        );
      })}
    </section>
  );
});
