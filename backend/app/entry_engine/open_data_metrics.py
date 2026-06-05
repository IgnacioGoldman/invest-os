from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from app.entry_engine.open_data_models import (
    OpenDataCompanyContext,
    HistoricalPricePoint,
    LatestPrice,
    OpenDataMetric,
    OpenDataPeriodMetrics,
    OpenDataSnapshot,
)


REVENUE_CONCEPTS = (
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax",
    "SalesRevenueNet",
    "SalesRevenueGoodsNet",
    "Revenue",
    "RevenueFromContractsWithCustomers",
    "RevenueAndOperatingIncome",
    "RevenuesNetOfInterestExpense",
    "RevenueFromSaleOfGoods",
)
NET_INCOME_CONCEPTS = (
    "NetIncomeLoss",
    "ProfitLoss",
    "ProfitLossAttributableToOwnersOfParent",
    "ProfitLossAttributableToOrdinaryEquityHoldersOfParentEntity",
)
GROSS_PROFIT_CONCEPTS = ("GrossProfit",)
COST_OF_REVENUE_CONCEPTS = ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfSales", "CostOfMerchandiseSold")
OPERATING_INCOME_CONCEPTS = ("OperatingIncomeLoss", "ProfitLossFromOperatingActivities")
OPERATING_EXPENSES_CONCEPTS = ("OperatingExpenses",)
RESEARCH_DEVELOPMENT_EXPENSE_CONCEPTS = (
    "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
)
SELLING_GENERAL_ADMINISTRATIVE_EXPENSE_CONCEPTS = ("SellingGeneralAndAdministrativeExpense",)
OPERATING_CASH_FLOW_CONCEPTS = (
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    "CashFlowsFromUsedInOperatingActivities",
    "CashFlowsFromUsedInOperations",
)
CAPEX_CONCEPTS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "CapitalExpenditures",
    "PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities",
    "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets",
)
DILUTED_SHARES_CONCEPTS = (
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "AdjustedWeightedAverageShares",
    "WeightedAverageShares",
)
DILUTED_EPS_CONCEPTS = ("EarningsPerShareDiluted", "DilutedEarningsLossPerShare")
CASH_CONCEPTS = (
    "CashAndCashEquivalentsAtCarryingValue",
    "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    "CashCashEquivalentsAndShortTermInvestments",
    "CashAndCashEquivalents",
)
EQUITY_CONCEPTS = (
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "Equity",
    "EquityAttributableToOwnersOfParent",
)
DEPRECIATION_AMORTIZATION_CONCEPTS = (
    "Depreciation",
    "DepreciationExpense",
    "DepreciationPropertyPlantAndEquipment",
    "DepreciationPropertyPlantAndEquipmentIncludingRightofuseAssets",
    "AmortizationOfIntangibleAssets",
    "DepreciationDepletionAndAmortization",
    "DepreciationDepletionAndAmortizationExpense",
    "DepreciationAndAmortization",
    "DepreciationAndAmortisationExpense",
    "AdjustmentsForDepreciationAndAmortisationExpense",
    "AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
    "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss",
)

DEBT_COMPONENT_GROUPS = (
    ("LongTermDebtCurrent", "LongTermDebtNoncurrent"),
    ("ShortTermBorrowings", "LongTermDebtCurrent", "LongTermDebtNoncurrent"),
    ("ShortTermBorrowings", "LongTermDebt"),
    ("DebtCurrent", "LongTermDebtNoncurrent"),
    ("DebtCurrent", "LongTermDebt"),
    ("CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings", "NoncurrentBorrowings"),
    ("CurrentLeaseLiabilities", "NoncurrentLeaseLiabilities"),
)
DEBT_DIRECT_CONCEPTS = (
    "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "LongTermDebtAndCapitalLeaseObligations",
    "LongTermDebt",
    "DebtInstrumentCarryingAmount",
    "FinanceLeaseLiability",
    "LongTermDebtNoncurrent",
    "DebtCurrent",
    "Borrowings",
    "LongtermBorrowings",
    "LeaseLiabilities",
)

SEC_TAXONOMIES = ("us-gaap", "ifrs-full")
MONETARY_UNITS = ("USD", "EUR", "GBP", "DKK", "CHF", "CAD", "TWD", "JPY", "CNY", "HKD")
USD_UNITS = MONETARY_UNITS
SHARE_UNITS = ("shares",)
EPS_UNITS = tuple(f"{currency}/shares" for currency in MONETARY_UNITS)


@dataclass(frozen=True)
class FactPoint:
    taxonomy: str
    concept: str
    unit: str
    value: float
    start: date | None
    end: date
    filed: date | None
    form: str
    fp: str | None
    fy: int | None
    frame: str | None

    @property
    def duration_days(self) -> int | None:
        if self.start is None:
            return None
        return (self.end - self.start).days + 1


@dataclass(frozen=True)
class SelectedFact:
    value: float
    concept: str
    unit: str
    as_of: str
    source: str
    tier: str
    notes: str
    annual_used: bool = False


