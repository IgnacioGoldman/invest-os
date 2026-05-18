import { Banknote, BriefcaseBusiness, Layers, ListOrdered, WalletCards } from "lucide-react";
import type { PortfolioSnapshot } from "../api";
import { formatMoney } from "../format";

type Props = {
  snapshot: PortfolioSnapshot;
  displayCurrency: string;
  displayRate: number;
};

export function SummaryCards({ snapshot, displayCurrency, displayRate }: Props) {
  const cards = [
    { label: "Net Worth", value: formatMoney(snapshot.total_net_worth * displayRate, displayCurrency), icon: WalletCards },
    { label: "Invested", value: formatMoney(snapshot.total_invested * displayRate, displayCurrency), icon: BriefcaseBusiness },
    { label: "Cash", value: formatMoney(snapshot.total_cash * displayRate, displayCurrency), icon: Banknote },
    { label: "Holdings", value: snapshot.holdings.length.toString(), icon: Layers },
    { label: "Open Orders", value: snapshot.open_orders.length.toString(), icon: ListOrdered },
  ];

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
}