def compute_open_data_snapshot(
    *,
    ticker: str,
    cik: int | None,
    companyfacts: dict[str, Any],
    price: LatestPrice | None,
    price_history: list[HistoricalPricePoint] | None = None,
    exchange: str | None = None,
    country: str | None = None,
    sector: str | None = None,
    industry: str | None = None,
    forward_pe_estimate: OpenDataMetric | None = None,
    company_context: OpenDataCompanyContext | None = None,
    statement_currency_rates: dict[str, OpenDataMetric] | None = None,
    market_cap_estimate: OpenDataMetric | None = None,
    adr_ratio: float = 1.0,
    adr_ratio_source: str | None = None,
    generated_as_of: str | None = None,
) -> OpenDataSnapshot:
    as_of = generated_as_of or date.today().isoformat()
    name = companyfacts.get("entityName") if isinstance(companyfacts.get("entityName"), str) else None
    fx_rates = statement_currency_rates or {}

    revenue = _ttm_metric(companyfacts, REVENUE_CONCEPTS, USD_UNITS, "revenue_ttm", as_of)
    net_income = _ttm_metric(companyfacts, NET_INCOME_CONCEPTS, USD_UNITS, "net_income_ttm", as_of)
    operating_cash_flow = _ttm_metric(
        companyfacts,
        OPERATING_CASH_FLOW_CONCEPTS,
        USD_UNITS,
        "operating_cash_flow_ttm",
        as_of,
    )
    gross_profit = _ttm_metric(companyfacts, GROSS_PROFIT_CONCEPTS, USD_UNITS, "gross_profit_ttm", as_of)
    cost_of_revenue = _ttm_metric(companyfacts, COST_OF_REVENUE_CONCEPTS, USD_UNITS, "cost_of_revenue_ttm", as_of)
    if gross_profit.value is None and revenue.value is not None and cost_of_revenue.value is not None:
        gross_profit = _computed_metric(
            "gross_profit_ttm",
            revenue.value,
            cost_of_revenue.value,
            lambda sales, cost: sales - cost,
            source=f"{revenue.source}; {cost_of_revenue.source}",
            as_of=_max_as_of(revenue.as_of, cost_of_revenue.as_of),
            notes="Gross profit computed as revenue TTM minus cost of revenue TTM.",
            fallback_as_of=as_of,
        )
    operating_income = _ttm_metric(
        companyfacts,
        OPERATING_INCOME_CONCEPTS,
        USD_UNITS,
        "operating_income_ttm",
        as_of,
    )
    operating_expenses = _ttm_metric(companyfacts, OPERATING_EXPENSES_CONCEPTS, USD_UNITS, "operating_expenses_ttm", as_of)
    if operating_income.value is None and gross_profit.value is not None and operating_expenses.value is not None:
        operating_income = _computed_metric(
            "operating_income_ttm",
            gross_profit.value,
            operating_expenses.value,
            lambda profit, expenses: profit - expenses,
            source=f"{gross_profit.source}; {operating_expenses.source}",
            as_of=_max_as_of(gross_profit.as_of, operating_expenses.as_of),
            notes="Operating income computed as gross profit TTM minus SEC operating expenses TTM.",
            fallback_as_of=as_of,
        )
    if operating_income.value is None and gross_profit.value is not None:
        research_development = _ttm_metric(
            companyfacts,
            RESEARCH_DEVELOPMENT_EXPENSE_CONCEPTS,
            USD_UNITS,
            "research_development_expense_ttm",
            as_of,
        )
        selling_general_admin = _ttm_metric(
            companyfacts,
            SELLING_GENERAL_ADMINISTRATIVE_EXPENSE_CONCEPTS,
            USD_UNITS,
            "selling_general_administrative_expense_ttm",
            as_of,
        )
        if research_development.value is not None and selling_general_admin.value is not None:
            operating_income = _computed_metric(
                "operating_income_ttm",
                gross_profit.value,
                research_development.value,
                lambda profit, rd: profit - rd - (selling_general_admin.value or 0),
                source=f"{gross_profit.source}; {research_development.source}; {selling_general_admin.source}",
                as_of=_max_as_of(gross_profit.as_of, research_development.as_of, selling_general_admin.as_of),
                notes=(
                    "Proxy operating income computed as gross profit TTM minus SEC R&D and SG&A expense components."
                ),
                fallback_as_of=as_of,
                tier="proxy_estimate",
            )
    capex = _ttm_metric(companyfacts, CAPEX_CONCEPTS, USD_UNITS, "capex_ttm", as_of)
    if capex.value is not None and capex.value < 0:
        capex = capex.model_copy(
            update={
                "value": abs(capex.value),
                "notes": f"{capex.notes} Negative source value normalized to positive cash outflow.",
            }
        )

    revenue_growth_yoy = _growth_metric(companyfacts, REVENUE_CONCEPTS, USD_UNITS, "revenue_growth_yoy", 1, as_of)
    revenue_cagr_3y = _growth_metric(companyfacts, REVENUE_CONCEPTS, USD_UNITS, "revenue_cagr_3y", 3, as_of)
    eps_growth_yoy = _eps_growth_metric(companyfacts, "eps_growth_yoy", 1, as_of)
    eps_cagr_3y = _eps_growth_metric(companyfacts, "eps_cagr_3y", 3, as_of)

    shares = _shares_diluted_metric(companyfacts, as_of)
    cash = _latest_fact_metric(
        companyfacts,
        CASH_CONCEPTS,
        USD_UNITS,
        "cash",
        as_of,
        "Latest SEC cash or cash-and-equivalent balance fact.",
    )
    debt = _debt_metric(companyfacts, as_of)
    equity = _latest_fact_metric(
        companyfacts,
        EQUITY_CONCEPTS,
        USD_UNITS,
        "equity",
        as_of,
        "Latest SEC stockholders' equity fact.",
    )

    free_cash_flow = _computed_metric(
        "free_cash_flow_ttm",
        operating_cash_flow.value,
        capex.value,
        lambda ocf, capex_outflow: ocf - capex_outflow,
        source=f"{operating_cash_flow.source}; {capex.source}",
        as_of=_max_as_of(operating_cash_flow.as_of, capex.as_of),
        notes="Operating cash flow TTM minus capex TTM. Capex is treated as a positive cash outflow.",
        fallback_as_of=as_of,
    )

    gross_margin = _computed_metric(
        "gross_margin",
        gross_profit.value,
        revenue.value,
        lambda profit, sales: (profit / sales) * 100,
        source=f"{gross_profit.source}; {revenue.source}",
        as_of=_max_as_of(gross_profit.as_of, revenue.as_of),
        notes="Gross profit divided by revenue, expressed as a percentage.",
        fallback_as_of=as_of,
    )
    operating_margin = _computed_metric(
        "operating_margin",
        operating_income.value,
        revenue.value,
        lambda income, sales: (income / sales) * 100,
        source=f"{operating_income.source}; {revenue.source}",
        as_of=_max_as_of(operating_income.as_of, revenue.as_of),
        notes="Operating income divided by revenue, expressed as a percentage.",
        fallback_as_of=as_of,
    )
    net_margin = _computed_metric(
        "net_margin",
        net_income.value,
        revenue.value,
        lambda income, sales: (income / sales) * 100,
        source=f"{net_income.source}; {revenue.source}",
        as_of=_max_as_of(net_income.as_of, revenue.as_of),
        notes="Net income divided by revenue, expressed as a percentage.",
        fallback_as_of=as_of,
    )
    roe = _computed_metric(
        "roe",
        net_income.value,
        equity.value,
        lambda income, book_equity: (income / book_equity) * 100,
        source=f"{net_income.source}; {equity.source}",
        as_of=_max_as_of(net_income.as_of, equity.as_of),
        notes="Net income TTM divided by latest stockholders' equity, expressed as a percentage.",
        fallback_as_of=as_of,
    )
    debt_to_equity = _computed_metric(
        "debt_to_equity",
        debt.value,
        equity.value,
        lambda total_debt, book_equity: total_debt / book_equity,
        source=f"{debt.source}; {equity.source}",
        as_of=_max_as_of(debt.as_of, equity.as_of),
        notes="Latest debt divided by latest stockholders' equity.",
        fallback_as_of=as_of,
    )
    invested_capital = _computed_metric(
        "invested_capital_proxy",
        debt.value,
        equity.value,
        lambda total_debt, book_equity: total_debt + book_equity - (cash.value or 0),
        source=f"{debt.source}; {equity.source}; {cash.source}",
        as_of=_max_as_of(debt.as_of, equity.as_of, cash.as_of),
        notes="Proxy invested capital: debt plus equity minus cash.",
        fallback_as_of=as_of,
        tier="proxy_estimate",
    )
    roic = _computed_metric(
        "roic_proxy",
        operating_income.value,
        invested_capital.value,
        lambda income, capital: (income / capital) * 100,
        source=f"{operating_income.source}; {invested_capital.source}",
        as_of=_max_as_of(operating_income.as_of, invested_capital.as_of),
        notes="Proxy ROIC: operating income TTM divided by proxy invested capital. No tax adjustment is applied.",
        fallback_as_of=as_of,
        tier="proxy_estimate",
    )

    price_metrics = _price_opportunity_metrics(price_history or [], price, as_of)
    market_cap = _price_metric(
        "market_cap",
        price,
        shares.value,
        lambda latest_price, share_count: latest_price * (share_count / adr_ratio),
        source=f"{price.source if price else 'price_unavailable'}; {shares.source}",
        as_of=_max_as_of(price.as_of if price else as_of, shares.as_of),
        notes=_market_cap_notes(adr_ratio, adr_ratio_source),
        fallback_as_of=as_of,
    )
    if market_cap.value is None and market_cap_estimate is not None and market_cap_estimate.value is not None:
        market_cap = market_cap_estimate
    revenue_for_valuation = _metric_in_price_currency("revenue_ttm_price_currency", revenue, price, fx_rates, as_of)
    net_income_for_valuation = _metric_in_price_currency("net_income_ttm_price_currency", net_income, price, fx_rates, as_of)
    free_cash_flow_for_valuation = _metric_in_price_currency(
        "free_cash_flow_ttm_price_currency",
        free_cash_flow,
        price,
        fx_rates,
        as_of,
    )
    pe = (
        _valuation_input_unavailable("pe_ttm", net_income_for_valuation, as_of)
        if _is_currency_bridge_unavailable(net_income_for_valuation)
        else
        _computed_metric(
            "pe_ttm",
            market_cap.value,
            net_income_for_valuation.value,
            lambda market_value, income: market_value / income,
            source=f"{market_cap.source}; {net_income_for_valuation.source}",
            as_of=_max_as_of(market_cap.as_of, net_income_for_valuation.as_of),
            notes="Market cap divided by net income TTM.",
            fallback_as_of=as_of,
        )
    )
    price_to_sales = (
        _valuation_input_unavailable("price_to_sales_ttm", revenue_for_valuation, as_of)
        if _is_currency_bridge_unavailable(revenue_for_valuation)
        else
        _computed_metric(
            "price_to_sales_ttm",
            market_cap.value,
            revenue_for_valuation.value,
            lambda market_value, sales: market_value / sales,
            source=f"{market_cap.source}; {revenue_for_valuation.source}",
            as_of=_max_as_of(market_cap.as_of, revenue_for_valuation.as_of),
            notes="Market cap divided by revenue TTM.",
            fallback_as_of=as_of,
        )
    )
    fcf_yield = (
        _valuation_input_unavailable("fcf_yield", free_cash_flow_for_valuation, as_of)
        if _is_currency_bridge_unavailable(free_cash_flow_for_valuation)
        else
        _computed_metric(
            "fcf_yield",
            free_cash_flow_for_valuation.value,
            market_cap.value,
            lambda fcf, market_value: (fcf / market_value) * 100,
            source=f"{free_cash_flow_for_valuation.source}; {market_cap.source}",
            as_of=_max_as_of(free_cash_flow_for_valuation.as_of, market_cap.as_of),
            notes="Free cash flow TTM divided by market cap, expressed as a percentage.",
            fallback_as_of=as_of,
        )
    )

    forward_pe_proxy = _forward_pe_proxy(price, net_income, shares.value, eps_cagr_3y.value, fx_rates, as_of)
    forward_pe = (
        forward_pe_estimate
        if forward_pe_estimate is not None and forward_pe_estimate.value is not None
        else forward_pe_proxy
    )
    peg = (
        _unavailable("peg", "Positive 3-year EPS CAGR was unavailable; PEG is not meaningful.", as_of)
        if eps_cagr_3y.value is None or eps_cagr_3y.value <= 0
        else _computed_metric(
            "peg",
            pe.value,
            eps_cagr_3y.value,
            lambda pe_value, growth_pct: pe_value / growth_pct,
            source=f"{pe.source}; {eps_cagr_3y.source}",
            as_of=_max_as_of(pe.as_of, eps_cagr_3y.as_of),
            notes="Proxy PEG: trailing P/E divided by 3-year EPS CAGR percentage. This is not analyst-consensus PEG.",
            fallback_as_of=as_of,
            tier="proxy_estimate",
        )
    )
    depreciation_amortization = _ttm_metric(
        companyfacts,
        DEPRECIATION_AMORTIZATION_CONCEPTS,
        USD_UNITS,
        "depreciation_amortization_ttm",
        as_of,
    )
    ebitda = _computed_metric(
        "ebitda_proxy",
        operating_income.value,
        depreciation_amortization.value,
        lambda income, da: income + da,
        source=f"{operating_income.source}; {depreciation_amortization.source}",
        as_of=_max_as_of(operating_income.as_of, depreciation_amortization.as_of),
        notes="Proxy EBITDA: operating income plus depreciation/amortization where SEC facts are available.",
        fallback_as_of=as_of,
        tier="proxy_estimate",
    )
    ebitda_for_valuation = _metric_in_price_currency("ebitda_proxy_price_currency", ebitda, price, fx_rates, as_of)
    debt_for_valuation = _metric_in_price_currency("debt_price_currency", debt, price, fx_rates, as_of)
    cash_for_valuation = _metric_in_price_currency("cash_price_currency", cash, price, fx_rates, as_of)
    enterprise_value = (
        _valuation_input_unavailable("enterprise_value_proxy", debt_for_valuation, as_of)
        if _is_currency_bridge_unavailable(debt_for_valuation)
        else _valuation_input_unavailable("enterprise_value_proxy", cash_for_valuation, as_of)
        if _is_currency_bridge_unavailable(cash_for_valuation)
        else
        _computed_metric(
            "enterprise_value_proxy",
            market_cap.value,
            debt_for_valuation.value,
            lambda market_value, total_debt: market_value + total_debt - (cash_for_valuation.value or 0),
            source=f"{market_cap.source}; {debt_for_valuation.source}; {cash_for_valuation.source}",
            as_of=_max_as_of(market_cap.as_of, debt_for_valuation.as_of, cash_for_valuation.as_of),
            notes="Proxy enterprise value: market cap plus debt minus cash.",
            fallback_as_of=as_of,
            tier="proxy_estimate",
        )
    )
    ev_to_ebitda = _computed_metric(
        "ev_to_ebitda",
        enterprise_value.value,
        ebitda_for_valuation.value,
        lambda ev, ebitda_value: ev / ebitda_value,
        source=f"{enterprise_value.source}; {ebitda_for_valuation.source}",
        as_of=_max_as_of(enterprise_value.as_of, ebitda_for_valuation.as_of),
        notes="Proxy EV/EBITDA from open/free public facts.",
        fallback_as_of=as_of,
        tier="proxy_estimate",
    )
    historical_series = _historical_series(companyfacts, price_history or [], as_of)
    data_gaps = _data_gaps(historical_series, forward_pe_estimate, company_context, companyfacts)

    business_health = {
        "revenue_growth_yoy": revenue_growth_yoy,
        "revenue_cagr_3y": revenue_cagr_3y,
        "eps_growth_yoy": eps_growth_yoy,
        "eps_cagr_3y": eps_cagr_3y,
        "gross_margin": gross_margin,
        "operating_margin": operating_margin,
        "net_margin": net_margin,
        "free_cash_flow": free_cash_flow,
        "roe": roe,
        "roic": roic,
        "cash": cash,
        "debt": debt,
        "debt_to_equity": debt_to_equity,
    }
    price_opportunity = {
        "current_price": price_metrics["current_price"],
        "change_1d": price_metrics["change_1d"],
        "change_1w": price_metrics["change_1w"],
        "change_1m": price_metrics["change_1m"],
        "change_3m": price_metrics["change_3m"],
        "change_6m": price_metrics["change_6m"],
        "change_1y": price_metrics["change_1y"],
        "change_2y": price_metrics["change_2y"],
        "change_5y": price_metrics["change_5y"],
        "distance_from_ath": price_metrics["distance_from_ath"],
        "distance_from_52w_high": price_metrics["distance_from_52w_high"],
        "distance_from_52w_low": price_metrics["distance_from_52w_low"],
    }
    valuation = {
        "pe": pe,
        "forward_pe": forward_pe,
        "peg": peg,
        "price_to_sales": price_to_sales,
        "ev_to_ebitda": ev_to_ebitda,
        "fcf_yield": fcf_yield,
    }
    _mark_non_comparable_metrics(sector, industry, business_health, valuation, as_of)
    metrics = {
        "revenue_ttm": revenue,
        "net_income_ttm": net_income,
        "operating_cash_flow_ttm": operating_cash_flow,
        "capex_ttm": capex,
        "gross_profit_ttm": gross_profit,
        "cost_of_revenue_ttm": cost_of_revenue,
        "operating_income_ttm": operating_income,
        "shares_diluted": shares,
        "market_cap": market_cap,
        "revenue_growth_yoy": revenue_growth_yoy,
        "revenue_cagr_3y": revenue_cagr_3y,
        "eps_growth_yoy": eps_growth_yoy,
        "eps_cagr_3y": eps_cagr_3y,
        **business_health,
        **price_opportunity,
        **valuation,
        "free_cash_flow_ttm": free_cash_flow,
        "pe_ttm": pe,
        "price_to_sales_ttm": price_to_sales,
        "fcf_yield": fcf_yield,
        "forward_pe_proxy": forward_pe_proxy,
        "forward_pe_public_estimate": forward_pe_estimate
        or _unavailable("forward_pe_public_estimate", "Free public forward PE estimate was unavailable.", as_of),
        "peg_proxy": peg,
        "eps_growth_3y_proxy": eps_cagr_3y,
        "ev_to_ebitda_proxy": ev_to_ebitda,
    }

    return OpenDataSnapshot(
        ticker=ticker.upper(),
        name=name,
        cik=cik,
        exchange=exchange,
        country=country,
        sector=sector,
        industry=industry,
        business_health=business_health,
        price_opportunity=price_opportunity,
        valuation=valuation,
        historical_series=historical_series,
        company_context=company_context,
        data_gaps=data_gaps,
        metrics=metrics,
    )


def _ttm_metric(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    units: tuple[str, ...],
    metric_name: str,
    fallback_as_of: str,
) -> OpenDataMetric:
    annual_fallback: OpenDataMetric | None = None
    computed: OpenDataMetric | None = None
    for concept in concepts:
        points = _fact_points(companyfacts, concept, units)
        selected = _select_ttm(points)
        if selected:
            metric = OpenDataMetric(
                value=selected.value,
                source=selected.source,
                tier=selected.tier,  # type: ignore[arg-type]
                as_of=selected.as_of,
                notes=selected.notes,
            )
            if selected.tier == "computed_from_public_facts":
                if computed is None or metric.as_of > computed.as_of:
                    computed = metric
            elif annual_fallback is None or metric.as_of > annual_fallback.as_of:
                annual_fallback = metric
    if computed is not None and (annual_fallback is None or computed.as_of >= annual_fallback.as_of):
        return computed
    if annual_fallback is not None:
        return annual_fallback
    return _unavailable(metric_name, "SEC companyfacts did not include usable public facts for this metric.", fallback_as_of)


def _latest_fact_metric(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    units: tuple[str, ...],
    metric_name: str,
    fallback_as_of: str,
    notes: str,
) -> OpenDataMetric:
    for concept in concepts:
        points = _fact_points(companyfacts, concept, units)
        if not points:
            continue
        latest = max(points, key=_point_sort_key)
        return OpenDataMetric(
            value=latest.value,
            source=_source(latest),
            tier="exact_public_fact",
            as_of=latest.end.isoformat(),
            notes=notes,
        )
    return _unavailable(metric_name, "SEC companyfacts did not include a usable public fact.", fallback_as_of)


def _shares_diluted_metric(companyfacts: dict[str, Any], fallback_as_of: str) -> OpenDataMetric:
    exact = _latest_fact_metric(
        companyfacts,
        DILUTED_SHARES_CONCEPTS,
        SHARE_UNITS,
        "shares_diluted",
        fallback_as_of,
        "Latest diluted weighted-average share count from SEC companyfacts; not a live shares-outstanding feed.",
    )
    if exact.value is not None:
        return exact

    net_income = _latest_annual(_annual_points(companyfacts, NET_INCOME_CONCEPTS, USD_UNITS))
    eps = _latest_annual(_annual_points(companyfacts, DILUTED_EPS_CONCEPTS, EPS_UNITS))
    if net_income is None or eps is None or eps.value == 0:
        return exact
    if _period_year(net_income) != _period_year(eps):
        return exact
    return OpenDataMetric(
        value=net_income.value / eps.value,
        source=f"{_source(net_income)}; {_source(eps)}",
        tier="computed_from_public_facts",
        as_of=_max_as_of(net_income.end.isoformat(), eps.end.isoformat()),
        notes="Diluted shares computed from annual SEC net income divided by annual diluted EPS; not a live shares-outstanding feed.",
    )


def _growth_metric(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    units: tuple[str, ...],
    metric_name: str,
    years: int,
    fallback_as_of: str,
) -> OpenDataMetric:
    points = _annual_points(companyfacts, concepts, units)
    if len(points) <= years:
        return _unavailable(metric_name, f"{years + 1} annual SEC facts were unavailable.", fallback_as_of)
    latest = points[0]
    prior = _annual_point_for_fy(points, latest.fy - years if latest.fy else None) or points[years]
    if prior.value == 0 or latest.value <= 0 or prior.value <= 0:
        return _unavailable(metric_name, "Annual facts were not usable for growth calculation.", fallback_as_of)
    value = ((latest.value - prior.value) / abs(prior.value)) * 100 if years == 1 else (((latest.value / prior.value) ** (1 / years)) - 1) * 100
    label = "YoY growth" if years == 1 else f"{years}-year CAGR"
    return OpenDataMetric(
        value=value,
        source=f"{_source(latest)}; {_source(prior)}",
        tier="computed_from_public_facts",
        as_of=latest.end.isoformat(),
        notes=f"{label} computed from annual SEC facts.",
    )


def _eps_growth_metric(companyfacts: dict[str, Any], metric_name: str, years: int, fallback_as_of: str) -> OpenDataMetric:
    eps_points = _annual_points(companyfacts, DILUTED_EPS_CONCEPTS, EPS_UNITS)
    if len(eps_points) > years:
        latest = eps_points[0]
        prior = _annual_point_for_fy(eps_points, latest.fy - years if latest.fy else None) or eps_points[years]
        if latest.value > 0 and prior.value > 0:
            value = ((latest.value - prior.value) / abs(prior.value)) * 100 if years == 1 else (((latest.value / prior.value) ** (1 / years)) - 1) * 100
            label = "YoY diluted EPS growth" if years == 1 else f"{years}-year diluted EPS CAGR"
            return OpenDataMetric(
                value=value,
                source=f"{_source(latest)}; {_source(prior)}",
                tier="computed_from_public_facts",
                as_of=latest.end.isoformat(),
                notes=f"{label} computed from annual SEC diluted EPS facts.",
            )
        return _eps_not_meaningful_metric(metric_name, latest.value, prior.value, _source(latest), _source(prior), latest.end.isoformat(), years)

    net_income_points = _annual_points(companyfacts, NET_INCOME_CONCEPTS, USD_UNITS)
    share_points = _annual_points(companyfacts, DILUTED_SHARES_CONCEPTS, SHARE_UNITS)
    computed_eps = _computed_annual_eps(net_income_points, share_points)
    if len(computed_eps) > years:
        latest = computed_eps[0]
        prior = _computed_eps_for_fy(computed_eps, latest["fy"] - years if latest.get("fy") else None) or computed_eps[years]
        if latest["eps"] > 0 and prior["eps"] > 0:
            value = ((latest["eps"] - prior["eps"]) / abs(prior["eps"])) * 100 if years == 1 else (((latest["eps"] / prior["eps"]) ** (1 / years)) - 1) * 100
            label = "YoY EPS growth" if years == 1 else f"{years}-year EPS CAGR"
            return OpenDataMetric(
                value=value,
                source=f"{latest['source']}; {prior['source']}",
                tier="proxy_estimate",
                as_of=latest["as_of"],
                notes=f"Proxy {label} computed from SEC annual net income and diluted shares.",
            )
        return _eps_not_meaningful_metric(
            metric_name,
            latest["eps"],
            prior["eps"],
            latest["source"],
            prior["source"],
            latest["as_of"],
            years,
        )

    return _unavailable(metric_name, f"A positive {years}-year SEC EPS history was unavailable.", fallback_as_of)


def _eps_not_meaningful_metric(
    metric_name: str,
    latest_eps: float,
    prior_eps: float,
    latest_source: str,
    prior_source: str,
    as_of: str,
    years: int,
) -> OpenDataMetric:
    if latest_eps > 0 and prior_eps <= 0:
        label = "YoY EPS growth" if years == 1 else f"{years}-year EPS CAGR"
        notes = (
            f"{metric_name}: EPS turned positive from a loss-making comparison period "
            f"(latest {latest_eps:.4g}, comparison {prior_eps:.4g}); {label} is not meaningful."
        )
    elif latest_eps <= 0:
        notes = f"{metric_name}: EPS remains loss-making (latest {latest_eps:.4g}); EPS growth is not meaningful."
    else:
        notes = f"{metric_name}: Comparison EPS was non-positive ({prior_eps:.4g}); EPS growth is not meaningful."
    return OpenDataMetric(
        value=None,
        source=f"{latest_source}; {prior_source}",
        tier="unavailable_open_free",
        as_of=as_of,
        notes=notes,
    )


def _debt_metric(companyfacts: dict[str, Any], fallback_as_of: str) -> OpenDataMetric:
    for group in DEBT_COMPONENT_GROUPS:
        components = [
            _latest_fact_metric(
                companyfacts,
                (concept,),
                USD_UNITS,
                concept,
                fallback_as_of,
                f"Latest SEC {concept} debt component.",
            )
            for concept in group
        ]
        values = [component.value for component in components]
        as_of_dates = {component.as_of for component in components if component.value is not None}
        statement_currencies = {
            currency
            for component in components
            if component.value is not None
            for currency in _source_statement_currencies(component.source)
        }
        if (
            all(value is not None for value in values)
            and any(value for value in values)
            and len(as_of_dates) == 1
            and len(statement_currencies) <= 1
        ):
            return OpenDataMetric(
                value=sum(value or 0 for value in values),
                source="; ".join(component.source for component in components),
                tier="computed_from_public_facts",
                as_of=_max_as_of(*(component.as_of for component in components)),
                notes=f"Debt computed as sum of SEC debt components: {', '.join(group)}.",
            )

    debt = _latest_fact_across_concepts(
        companyfacts,
        DEBT_DIRECT_CONCEPTS,
        USD_UNITS,
        "debt",
        fallback_as_of,
        "Latest available SEC debt fact. This may include capital/finance lease obligations depending on the SEC tag.",
    )
    if debt.value is not None:
        return debt
    return _unavailable("debt", "SEC companyfacts did not include usable debt facts.", fallback_as_of)


def _latest_fact_across_concepts(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    units: tuple[str, ...],
    metric_name: str,
    fallback_as_of: str,
    notes: str,
) -> OpenDataMetric:
    candidates: list[FactPoint] = []
    for concept in concepts:
        candidates.extend(_fact_points(companyfacts, concept, units))
    if not candidates:
        return _unavailable(metric_name, "SEC companyfacts did not include a usable public fact.", fallback_as_of)
    latest = max(candidates, key=_point_sort_key)
    return OpenDataMetric(
        value=latest.value,
        source=_source(latest),
        tier="exact_public_fact",
        as_of=latest.end.isoformat(),
        notes=notes,
    )


def _historical_series(
    companyfacts: dict[str, Any],
    price_history: list[HistoricalPricePoint],
    fallback_as_of: str,
) -> dict[str, list[OpenDataPeriodMetrics]]:
    annual = _annual_fundamental_rows(companyfacts, fallback_as_of)
    valuations = _annual_valuation_rows(companyfacts, price_history, annual, fallback_as_of)
    ranges = _valuation_range_rows(valuations, fallback_as_of)
    return {
        "annual_fundamentals": annual,
        "valuation_history": valuations,
        "valuation_ranges": ranges,
    }


def _annual_fundamental_rows(companyfacts: dict[str, Any], fallback_as_of: str) -> list[OpenDataPeriodMetrics]:
    revenue = _annual_fact_map(companyfacts, REVENUE_CONCEPTS, USD_UNITS)
    cost_of_revenue = _annual_fact_map(companyfacts, COST_OF_REVENUE_CONCEPTS, USD_UNITS)
    gross_profit = _annual_fact_map(companyfacts, GROSS_PROFIT_CONCEPTS, USD_UNITS)
    operating_income = _annual_fact_map(companyfacts, OPERATING_INCOME_CONCEPTS, USD_UNITS)
    net_income = _annual_fact_map(companyfacts, NET_INCOME_CONCEPTS, USD_UNITS)
    operating_cash_flow = _annual_fact_map(companyfacts, OPERATING_CASH_FLOW_CONCEPTS, USD_UNITS)
    capex = _annual_fact_map(companyfacts, CAPEX_CONCEPTS, USD_UNITS)
    eps = _annual_fact_map(companyfacts, DILUTED_EPS_CONCEPTS, EPS_UNITS)
    shares = _annual_fact_map(companyfacts, DILUTED_SHARES_CONCEPTS, SHARE_UNITS)
    cash = _annual_fact_map(companyfacts, CASH_CONCEPTS, USD_UNITS)
    equity = _annual_fact_map(companyfacts, EQUITY_CONCEPTS, USD_UNITS)
    debt = _annual_debt_metrics(companyfacts, fallback_as_of)

    fiscal_years = sorted(set(revenue) | set(net_income) | set(eps), reverse=True)[:5]
    rows: list[OpenDataPeriodMetrics] = []
    for fy in sorted(fiscal_years):
        row: dict[str, OpenDataMetric] = {}
        row["revenue"] = _metric_from_point(revenue.get(fy), "revenue", fallback_as_of)
        row["eps_diluted"] = _metric_from_point(eps.get(fy), "eps_diluted", fallback_as_of)
        row["net_income"] = _metric_from_point(net_income.get(fy), "net_income", fallback_as_of)
        exact_shares = _metric_from_point(shares.get(fy), "shares_diluted", fallback_as_of)
        computed_shares = _computed_from_metrics(
            "shares_diluted",
            row["net_income"],
            row["eps_diluted"],
            lambda income, eps_value: income / eps_value,
            "Annual diluted shares computed as net income divided by diluted EPS.",
            fallback_as_of,
        )
        row["shares_diluted"] = exact_shares if exact_shares.value is not None else computed_shares
        row["eps_diluted_computed"] = _computed_from_metrics(
            "eps_diluted_computed",
            row["net_income"],
            row["shares_diluted"],
            lambda income, share_count: income / share_count,
            "Annual EPS computed as net income divided by diluted shares.",
            fallback_as_of,
            tier="proxy_estimate",
        )
        row["operating_income"] = _metric_from_point(operating_income.get(fy), "operating_income", fallback_as_of)
        row["operating_cash_flow"] = _metric_from_point(operating_cash_flow.get(fy), "operating_cash_flow", fallback_as_of)
        normalized_capex = _metric_from_point(capex.get(fy), "capex", fallback_as_of)
        if normalized_capex.value is not None and normalized_capex.value < 0:
            normalized_capex = normalized_capex.model_copy(update={"value": abs(normalized_capex.value)})
        row["capex"] = normalized_capex
        row["cash"] = _metric_from_point(cash.get(fy), "cash", fallback_as_of)
        row["debt"] = debt.get(fy) or _unavailable("debt", "Annual debt fact was unavailable.", fallback_as_of)
        row["equity"] = _metric_from_point(equity.get(fy), "equity", fallback_as_of)

        annual_gross_profit = gross_profit.get(fy)
        if annual_gross_profit is not None:
            row["gross_profit"] = _metric_from_point(annual_gross_profit, "gross_profit", fallback_as_of)
        else:
            row["gross_profit"] = _computed_from_metrics(
                "gross_profit",
                row["revenue"],
                _metric_from_point(cost_of_revenue.get(fy), "cost_of_revenue", fallback_as_of),
                lambda sales, cost: sales - cost,
                "Gross profit computed as annual revenue minus annual cost of revenue.",
                fallback_as_of,
            )
        row["free_cash_flow"] = _computed_from_metrics(
            "free_cash_flow",
            row["operating_cash_flow"],
            row["capex"],
            lambda ocf, capex_outflow: ocf - capex_outflow,
            "Free cash flow computed as annual operating cash flow minus annual capex.",
            fallback_as_of,
        )
        row["gross_margin"] = _computed_from_metrics(
            "gross_margin",
            row["gross_profit"],
            row["revenue"],
            lambda profit, sales: (profit / sales) * 100,
            "Annual gross margin.",
            fallback_as_of,
        )
        row["operating_margin"] = _computed_from_metrics(
            "operating_margin",
            row["operating_income"],
            row["revenue"],
            lambda income, sales: (income / sales) * 100,
            "Annual operating margin.",
            fallback_as_of,
        )
        row["net_margin"] = _computed_from_metrics(
            "net_margin",
            row["net_income"],
            row["revenue"],
            lambda income, sales: (income / sales) * 100,
            "Annual net margin.",
            fallback_as_of,
        )
        row["fcf_margin"] = _computed_from_metrics(
            "fcf_margin",
            row["free_cash_flow"],
            row["revenue"],
            lambda fcf, sales: (fcf / sales) * 100,
            "Annual free cash flow margin.",
            fallback_as_of,
        )
        row["roe"] = _computed_from_metrics(
            "roe",
            row["net_income"],
            row["equity"],
            lambda income, book_equity: (income / book_equity) * 100,
            "Annual net income divided by year-end equity.",
            fallback_as_of,
        )
        row["debt_to_equity"] = _computed_from_metrics(
            "debt_to_equity",
            row["debt"],
            row["equity"],
            lambda total_debt, book_equity: total_debt / book_equity,
            "Annual debt divided by year-end equity.",
            fallback_as_of,
        )
        as_of = _max_as_of(*(metric.as_of for metric in row.values()))
        rows.append(OpenDataPeriodMetrics(period=str(fy), as_of=as_of, metrics=row))
    return rows


def _annual_valuation_rows(
    companyfacts: dict[str, Any],
    price_history: list[HistoricalPricePoint],
    annual_rows: list[OpenDataPeriodMetrics],
    fallback_as_of: str,
) -> list[OpenDataPeriodMetrics]:
    depreciation = _annual_fact_map(companyfacts, DEPRECIATION_AMORTIZATION_CONCEPTS, USD_UNITS)
    prices = sorted((point for point in price_history if math.isfinite(point.close) and point.close > 0), key=lambda point: point.date)
    rows: list[OpenDataPeriodMetrics] = []

    for annual in annual_rows:
        try:
            fy = int(annual.period)
        except ValueError:
            continue
        period_end = date(fy, 12, 31)
        price_point = _historical_price_on_or_before(prices, period_end)
        price = _price_history_metric(price_point, fallback_as_of)
        share_metric = annual.metrics["shares_diluted"]
        market_cap = _computed_from_metrics(
            "market_cap",
            price,
            share_metric,
            lambda close, share_count: close * share_count,
            "Year-end close multiplied by annual diluted shares.",
            fallback_as_of,
        )
        net_income = annual.metrics["net_income"]
        revenue = annual.metrics["revenue"]
        fcf = annual.metrics["free_cash_flow"]
        debt = annual.metrics["debt"]
        cash = annual.metrics["cash"]
        operating_income = annual.metrics["operating_income"]
        depreciation_metric = _metric_from_point(depreciation.get(fy), "depreciation_amortization", fallback_as_of)
        ebitda = _computed_from_metrics(
            "ebitda_proxy",
            operating_income,
            depreciation_metric,
            lambda income, da: income + da,
            "Proxy annual EBITDA: operating income plus depreciation/amortization.",
            fallback_as_of,
            tier="proxy_estimate",
        )
        enterprise_value = (
            _currency_mismatch_metric_for_price_currency("enterprise_value", "USD", debt, cash, fallback_as_of=fallback_as_of)
            if _has_statement_currency_mismatch("USD", debt, cash)
            else _enterprise_value_from_metrics(market_cap, debt, cash, fallback_as_of)
        )
        row = {
            "year_end_price": price,
            "market_cap": market_cap,
            "pe": (
                _currency_mismatch_metric_for_price_currency("pe", "USD", net_income, fallback_as_of=fallback_as_of)
                if _has_statement_currency_mismatch("USD", net_income)
                else _computed_from_metrics("pe", market_cap, net_income, lambda value, income: value / income, "Historical PE from public facts.", fallback_as_of)
            ),
            "price_to_sales": (
                _currency_mismatch_metric_for_price_currency("price_to_sales", "USD", revenue, fallback_as_of=fallback_as_of)
                if _has_statement_currency_mismatch("USD", revenue)
                else _computed_from_metrics("price_to_sales", market_cap, revenue, lambda value, sales: value / sales, "Historical Price/Sales from public facts.", fallback_as_of)
            ),
            "fcf_yield": (
                _currency_mismatch_metric_for_price_currency("fcf_yield", "USD", fcf, fallback_as_of=fallback_as_of)
                if _has_statement_currency_mismatch("USD", fcf)
                else _computed_from_metrics("fcf_yield", fcf, market_cap, lambda free_cash_flow, value: (free_cash_flow / value) * 100, "Historical FCF yield from public facts.", fallback_as_of)
            ),
            "enterprise_value": enterprise_value,
            "ev_to_ebitda": _computed_from_metrics("ev_to_ebitda", enterprise_value, ebitda, lambda ev, ebitda_value: ev / ebitda_value, "Historical proxy EV/EBITDA from public facts.", fallback_as_of, tier="proxy_estimate"),
        }
        rows.append(OpenDataPeriodMetrics(period=str(fy), as_of=_max_as_of(*(metric.as_of for metric in row.values())), metrics=row))
    return rows


def _valuation_range_rows(
    valuation_rows: list[OpenDataPeriodMetrics],
    fallback_as_of: str,
) -> list[OpenDataPeriodMetrics]:
    metrics: dict[str, OpenDataMetric] = {}
    for metric_name in ("pe", "price_to_sales", "ev_to_ebitda", "fcf_yield"):
        values = [
            row.metrics[metric_name].value
            for row in valuation_rows
            if metric_name in row.metrics and row.metrics[metric_name].value is not None
        ]
        if not values:
            continue
        tier = "proxy_estimate" if metric_name == "ev_to_ebitda" else "computed_from_public_facts"
        metrics[f"{metric_name}_min"] = OpenDataMetric(value=min(values), source="historical_series", tier=tier, as_of=fallback_as_of, notes=f"Minimum historical {metric_name} across available annual rows.")
        metrics[f"{metric_name}_max"] = OpenDataMetric(value=max(values), source="historical_series", tier=tier, as_of=fallback_as_of, notes=f"Maximum historical {metric_name} across available annual rows.")
        metrics[f"{metric_name}_median"] = OpenDataMetric(value=_median(values), source="historical_series", tier=tier, as_of=fallback_as_of, notes=f"Median historical {metric_name} across available annual rows.")
    return [OpenDataPeriodMetrics(period="available_annual_rows", as_of=fallback_as_of, metrics=metrics)] if metrics else []


def _data_gaps(
    historical_series: dict[str, list[OpenDataPeriodMetrics]],
    forward_pe_estimate: OpenDataMetric | None,
    company_context: OpenDataCompanyContext | None,
    companyfacts: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    taxonomies = companyfacts.get("facts", {}) if isinstance(companyfacts.get("facts"), dict) else {}
    if "us-gaap" not in taxonomies and "ifrs-full" in taxonomies:
        gaps.append(
            "SEC companyfacts uses IFRS taxonomy. Foreign-currency fundamentals are supported; current valuation can use "
            "an explicit FX and ADR-ratio bridge, while historical valuation still needs historical FX handling."
        )
    annual = historical_series.get("annual_fundamentals", [])
    valuations = historical_series.get("valuation_history", [])
    if len(annual) < 5:
        gaps.append("Less than 5 annual fundamental rows were available.")
    if len(valuations) < 5:
        gaps.append("Less than 5 annual valuation rows were available.")
    for metric_name in ("revenue", "eps_diluted", "gross_margin", "operating_margin", "net_margin", "free_cash_flow", "cash", "debt"):
        available = sum(1 for row in annual if row.metrics.get(metric_name) and row.metrics[metric_name].value is not None)
        if available < 5:
            gaps.append(f"Only {available} annual values available for {metric_name}.")
    shares_available = sum(1 for row in annual if row.metrics.get("shares_diluted") and row.metrics["shares_diluted"].value is not None)
    if shares_available < 5:
        gaps.append(f"Only {shares_available} annual values available for shares_diluted.")
    eps_values = [
        row.metrics["eps_diluted"].value
        for row in annual
        if row.metrics.get("eps_diluted") and row.metrics["eps_diluted"].value is not None and row.metrics["eps_diluted"].value
    ]
    if eps_values and max(eps_values) / min(eps_values) > 10:
        gaps.append("Annual EPS series may cross stock-split accounting periods; use eps_diluted_computed and split-adjusted history with care.")
    for metric_name in ("pe", "price_to_sales", "ev_to_ebitda", "fcf_yield"):
        available = sum(1 for row in valuations if row.metrics.get(metric_name) and row.metrics[metric_name].value is not None)
        if available < 5:
            gaps.append(f"Only {available} historical valuation values available for {metric_name}.")
    if forward_pe_estimate is None or forward_pe_estimate.value is None:
        gaps.append("Free public forward PE estimate was unavailable; forward PE remains a SEC-derived proxy.")
    if company_context is None or not company_context.recent_filings:
        gaps.append("Company-specific SEC filing context was unavailable from the deterministic provider.")
    return gaps


def _price_opportunity_metrics(
    history: list[HistoricalPricePoint],
    latest_price: LatestPrice | None,
    fallback_as_of: str,
) -> dict[str, OpenDataMetric]:
    points = sorted((point for point in history if math.isfinite(point.close) and point.close > 0), key=lambda point: point.date)
    if points:
        latest = points[-1]
        price = latest.close
        as_of = latest.date
        source = latest.source
    elif latest_price is not None and math.isfinite(latest_price.price) and latest_price.price > 0:
        price = latest_price.price
        as_of = latest_price.as_of
        source = latest_price.source
    else:
        price = None
        as_of = fallback_as_of
        source = "open_data_provider"

    metrics: dict[str, OpenDataMetric] = {
        "current_price": OpenDataMetric(
            value=price,
            source=source,
            tier="exact_public_fact" if price is not None else "unavailable_open_free",
            as_of=as_of,
            notes="Latest open/free daily close price." if price is not None else "current_price: Open/free price was unavailable.",
        )
    }
    if price is None or not points:
        for name in (
            "change_1d",
            "change_1w",
            "change_1m",
            "change_3m",
            "change_6m",
            "change_1y",
            "change_2y",
            "change_5y",
            "distance_from_ath",
            "distance_from_52w_high",
            "distance_from_52w_low",
        ):
            metrics[name] = _unavailable(name, "Historical open/free prices were unavailable.", fallback_as_of)
        return metrics

    latest_date = _parse_date(points[-1].date) or date.today()
    periods = {
        "change_1d": 1,
        "change_1w": 7,
        "change_1m": 30,
        "change_3m": 91,
        "change_6m": 182,
        "change_1y": 365,
        "change_2y": 365 * 2,
        "change_5y": 365 * 5,
    }
    for name, days in periods.items():
        basis = _price_on_or_before(points, latest_date, days)
        metrics[name] = _price_change_metric(name, price, basis, source, as_of, fallback_as_of)

    ath = max((point.close for point in points), default=None)
    last_year_start = latest_date - timedelta(days=365)
    last_year = [point.close for point in points if (_parse_date(point.date) or date.min) >= last_year_start]
    high_52w = max(last_year) if last_year else None
    low_52w = min(last_year) if last_year else None
    metrics["distance_from_ath"] = _distance_metric("distance_from_ath", price, ath, source, as_of, "latest close to all-time high close", fallback_as_of)
    metrics["distance_from_52w_high"] = _distance_metric("distance_from_52w_high", price, high_52w, source, as_of, "latest close to 52-week high close", fallback_as_of)
    metrics["distance_from_52w_low"] = _distance_metric("distance_from_52w_low", price, low_52w, source, as_of, "latest close to 52-week low close", fallback_as_of)
    return metrics


def _price_on_or_before(points: list[HistoricalPricePoint], latest_date: date, days_back: int) -> float | None:
    target = latest_date - timedelta(days=days_back)
    candidates = [point for point in points if (_parse_date(point.date) or date.min) <= target]
    return candidates[-1].close if candidates else None


def _price_change_metric(
    metric_name: str,
    current_price: float,
    basis_price: float | None,
    source: str,
    as_of: str,
    fallback_as_of: str,
) -> OpenDataMetric:
    if basis_price in (None, 0):
        return _unavailable(metric_name, "Historical basis price was unavailable.", fallback_as_of)
    return OpenDataMetric(
        value=((current_price - basis_price) / basis_price) * 100,
        source=source,
        tier="computed_from_public_facts",
        as_of=as_of,
        notes="Price performance computed from open/free daily close history.",
    )


def _distance_metric(
    metric_name: str,
    current_price: float,
    reference_price: float | None,
    source: str,
    as_of: str,
    label: str,
    fallback_as_of: str,
) -> OpenDataMetric:
    if reference_price in (None, 0):
        return _unavailable(metric_name, f"Reference price for {label} was unavailable.", fallback_as_of)
    return OpenDataMetric(
        value=((current_price - reference_price) / reference_price) * 100,
        source=source,
        tier="computed_from_public_facts",
        as_of=as_of,
        notes=f"Distance from {label}, expressed as a percentage.",
    )


def _eps_growth_3y_proxy(companyfacts: dict[str, Any], fallback_as_of: str) -> OpenDataMetric:
    eps_points = _annual_points(companyfacts, DILUTED_EPS_CONCEPTS, EPS_UNITS)
    if len(eps_points) >= 4:
        latest = eps_points[0]
        prior = _annual_point_for_fy(eps_points, latest.fy - 3 if latest.fy else None) or eps_points[3]
        if latest.value > 0 and prior.value > 0:
            growth = (((latest.value / prior.value) ** (1 / 3)) - 1) * 100
            return OpenDataMetric(
                value=growth,
                source=f"{_source(latest)}; {_source(prior)}",
                tier="proxy_estimate",
                as_of=latest.end.isoformat(),
                notes="Proxy 3-year diluted EPS CAGR from SEC annual diluted EPS facts.",
            )

    net_income_points = _annual_points(companyfacts, NET_INCOME_CONCEPTS, USD_UNITS)
    share_points = _annual_points(companyfacts, DILUTED_SHARES_CONCEPTS, SHARE_UNITS)
    computed_eps = _computed_annual_eps(net_income_points, share_points)
    if len(computed_eps) >= 4:
        latest = computed_eps[0]
        prior = _computed_eps_for_fy(computed_eps, latest["fy"] - 3 if latest.get("fy") else None) or computed_eps[3]
        if latest["eps"] > 0 and prior["eps"] > 0:
            growth = (((latest["eps"] / prior["eps"]) ** (1 / 3)) - 1) * 100
            return OpenDataMetric(
                value=growth,
                source=f"{latest['source']}; {prior['source']}",
                tier="proxy_estimate",
                as_of=latest["as_of"],
                notes="Proxy 3-year diluted EPS CAGR computed from SEC annual net income and diluted shares.",
            )

    return _unavailable("eps_growth_3y_proxy", "A positive 3-year SEC EPS history was unavailable.", fallback_as_of)


def _forward_pe_proxy(
    price: LatestPrice | None,
    net_income_ttm: OpenDataMetric,
    shares_diluted: float | None,
    eps_growth_3y_pct: float | None,
    statement_currency_rates: dict[str, OpenDataMetric],
    fallback_as_of: str,
) -> OpenDataMetric:
    if price is None:
        return _unavailable("forward_pe_proxy", "Open/free latest price was unavailable.", fallback_as_of)
    net_income = _metric_in_price_currency(
        "net_income_ttm_price_currency",
        net_income_ttm,
        price,
        statement_currency_rates,
        fallback_as_of,
    )
    if net_income.value is None or shares_diluted in (None, 0):
        return _unavailable(
            "forward_pe_proxy",
            "Trailing EPS was unavailable, so a forward PE proxy could not be computed.",
            fallback_as_of,
        )
    trailing_eps = net_income.value / shares_diluted
    if trailing_eps <= 0:
        return _unavailable("forward_pe_proxy", "Trailing EPS is loss-making; forward PE proxy is not meaningful.", fallback_as_of)
    if eps_growth_3y_pct is None:
        return _unavailable(
            "forward_pe_proxy",
            "Positive 3-year EPS CAGR was unavailable, so a forward PE proxy is not meaningful.",
            fallback_as_of,
        )
    growth_decimal = eps_growth_3y_pct / 100
    if growth_decimal <= -1:
        return _unavailable("forward_pe_proxy", "Trailing EPS or EPS growth proxy was not usable.", fallback_as_of)
    forward_eps_proxy = trailing_eps * (1 + growth_decimal)
    return OpenDataMetric(
        value=price.price / forward_eps_proxy,
        source=f"{price.source}; {net_income.source}",
        tier="proxy_estimate",
        as_of=price.as_of,
        notes="Proxy forward P/E using trailing EPS grown by 3-year EPS CAGR. This is not analyst consensus.",
    )


def _source_statement_currencies(source: str) -> set[str]:
    currencies: set[str] = set()
    for raw_part in source.split(";"):
        part = raw_part.strip()
        if not part.startswith("sec_companyfacts:"):
            continue
        pieces = part.split(":")
        if len(pieces) < 3:
            continue
        unit = pieces[2]
        currency = unit.split("/", 1)[0].upper()
        if currency in MONETARY_UNITS:
            currencies.add(currency)
    return currencies


def _has_price_currency_mismatch(price: LatestPrice | None, *metrics: OpenDataMetric) -> bool:
    if price is None:
        return False
    return _has_statement_currency_mismatch(price.currency, *metrics)


def _has_statement_currency_mismatch(price_currency: str, *metrics: OpenDataMetric) -> bool:
    statement_currencies: set[str] = set()
    for metric in metrics:
        statement_currencies.update(_source_statement_currencies(metric.source))
    if not statement_currencies:
        return False
    return statement_currencies != {price_currency.upper()}


def _currency_mismatch_metric(
    metric_name: str,
    price: LatestPrice | None,
    *metrics: OpenDataMetric,
    fallback_as_of: str,
) -> OpenDataMetric:
    price_currency = price.currency.upper() if price is not None else "unknown"
    return _currency_mismatch_metric_for_price_currency(metric_name, price_currency, *metrics, fallback_as_of=fallback_as_of)


def _currency_mismatch_metric_for_price_currency(
    metric_name: str,
    price_currency: str,
    *metrics: OpenDataMetric,
    fallback_as_of: str,
) -> OpenDataMetric:
    statement_currencies = sorted({currency for metric in metrics for currency in _source_statement_currencies(metric.source)})
    statement_label = ", ".join(statement_currencies) if statement_currencies else "unknown"
    return _unavailable(
        metric_name,
        f"Statement currency ({statement_label}) does not match price currency ({price_currency}); FX and ADR ratio handling are required.",
        fallback_as_of,
    )


def _metric_in_price_currency(
    metric_name: str,
    metric: OpenDataMetric,
    price: LatestPrice | None,
    statement_currency_rates: dict[str, OpenDataMetric],
    fallback_as_of: str,
) -> OpenDataMetric:
    if metric.value is None or price is None:
        return metric
    statement_currencies = _source_statement_currencies(metric.source)
    if not statement_currencies or statement_currencies == {price.currency.upper()}:
        return metric
    if len(statement_currencies) != 1:
        return _currency_mismatch_metric(metric_name, price, metric, fallback_as_of=fallback_as_of)
    statement_currency = next(iter(statement_currencies))
    rate = statement_currency_rates.get(statement_currency)
    if rate is None or rate.value is None:
        return _currency_mismatch_metric(metric_name, price, metric, fallback_as_of=fallback_as_of)
    return OpenDataMetric(
        value=metric.value * rate.value,
        source=f"{metric.source}; {rate.source}",
        tier="computed_from_public_facts" if metric.tier != "unavailable_open_free" else metric.tier,
        as_of=_max_as_of(metric.as_of, rate.as_of),
        notes=(
            f"{metric.notes} Converted from {statement_currency} to {price.currency.upper()} using a public FX "
            f"reference rate for valuation."
        ),
    )


def _is_currency_bridge_unavailable(metric: OpenDataMetric) -> bool:
    return metric.value is None and "Statement currency" in metric.notes and "price currency" in metric.notes


def _mark_non_comparable_metrics(
    sector: str | None,
    industry: str | None,
    business_health: dict[str, OpenDataMetric],
    valuation: dict[str, OpenDataMetric],
    fallback_as_of: str,
) -> None:
    if not _is_financial_business(sector, industry):
        return
    replacements = {
        "business_health": {
            "gross_margin": "Gross margin is not meaningful for banks, insurers, brokers, and similar financial businesses.",
            "operating_margin": "Operating margin is not meaningful for many financial businesses because interest income, credit costs, and balance-sheet funding do not map cleanly to normal operating-company margins.",
            "free_cash_flow": "Free cash flow is not meaningful for many financial businesses because operating cash flow is distorted by balance-sheet lending, deposits, and financing activity.",
            "roic": "ROIC is not meaningful for many financial businesses because invested capital is not comparable to operating-company capital.",
        },
        "valuation": {
            "ev_to_ebitda": "EV/EBITDA is not meaningful for many financial businesses because debt is part of the operating model.",
            "fcf_yield": "FCF yield is not meaningful for many financial businesses because free cash flow is not comparable to operating-company free cash flow.",
        },
    }
    for key, notes in replacements["business_health"].items():
        metric = business_health.get(key)
        if metric is not None and metric.value is None:
            business_health[key] = _unavailable(key, notes, metric.as_of or fallback_as_of)
    for key, notes in replacements["valuation"].items():
        metric = valuation.get(key)
        if metric is not None and metric.value is None:
            valuation[key] = _unavailable(key, notes, metric.as_of or fallback_as_of)


def _is_financial_business(sector: str | None, industry: str | None) -> bool:
    sector_text = (sector or "").lower()
    industry_text = (industry or "").lower()
    if sector_text == "financials":
        return True
    financial_terms = (
        "bank",
        "banks",
        "insurance",
        "insurer",
        "broker",
        "brokers",
        "asset management",
        "capital markets",
        "credit",
        "savings institution",
        "investment banker",
    )
    return any(term in industry_text for term in financial_terms)


def _valuation_input_unavailable(metric_name: str, input_metric: OpenDataMetric, fallback_as_of: str) -> OpenDataMetric:
    _, _, reason = input_metric.notes.partition(": ")
    return _unavailable(metric_name, reason or input_metric.notes, fallback_as_of)


def _market_cap_notes(adr_ratio: float, adr_ratio_source: str | None) -> str:
    base = "Latest open/free price multiplied by SEC diluted weighted-average shares."
    if adr_ratio == 1:
        return f"{base} ADR/share ratio is 1:1." if adr_ratio_source else base
    return f"{base} Share count adjusted by ADR ratio of {adr_ratio:g} ordinary shares per ADS."


def _computed_metric(
    metric_name: str,
    left: float | None,
    right: float | None,
    compute: Any,
    *,
    source: str,
    as_of: str,
    notes: str,
    fallback_as_of: str,
    tier: str = "computed_from_public_facts",
) -> OpenDataMetric:
    if left is None or right in (None, 0):
        return _unavailable(metric_name, "Inputs required for this open/free computation were unavailable.", fallback_as_of)
    try:
        value = compute(left, right)
    except ZeroDivisionError:
        return _unavailable(metric_name, "Computation divided by zero.", fallback_as_of)
    if not _is_number(value):
        return _unavailable(metric_name, "Computation did not produce a finite value.", fallback_as_of)
    return OpenDataMetric(value=value, source=source, tier=tier, as_of=as_of, notes=notes)  # type: ignore[arg-type]


def _price_metric(
    metric_name: str,
    price: LatestPrice | None,
    right: float | None,
    compute: Any,
    *,
    source: str,
    as_of: str,
    notes: str,
    fallback_as_of: str,
) -> OpenDataMetric:
    if price is None:
        return _unavailable(metric_name, "Open/free latest price was unavailable.", fallback_as_of)
    return _computed_metric(
        metric_name,
        price.price,
        right,
        compute,
        source=source,
        as_of=as_of,
        notes=notes,
        fallback_as_of=fallback_as_of,
    )


def _select_ttm(points: list[FactPoint]) -> SelectedFact | None:
    annual = _latest_annual(points)
    if annual is None:
        return None

    latest_quarter = _latest_ytd_quarter_after(points, annual.end)
    if latest_quarter is None:
        return SelectedFact(
            value=annual.value,
            concept=annual.concept,
            unit=annual.unit,
            as_of=annual.end.isoformat(),
            source=_source(annual),
            tier="exact_public_fact",
            notes="Latest annual SEC fact used because a same-year quarterly TTM bridge was unavailable.",
            annual_used=True,
        )

    prior_quarter = _matching_prior_year_ytd(points, latest_quarter)
    if prior_quarter is None:
        return SelectedFact(
            value=annual.value,
            concept=annual.concept,
            unit=annual.unit,
            as_of=annual.end.isoformat(),
            source=_source(annual),
            tier="exact_public_fact",
            notes="Latest annual SEC fact used because prior-year quarterly bridge fact was unavailable.",
            annual_used=True,
        )

    return SelectedFact(
        value=annual.value + latest_quarter.value - prior_quarter.value,
        concept=annual.concept,
        unit=annual.unit,
        as_of=latest_quarter.end.isoformat(),
        source=f"{_source(annual)}; {_source(latest_quarter)}; {_source(prior_quarter)}",
        tier="computed_from_public_facts",
        notes="TTM computed as latest annual fact plus latest year-to-date quarter minus prior-year matching year-to-date quarter.",
    )


def _latest_annual(points: list[FactPoint]) -> FactPoint | None:
    candidates = [point for point in points if _is_annual(point)]
    if not candidates:
        return None
    return max(candidates, key=_point_sort_key)


def _latest_ytd_quarter_after(points: list[FactPoint], annual_end: date) -> FactPoint | None:
    candidates = [
        point
        for point in points
        if point.end > annual_end and point.fp in {"Q1", "Q2", "Q3"} and _is_10q(point) and _is_ytd_quarter(point)
    ]
    if not candidates:
        return None
    return max(candidates, key=_point_sort_key)


def _matching_prior_year_ytd(points: list[FactPoint], latest_quarter: FactPoint) -> FactPoint | None:
    candidates = [
        point
        for point in points
        if point.fp == latest_quarter.fp
        and _is_10q(point)
        and _is_ytd_quarter(point)
        and _is_prior_year(point, latest_quarter)
    ]
    if not candidates:
        return None
    return max(candidates, key=_point_sort_key)


def _is_prior_year(point: FactPoint, latest_quarter: FactPoint) -> bool:
    if point.end.year == latest_quarter.end.year - 1:
        return True
    if point.fy is not None and latest_quarter.fy is not None:
        return point.fy == latest_quarter.fy - 1
    return False


def _is_annual(point: FactPoint) -> bool:
    return point.fp == "FY" and _is_10k(point) and (point.duration_days is None or point.duration_days >= 300)


def _is_ytd_quarter(point: FactPoint) -> bool:
    if point.fp not in {"Q1", "Q2", "Q3"}:
        return False
    if point.duration_days is None:
        return True
    ranges = {"Q1": (60, 130), "Q2": (130, 230), "Q3": (220, 330)}
    low, high = ranges[point.fp]
    return low <= point.duration_days <= high


def _is_10k(point: FactPoint) -> bool:
    form = point.form.upper()
    return form.startswith("10-K") or form.startswith("20-F") or form.startswith("40-F")


def _is_10q(point: FactPoint) -> bool:
    return point.form.upper().startswith("10-Q")


def _annual_points(companyfacts: dict[str, Any], concepts: tuple[str, ...], units: tuple[str, ...]) -> list[FactPoint]:
    points: list[FactPoint] = []
    for concept in concepts:
        points.extend(point for point in _fact_points(companyfacts, concept, units) if _is_annual(point))
    points.sort(key=_point_sort_key, reverse=True)
    return points


def _annual_point_for_fy(points: list[FactPoint], fy: int | None) -> FactPoint | None:
    if fy is None:
        return None
    for point in points:
        if point.fy == fy:
            return point
    return None


def _computed_annual_eps(net_income_points: list[FactPoint], share_points: list[FactPoint]) -> list[dict[str, Any]]:
    share_by_fy = {point.fy: point for point in share_points if point.fy is not None}
    rows: list[dict[str, Any]] = []
    for income in net_income_points:
        if income.fy is None:
            continue
        shares = share_by_fy.get(income.fy)
        if shares is None or shares.value == 0:
            continue
        rows.append(
            {
                "fy": income.fy,
                "eps": income.value / shares.value,
                "as_of": income.end.isoformat(),
                "source": f"{_source(income)}; {_source(shares)}",
            }
        )
    rows.sort(key=lambda row: (row["fy"], row["as_of"]), reverse=True)
    return rows


def _computed_eps_for_fy(rows: list[dict[str, Any]], fy: int | None) -> dict[str, Any] | None:
    if fy is None:
        return None
    for row in rows:
        if row["fy"] == fy:
            return row
    return None


def _annual_fact_map(
    companyfacts: dict[str, Any],
    concepts: tuple[str, ...],
    units: tuple[str, ...],
) -> dict[int, FactPoint]:
    mapping: dict[int, FactPoint] = {}
    for point in _annual_points(companyfacts, concepts, units):
        period_year = _period_year(point)
        if period_year is None or period_year in mapping:
            continue
        mapping[period_year] = point
    return mapping


def _annual_debt_metrics(companyfacts: dict[str, Any], fallback_as_of: str) -> dict[int, OpenDataMetric]:
    result: dict[int, OpenDataMetric] = {}
    for group in DEBT_COMPONENT_GROUPS:
        component_maps = [_annual_fact_map(companyfacts, (concept,), USD_UNITS) for concept in group]
        common_years = set(component_maps[0])
        for component_map in component_maps[1:]:
            common_years &= set(component_map)
        for fy in sorted(common_years, reverse=True):
            if fy in result:
                continue
            points = [component_map[fy] for component_map in component_maps]
            end_dates = {point.end for point in points}
            units = {point.unit for point in points}
            if len(end_dates) != 1 or len(units) != 1:
                continue
            result[fy] = OpenDataMetric(
                value=sum(point.value for point in points),
                source="; ".join(_source(point) for point in points),
                tier="computed_from_public_facts",
                as_of=points[0].end.isoformat(),
                notes=f"Annual debt computed as sum of SEC debt components: {', '.join(group)}.",
            )

    for concept in DEBT_DIRECT_CONCEPTS:
        for fy, point in _annual_fact_map(companyfacts, (concept,), USD_UNITS).items():
            if fy in result:
                continue
            result[fy] = OpenDataMetric(
                value=point.value,
                source=_source(point),
                tier="exact_public_fact",
                as_of=point.end.isoformat(),
                notes=f"Annual debt SEC fact from {concept}. This may include capital/finance lease obligations depending on the SEC tag.",
            )
    return result


def _period_year(point: FactPoint) -> int | None:
    if point.frame and point.frame.startswith("CY") and len(point.frame) >= 6:
        try:
            return int(point.frame[2:6])
        except ValueError:
            pass
    return point.end.year


def _metric_from_point(point: FactPoint | None, metric_name: str, fallback_as_of: str) -> OpenDataMetric:
    if point is None:
        return _unavailable(metric_name, "Annual SEC fact was unavailable.", fallback_as_of)
    return OpenDataMetric(
        value=point.value,
        source=_source(point),
        tier="exact_public_fact",
        as_of=point.end.isoformat(),
        notes=f"Annual {metric_name} SEC fact.",
    )


def _computed_from_metrics(
    metric_name: str,
    left: OpenDataMetric,
    right: OpenDataMetric,
    compute: Any,
    notes: str,
    fallback_as_of: str,
    *,
    tier: str = "computed_from_public_facts",
) -> OpenDataMetric:
    if left.value is None or right.value in (None, 0):
        return _unavailable(metric_name, "Inputs required for this historical computation were unavailable.", fallback_as_of)
    try:
        value = compute(left.value, right.value)
    except ZeroDivisionError:
        return _unavailable(metric_name, "Historical computation divided by zero.", fallback_as_of)
    if not _is_number(value):
        return _unavailable(metric_name, "Historical computation did not produce a finite value.", fallback_as_of)
    return OpenDataMetric(
        value=value,
        source=f"{left.source}; {right.source}",
        tier=tier,  # type: ignore[arg-type]
        as_of=_max_as_of(left.as_of, right.as_of),
        notes=notes,
    )


def _enterprise_value_from_metrics(
    market_cap: OpenDataMetric,
    debt: OpenDataMetric,
    cash: OpenDataMetric,
    fallback_as_of: str,
) -> OpenDataMetric:
    if market_cap.value is None or debt.value is None or cash.value is None:
        return _unavailable("enterprise_value", "Inputs required for enterprise value were unavailable.", fallback_as_of)
    return OpenDataMetric(
        value=market_cap.value + debt.value - cash.value,
        source=f"{market_cap.source}; {debt.source}; {cash.source}",
        tier="proxy_estimate",
        as_of=_max_as_of(market_cap.as_of, debt.as_of, cash.as_of),
        notes="Historical proxy enterprise value: market cap plus debt minus cash.",
    )


def _historical_price_on_or_before(points: list[HistoricalPricePoint], target: date) -> HistoricalPricePoint | None:
    candidates = [point for point in points if (_parse_date(point.date) or date.min) <= target]
    return candidates[-1] if candidates else None


def _price_history_metric(point: HistoricalPricePoint | None, fallback_as_of: str) -> OpenDataMetric:
    if point is None:
        return _unavailable("year_end_price", "Historical price was unavailable.", fallback_as_of)
    return OpenDataMetric(
        value=point.close,
        source=point.source,
        tier="exact_public_fact",
        as_of=point.date,
        notes="Historical close on or before fiscal year end.",
    )


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _fact_points(companyfacts: dict[str, Any], concept: str, units: tuple[str, ...]) -> list[FactPoint]:
    points: list[FactPoint] = []
    facts = companyfacts.get("facts", {})
    if not isinstance(facts, dict):
        return points
    for taxonomy in SEC_TAXONOMIES:
        concept_data = facts.get(taxonomy, {}).get(concept, {})
        unit_data = concept_data.get("units", {}) if isinstance(concept_data, dict) else {}
        for unit in units:
            for row in unit_data.get(unit, []):
                point = _parse_fact_point(taxonomy, concept, unit, row)
                if point is not None:
                    points.append(point)
    return points


def _parse_fact_point(taxonomy: str, concept: str, unit: str, row: dict[str, Any]) -> FactPoint | None:
    value = row.get("val")
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not _is_number(number):
        return None
    end = _parse_date(row.get("end"))
    if end is None:
        return None
    fy = row.get("fy")
    try:
        fy_int = int(fy) if fy is not None else None
    except (TypeError, ValueError):
        fy_int = None
    return FactPoint(
        taxonomy=taxonomy,
        concept=concept,
        unit=unit,
        value=number,
        start=_parse_date(row.get("start")),
        end=end,
        filed=_parse_date(row.get("filed")),
        form=str(row.get("form") or ""),
        fp=str(row.get("fp") or "") or None,
        fy=fy_int,
        frame=str(row.get("frame") or "") or None,
    )


def _parse_date(raw: Any) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw))
    except ValueError:
        return None


def _source(point: FactPoint) -> str:
    return f"sec_companyfacts:{point.taxonomy}/{point.concept}:{point.unit}:{point.form}:{point.end.isoformat()}"


def _point_sort_key(point: FactPoint) -> tuple[date, date, str]:
    return (point.end, point.filed or date.min, point.frame or "")


def _max_as_of(*values: str) -> str:
    present = [value for value in values if value]
    return max(present) if present else date.today().isoformat()


def _unavailable(metric_name: str, notes: str, as_of: str) -> OpenDataMetric:
    return OpenDataMetric(
        value=None,
        source="open_data_provider",
        tier="unavailable_open_free",
        as_of=as_of,
        notes=f"{metric_name}: {notes}",
    )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value)
