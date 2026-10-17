# Revenue-led expansion: 77 to 200 stocks

Research date: 17 October 2026.

**123 proposed additions**, selected from 1,908 new listed issuers with cached SEC facts. 432 promising or previously growing candidates received current listing/filing checks; 232 met the conservative final screen. The original 77 stocks were excluded by ticker and SEC issuer identity.

This is a research shortlist. The active universe, SQLite database, and website exports have not been changed by this discovery work. The existing 77 stocks were retained as the starting universe and were not required to pass this new screen.

## Selection

- All six consecutive quarterly revenue YoY growth observations are **at least 8%**. The latest quarter is Strong at >=20%, otherwise Solid.
- Every quarter in the ten-quarter revenue comparison window has at least USD25m of revenue. This avoids selecting extreme percentage growth from a very small historical revenue base.
- Latest quarterly reporting period is no more than 140 days old, with consistent USD reporting across the comparison window. Rates of 100%+ are flagged, not automatically rejected.
- Current Nasdaq directory listing, market cap >=USD500m, price >=USD5, and matching SEC ticker. No sector quotas were imposed.
- The latest supported SEC financial filing accession must appear in revenue facts; its reporting date cannot exceed the extracted latest revenue quarter. A newer earnings 8-K with Item 2.02 sends a company to further review.
- Quarterly calculations and fiscal-calendar normalization reuse the application's existing revenue and momentum functions. Q4 may be annual revenue less nine-month revenue.

Rank is a screening order: 60% six-quarter median growth, 30% minimum growth in the latest three quarters, and 10% the fraction of six quarters above 8%; growth inputs are capped at 50% before scoring. Ties use the six-quarter minimum, then ticker. All selected companies have six qualifying quarters, so their consistency component is equal.

This evaluates reported revenue growth. It does not establish organic growth, profitability, financial strength, valuation, or expected stock returns. Acquisitions and currency translation can contribute to reported USD growth. Sector revenue definitions differ, especially for financial companies. Decelerating companies remain eligible when all six quarters meet the growth threshold.

## Coverage

Latest-quarter classifications: **111 Strong**, **12 Solid**.

| Sector (normalized Nasdaq labels) | Additions |
| --- | ---: |
| Technology | 42 |
| Healthcare | 27 |
| Consumer Cyclical | 17 |
| Industrials | 15 |
| Financials | 11 |
| Real Estate | 4 |
| Utilities | 3 |
| Materials | 1 |
| Communication Services | 1 |
| Miscellaneous | 1 |
| Energy | 1 |

## Proposed 123 additions

All growth values below are percentages. The six-quarter sequence runs oldest to newest; fiscal-quarter labels and underlying revenues are included in the JSON and CSV.

| Rank | Stock | Company | Latest period end | Latest YoY | 6Q median | Six quarterly YoY rates | Momentum |
| ---: | --- | --- | --- | ---: | ---: | --- | --- |
| 1 | [CRDO](https://www.sec.gov/Archives/edgar/data/1807794/000162828026060111/crdo-20260801.htm) | Credo Technology Group Holding Ltd | 2026-08-01 | 114.7% | 190.6% | 179.7, 273.6, 272.1, 201.5, 157.0, 114.7 | Decelerating |
| 2 | [CRWV](https://www.sec.gov/Archives/edgar/data/1769628/000176962826000366/crwv-20260630.htm) | CoreWeave, Inc. | 2026-06-30 | 112.5% | 123.1% | 420.4, 206.5, 133.7, 110.4, 111.6, 112.5 | Decelerating |
| 3 | [ALAB](https://www.sec.gov/Archives/edgar/data/1736297/000173629726000035/alab-20260630.htm) | Astera Labs, Inc. | 2026-06-30 | 104.5% | 104.2% | 144.3, 149.7, 103.9, 91.8, 93.4, 104.5 | Decelerating |
| 4 | [TGTX](https://www.sec.gov/Archives/edgar/data/1001316/000143774926025955/tgtx20260630_10q.htm) | TG THERAPEUTICS, INC. | 2026-06-30 | 70.3% | 84.2% | 90.4, 92.1, 92.8, 78.0, 69.6, 70.3 | Decelerating |
| 5 | [TARS](https://www.sec.gov/Archives/edgar/data/1819790/000181979026000064/tars-20260630.htm) | TARSUS PHARMACEUTICALS, INC. | 2026-06-30 | 69.4% | 137.5% | 183.7, 151.5, 146.7, 128.4, 106.9, 69.4 | Decelerating |
| 6 | [CDE](https://www.sec.gov/Archives/edgar/data/215466/000021546626000036/cde-20260630.htm) | COEUR MINING, INC. | 2026-06-30 | 125.9% | 118.7% | 69.0, 116.5, 76.9, 120.9, 137.8, 125.9 | Accelerating |
| 7 | [RDDT](https://www.sec.gov/Archives/edgar/data/1713445/000171344526000100/rddt-20260630.htm) | Reddit, Inc. | 2026-06-30 | 61.1% | 68.5% | 61.5, 77.7, 67.9, 69.7, 69.1, 61.1 | Stable |
| 8 | [PLMR](https://www.sec.gov/Archives/edgar/data/1761312/000119312526335508/plmr-20260630.htm) | Palomar Holdings, Inc. | 2026-06-30 | 54.7% | 57.4% | 47.3, 55.1, 64.8, 62.7, 59.7, 54.7 | Accelerating |
| 9 | [SITM](https://www.sec.gov/Archives/edgar/data/1451809/000145180926000060/sitm-20260630.htm) | SiTime Corporation | 2026-06-30 | 126.5% | 74.5% | 82.6, 58.4, 44.8, 66.3, 88.3, 126.5 | Accelerating |
| 10 | [CVNA](https://www.sec.gov/Archives/edgar/data/1690820/000169082026000055/cvna-20260630.htm) | CARVANA CO. | 2026-06-30 | 52.4% | 52.2% | 38.3, 41.9, 54.5, 58.0, 52.0, 52.4 | Accelerating |
| 11 | [ARQT](https://www.sec.gov/Archives/edgar/data/1787306/000178730626000051/arqt-20260630.htm) | ARCUTIS BIOTHERAPEUTICS, INC. | 2026-06-30 | 59.3% | 70.8% | 32.8, 164.1, 121.7, 81.5, 60.1, 59.3 | Decelerating |
| 12 | [RGLD](https://www.sec.gov/Archives/edgar/data/85535/000008553526000041/rgld-20260630.htm) | Royal Gold, Inc | 2026-06-30 | 114.9% | 57.7% | 29.9, 20.4, 30.0, 85.3, 142.5, 114.9 | Accelerating |
| 13 | [INSM](https://www.sec.gov/Archives/edgar/data/1104506/000110450626000041/insm-20260630.htm) | INSMED INC | 2026-06-30 | 296.1% | 102.5% | 22.9, 18.9, 52.4, 152.6, 229.6, 296.1 | Accelerating |
| 14 | [LITE](https://www.sec.gov/Archives/edgar/data/1633978/000162828026057358/lite-20260627.htm) | Lumentum Holdings Inc. | 2026-06-27 | 109.3% | 62.0% | 16.0, 55.9, 58.4, 65.5, 90.1, 109.3 | Accelerating |
| 15 | [APH](https://www.sec.gov/Archives/edgar/data/820313/000110465926089194/aph-20260630x10q.htm) | AMPHENOL CORPORATION | 2026-06-30 | 55.0% | 54.2% | 47.7, 56.5, 53.4, 49.1, 58.4, 55.0 | Stable |
| 16 | [TVTX](https://www.sec.gov/Archives/edgar/data/1438533/000143853326000063/tvtx-20260630.htm) | TRAVERE THERAPEUTICS, INC. | 2026-06-30 | 48.2% | 85.5% | 97.5, 111.5, 162.1, 73.4, 55.6, 48.2 | Decelerating |
| 17 | [SEI](https://www.sec.gov/Archives/edgar/data/1697500/000162828026054349/sei-20260630.htm) | SOLARIS ENERGY INFRASTRUCTURE, INC. | 2026-06-30 | 46.9% | 86.3% | 86.1, 102.1, 122.4, 86.6, 55.3, 46.9 | Decelerating |
| 18 | [LMND](https://www.sec.gov/Archives/edgar/data/1691421/000169142126000055/lmnd-20260630.htm) | Lemonade, Inc. | 2026-06-30 | 79.4% | 47.8% | 27.0, 34.5, 42.4, 53.3, 70.6, 79.4 | Accelerating |
| 19 | [AXSM](https://www.sec.gov/Archives/edgar/data/1579428/000119312526342360/axsm-20260630.htm) | AXSOME THERAPEUTICS, INC. | 2026-06-30 | 45.5% | 62.6% | 62.0, 72.1, 63.2, 65.0, 57.4, 45.5 | Decelerating |
| 20 | [CTRE](https://www.sec.gov/Archives/edgar/data/1590717/000162828026054284/ctre-20260630.htm) | CareTrust REIT, Inc. | 2026-06-30 | 43.5% | 54.2% | 53.2, 63.3, 71.2, 55.1, 47.8, 43.5 | Decelerating |
| 21 | [ASTH](https://www.sec.gov/Archives/edgar/data/1083446/000119312526342631/asth-20260630.htm) | Astrana Health, Inc. | 2026-06-30 | 48.5% | 51.0% | 53.4, 34.7, 99.7, 42.9, 55.6, 48.5 | Decelerating |
| 22 | [OUST](https://www.sec.gov/Archives/edgar/data/1816581/000162828026054467/oust-20260630.htm) | Ouster, Inc. | 2026-06-30 | 55.9% | 44.8% | 25.8, 29.9, 40.8, 106.6, 48.9, 55.9 | Accelerating |
| 23 | [RYTM](https://www.sec.gov/Archives/edgar/data/1649904/000162828026052533/rytm-20260630.htm) | RHYTHM PHARMACEUTICALS, INC. | 2026-06-30 | 46.9% | 50.6% | 25.9, 66.8, 54.3, 36.9, 83.8, 46.9 | Decelerating |
| 24 | [MIRM](https://www.sec.gov/Archives/edgar/data/1759425/000175942526000045/mirm-20260630.htm) | Mirum Pharmaceuticals, Inc. | 2026-06-30 | 37.9% | 48.5% | 61.2, 64.1, 47.2, 49.8, 43.3, 37.9 | Decelerating |
| 25 | [AAOI](https://www.sec.gov/Archives/edgar/data/1158114/000143774926026278/aaoi20260630_10q.htm) | Applied Optoelectronics, Inc. | 2026-06-30 | 86.4% | 84.3% | 145.5, 137.9, 82.1, 33.9, 51.4, 86.4 | Decelerating |
| 26 | [RBRK](https://www.sec.gov/Archives/edgar/data/1943896/000194389626000060/rbrk-20260731.htm) | RUBRIK, INC. | 2026-07-31 | 37.9% | 47.3% | 48.7, 51.2, 48.3, 46.3, 39.0, 37.9 | Decelerating |
| 27 | [DAVE](https://www.sec.gov/Archives/edgar/data/1841408/000119312526335154/dave-20260630.htm) | Dave Inc./DE | 2026-06-30 | 29.6% | 54.5% | 46.7, 64.5, 63.0, 62.4, 46.7, 29.6 | Decelerating |
| 28 | [FTAI](https://www.sec.gov/Archives/edgar/data/1590364/000162828026051412/ftai-20260630.htm) | FTAI AVIATION LTD. | 2026-06-30 | 40.9% | 47.8% | 53.7, 52.4, 43.2, 32.7, 65.5, 40.9 | Decelerating |
| 29 | [HALO](https://www.sec.gov/Archives/edgar/data/1159036/000115903626000104/halo-20260630.htm) | HALOZYME THERAPEUTICS, INC. | 2026-06-30 | 47.7% | 41.5% | 35.2, 40.8, 22.1, 51.6, 42.2, 47.7 | Accelerating |
| 30 | [ROAD](https://www.sec.gov/Archives/edgar/data/1718227/000162828026054661/road-20260630.htm) | Construction Partners, Inc. | 2026-06-30 | 28.2% | 47.3% | 53.9, 50.5, 67.2, 44.1, 34.6, 28.2 | Decelerating |
| 31 | [SNPS](https://www.sec.gov/Archives/edgar/data/883241/000088324126000025/snps-20260731.htm) | SYNOPSYS INC | 2026-07-31 | 42.4% | 39.8% | 10.3, 14.0, 37.8, 65.5, 41.9, 42.4 | Accelerating |
| 32 | [TEM](https://www.sec.gov/Archives/edgar/data/1717115/000119312526326090/tem-20260630.htm) | Tempus AI, Inc. | 2026-06-30 | 21.6% | 79.2% | 75.4, 89.6, 84.7, 83.0, 36.1, 21.6 | Decelerating |
| 33 | [RUN](https://www.sec.gov/Archives/edgar/data/1469367/000162828026053366/run-20260630.htm) | Sunrun Inc. | 2026-06-30 | 52.8% | 39.1% | 10.1, 8.7, 34.9, 123.5, 43.2, 52.8 | Accelerating |
| 34 | [RKLB](https://www.sec.gov/Archives/edgar/data/1819994/000181999426000062/rklb-20260630.htm) | Rocket Lab Corp | 2026-06-30 | 62.0% | 42.0% | 32.1, 36.0, 48.0, 35.7, 63.5, 62.0 | Accelerating |
| 35 | [OKE](https://www.sec.gov/Archives/edgar/data/1039684/000103968426000029/oke-20260630.htm) | ONEOK INC /NEW/ | 2026-06-30 | 52.8% | 57.0% | 68.2, 61.2, 71.9, 29.5, 19.6, 52.8 | Decelerating |
| 36 | [ALHC](https://www.sec.gov/Archives/edgar/data/1832466/000162828026051060/alhc-20260630.htm) | ALIGNMENT HEALTHCARE, INC. | 2026-06-30 | 31.6% | 44.0% | 47.5, 49.0, 43.5, 44.4, 33.3, 31.6 | Decelerating |
| 37 | [FIX](https://www.sec.gov/Archives/edgar/data/1035983/000110465926086258/fix-20260630x10q.htm) | COMFORT SYSTEMS USA, INC. | 2026-06-30 | 50.3% | 38.5% | 19.1, 20.1, 35.2, 41.7, 56.5, 50.3 | Accelerating |
| 38 | [NVT](https://www.sec.gov/Archives/edgar/data/1720635/000162828026051428/nvt-20260630.htm) | nVent Electric plc | 2026-06-30 | 52.8% | 38.3% | 10.5, 30.2, 34.8, 41.8, 53.5, 52.8 | Accelerating |
| 39 | [GH](https://www.sec.gov/Archives/edgar/data/1576280/000157628026000037/gh-20260630.htm) | GUARDANT HEALTH, INC. | 2026-06-30 | 44.3% | 38.9% | 20.8, 30.9, 38.5, 39.4, 48.3, 44.3 | Accelerating |
| 40 | [CLS](https://www.sec.gov/Archives/edgar/data/1030894/000103089426000044/cls-20260630.htm) | CELESTICA INC | 2026-06-30 | 62.4% | 35.7% | 19.9, 21.0, 27.8, 43.6, 52.8, 62.4 | Accelerating |
| 41 | [PL](https://www.sec.gov/Archives/edgar/data/1836833/000119312526382016/pl-20260731.htm) | Planet Labs PBC | 2026-07-31 | 58.1% | 36.8% | 9.6, 20.1, 32.6, 41.1, 42.1, 58.1 | Accelerating |
| 42 | [NTRA](https://www.sec.gov/Archives/edgar/data/1604821/000162828026054525/ntra-20260630.htm) | NATERA, INC. | 2026-06-30 | 37.7% | 37.1% | 36.5, 32.2, 34.7, 39.8, 38.8, 37.7 | Accelerating |
| 43 | [RBLX](https://www.sec.gov/Archives/edgar/data/1315098/000162828026051082/rblx-20260630.htm) | Roblox Corporation | 2026-06-30 | 35.9% | 37.6% | 29.2, 21.0, 48.0, 43.2, 39.3, 35.9 | Accelerating |
| 44 | [GKOS](https://www.sec.gov/Archives/edgar/data/1192448/000119312526324201/gkos-20260630.htm) | GLAUKOS Corp | 2026-06-30 | 49.5% | 36.9% | 24.6, 29.7, 38.1, 35.7, 41.2, 49.5 | Accelerating |
| 45 | [SSRM](https://www.sec.gov/Archives/edgar/data/921638/000092163826000081/ssrm-20260630.htm) | SSR Mining Inc. | 2026-06-30 | 9.5% | 55.7% | 37.5, 119.4, 49.9, 61.4, 83.7, 9.5 | Accelerating |
| 46 | [FA](https://www.sec.gov/Archives/edgar/data/1210677/000119312526338063/fa-20260630.htm) | First Advantage Corporation | 2026-06-30 | 14.9% | 71.1% | 109.3, 111.7, 105.5, 36.8, 8.6, 14.9 | Decelerating |
| 47 | [BKV](https://www.sec.gov/Archives/edgar/data/1838406/000110465926098821/bkv-20251231x10ka.htm) | BKV Corp | 2026-06-30 | 20.0% | 43.9% | 75.1, 100.5, 49.6, 30.9, 38.2, 20.0 | Decelerating |
| 48 | [VSEC](https://www.sec.gov/Archives/edgar/data/102752/000010275226000064/vsec-20260630.htm) | VSE CORPORATION | 2026-06-30 | 65.0% | 40.0% | 57.7, 41.1, 38.9, 32.4, 26.8, 65.0 | Decelerating |
| 49 | [LPLA](https://www.sec.gov/Archives/edgar/data/1397911/000162828026051542/lpla-20260630.htm) | LPL Financial Holdings Inc. | 2026-06-30 | 35.2% | 34.9% | 29.6, 30.8, 46.4, 40.4, 34.6, 35.2 | Accelerating |
| 50 | [AXON](https://www.sec.gov/Archives/edgar/data/1069183/000162828026053646/axon-20260630.htm) | AXON ENTERPRISE, INC. | 2026-06-30 | 35.3% | 33.3% | 31.3, 32.8, 30.6, 38.5, 33.7, 35.3 | Accelerating |
| 51 | [VIAV](https://www.sec.gov/Archives/edgar/data/912093/000162828026056765/viav-20260627.htm) | Viavi Solutions Inc. | 2026-06-27 | 52.5% | 31.0% | 15.8, 15.3, 25.6, 36.4, 42.8, 52.5 | Accelerating |
| 52 | [NET](https://www.sec.gov/Archives/edgar/data/1477333/000147733326000054/cloud-20260630.htm) | Cloudflare, Inc. | 2026-06-30 | 35.9% | 32.1% | 26.5, 27.8, 30.7, 33.6, 33.5, 35.9 | Accelerating |
| 53 | [ESTA](https://www.sec.gov/Archives/edgar/data/1688757/000168875726000050/esta-20260630.htm) | Establishment Labs Holdings Inc. | 2026-06-30 | 31.7% | 32.7% | 11.3, 16.3, 33.7, 45.2, 44.7, 31.7 | Accelerating |
| 54 | [ZETA](https://www.sec.gov/Archives/edgar/data/1851003/000119312526333902/zeta-20260630.htm) | ZETA GLOBAL HOLDINGS CORP. | 2026-06-30 | 43.5% | 35.5% | 35.6, 35.4, 25.7, 25.4, 49.9, 43.5 | Accelerating |
| 55 | [LIF](https://www.sec.gov/Archives/edgar/data/1581760/000158176026000141/lifx-20260630.htm) | Life360, Inc. | 2026-06-30 | 37.8% | 35.0% | 32.5, 36.0, 34.1, 26.4, 38.1, 37.8 | Accelerating |
| 56 | [BRO](https://www.sec.gov/Archives/edgar/data/79282/000119312526318251/bro-20260630.htm) | BROWN & BROWN, INC. | 2026-06-30 | 30.4% | 32.9% | 11.6, 9.1, 35.4, 35.8, 35.4, 30.4 | Accelerating |
| 57 | [FOUR](https://www.sec.gov/Archives/edgar/data/1794669/000179466926000045/four-20260630.htm) | SHIFT4 PAYMENTS, INC. | 2026-06-30 | 34.1% | 30.8% | 19.9, 16.8, 29.4, 33.9, 32.2, 34.1 | Accelerating |
| 58 | [DASH](https://www.sec.gov/Archives/edgar/data/1792789/000179278926000050/dash-20260630.htm) | DOORDASH, INC. | 2026-06-30 | 35.6% | 30.2% | 20.7, 24.9, 27.3, 37.7, 33.1, 35.6 | Accelerating |
| 59 | [ANIP](https://www.sec.gov/Archives/edgar/data/1023024/000102302426000069/anip-20260630.htm) | ANI PHARMACEUTICALS, INC | 2026-06-30 | 25.9% | 36.5% | 43.4, 53.1, 53.6, 29.6, 20.5, 25.9 | Decelerating |
| 60 | [FN](https://www.sec.gov/Archives/edgar/data/1408710/000140871026000028/fn-20260626.htm) | FABRINET | 2026-06-26 | 44.6% | 28.8% | 19.2, 20.8, 21.6, 35.9, 39.3, 44.6 | Accelerating |
| 61 | [SHOP](https://www.sec.gov/Archives/edgar/data/1594805/000159480526000047/shop-20260630.htm) | Shopify Inc. | 2026-06-30 | 33.7% | 31.3% | 26.8, 31.1, 31.5, 30.6, 34.3, 33.7 | Stable |
| 62 | [ADPT](https://www.sec.gov/Archives/edgar/data/1478320/000119312526332940/adpt-20260630.htm) | ADAPTIVE BIOTECHNOLOGIES CORPORATION | 2026-06-30 | 21.5% | 35.7% | 25.2, 36.3, 102.4, 51.0, 35.1, 21.5 | Stable |
| 63 | [PAY](https://www.sec.gov/Archives/edgar/data/1841156/000119312526330940/pay-20260630.htm) | Paymentus Holdings, Inc. | 2026-06-30 | 28.8% | 32.2% | 48.9, 41.9, 34.2, 28.1, 30.2, 28.8 | Decelerating |
| 64 | [HOOD](https://www.sec.gov/Archives/edgar/data/1783879/000178387926000114/hood-20260630.htm) | Robinhood Markets, Inc. | 2026-06-30 | 32.3% | 38.6% | 50.0, 45.0, 100.0, 26.5, 15.1, 32.3 | Decelerating |
| 65 | [SNOW](https://www.sec.gov/Archives/edgar/data/1640147/000164014726000037/snow-20260731.htm) | SNOWFLAKE INC. | 2026-07-31 | 35.1% | 31.0% | 25.7, 31.8, 28.7, 30.1, 33.5, 35.1 | Accelerating |
| 66 | [DUOL](https://www.sec.gov/Archives/edgar/data/1562088/000162828026053603/duol-20260630.htm) | Duolingo, Inc. | 2026-06-30 | 18.3% | 36.4% | 37.7, 41.5, 41.1, 35.0, 26.5, 18.3 | Decelerating |
| 67 | [LASR](https://www.sec.gov/Archives/edgar/data/1124796/000112479626000038/lasr-20260630.htm) | NLIGHT, INC. | 2026-06-30 | 33.8% | 28.0% | 16.0, 22.2, 18.9, 71.3, 55.2, 33.8 | Accelerating |
| 68 | [IOT](https://www.sec.gov/Archives/edgar/data/1642896/000162828026060909/iot-20260801.htm) | SAMSARA INC. | 2026-08-01 | 29.9% | 30.1% | 30.7, 30.4, 29.2, 28.3, 30.5, 29.9 | Stable |
| 69 | [ECG](https://www.sec.gov/Archives/edgar/data/2015845/000201584526000050/ecg-20260630.htm) | Everus Construction Group, Inc. | 2026-06-30 | 33.7% | 31.6% | 32.1, 31.0, 29.7, 33.2, 25.4, 33.7 | Stable |
| 70 | [OSCR](https://www.sec.gov/Archives/edgar/data/1568651/000156865126000069/oscr-20260630.htm) | Oscar Health, Inc. | 2026-06-30 | 70.4% | 35.6% | 42.2, 29.0, 23.2, 17.3, 52.6, 70.4 | Accelerating |
| 71 | [KVYO](https://www.sec.gov/Archives/edgar/data/1835830/000183583026000040/kvyo-20260630.htm) | Klaviyo, Inc. | 2026-06-30 | 26.4% | 30.8% | 33.3, 31.9, 32.2, 29.6, 27.9, 26.4 | Decelerating |
| 72 | [BROS](https://www.sec.gov/Archives/edgar/data/1866581/000186658126000133/bros-20260630.htm) | DUTCH BROS INC. | 2026-06-30 | 32.5% | 29.3% | 29.1, 28.0, 25.2, 29.4, 30.8, 32.5 | Stable |
| 73 | [GRND](https://www.sec.gov/Archives/edgar/data/1820144/000182014426000025/grnd-20260630.htm) | Grindr Inc. | 2026-06-30 | 32.5% | 29.3% | 24.7, 26.6, 29.6, 29.0, 38.3, 32.5 | Accelerating |
| 74 | [LGND](https://www.sec.gov/Archives/edgar/data/886163/000088616326000044/lgnd-20260630.htm) | LIGAND PHARMACEUTICALS INCORPORATED | 2026-06-30 | 33.7% | 36.6% | 46.3, 14.7, 122.8, 39.4, 14.1, 33.7 | Decelerating |
| 75 | [UI](https://www.sec.gov/Archives/edgar/data/1511737/000151173726000056/ubnt-20260630.htm) | UBIQUITI INC. | 2026-06-30 | 23.5% | 34.0% | 34.7, 49.6, 33.3, 35.8, 18.7, 23.5 | Decelerating |
| 76 | [XMTR](https://www.sec.gov/Archives/edgar/data/1657573/000119312526332776/xmtr-20260630.htm) | XOMETRY, INC. | 2026-06-30 | 41.1% | 28.5% | 23.1, 22.6, 27.5, 29.5, 35.9, 41.1 | Accelerating |
| 77 | [TMDX](https://www.sec.gov/Archives/edgar/data/1756262/000119312526332843/tmdx-20260630.htm) | TransMedics Group, Inc. | 2026-06-30 | 20.7% | 32.2% | 48.2, 37.7, 32.2, 32.2, 21.2, 20.7 | Decelerating |
| 78 | [PODD](https://www.sec.gov/Archives/edgar/data/1145197/000114519726000169/podd-20260630.htm) | INSULET CORPORATION | 2026-06-30 | 23.5% | 30.5% | 28.8, 32.9, 29.9, 31.2, 33.9, 23.5 | Stable |
| 79 | [NBIX](https://www.sec.gov/Archives/edgar/data/914475/000091447526000037/nbix-20260630.htm) | NEUROCRINE BIOSCIENCES INC | 2026-06-30 | 39.5% | 28.1% | 11.1, 16.5, 27.8, 28.3, 42.2, 39.5 | Accelerating |
| 80 | [DY](https://www.sec.gov/Archives/edgar/data/67215/000006721526000043/dy-20260801.htm) | DYCOM INDUSTRIES, INC. | 2026-08-01 | 45.6% | 24.5% | 10.2, 14.5, 14.1, 34.4, 56.1, 45.6 | Accelerating |
| 81 | [MTSI](https://www.sec.gov/Archives/edgar/data/1493594/000149359426000038/mtsi-20260703.htm) | MACOM Technology Solutions Holdings, Inc. | 2026-07-03 | 35.8% | 30.1% | 30.2, 32.3, 30.1, 24.5, 22.5, 35.8 | Decelerating |
| 82 | [FLYW](https://www.sec.gov/Archives/edgar/data/1580560/000158056026000016/flyw-20260630.htm) | FLYWIRE CORPORATION | 2026-06-30 | 27.2% | 27.4% | 17.0, 27.2, 27.6, 34.0, 41.0, 27.2 | Accelerating |
| 83 | [AMSC](https://www.sec.gov/Archives/edgar/data/880807/000143774926025922/amsc20260630_10q.htm) | AMERICAN SUPERCONDUCTOR CORP /DE/ | 2026-06-30 | 30.0% | 29.8% | 58.6, 79.6, 20.9, 21.4, 29.6, 30.0 | Decelerating |
| 84 | [ARES](https://www.sec.gov/Archives/edgar/data/1176948/000162828026054538/ares-20260630.htm) | ARES MANAGEMENT CORPORATION | 2026-06-30 | 24.3% | 27.6% | 36.5, 19.0, 36.9, 25.8, 29.3, 24.3 | Decelerating |
| 85 | [MPWR](https://www.sec.gov/Archives/edgar/data/1280452/000162828026053275/mpwr-20260630.htm) | Monolithic Power Systems, Inc. | 2026-06-30 | 47.6% | 28.6% | 39.2, 31.0, 18.9, 20.8, 26.1, 47.6 | Decelerating |
| 86 | [BRZE](https://www.sec.gov/Archives/edgar/data/1676238/000167623826000040/brze-20260731.htm) | Braze, Inc. | 2026-07-31 | 26.2% | 25.8% | 19.6, 23.8, 25.5, 27.9, 30.2, 26.2 | Accelerating |
| 87 | [RSI](https://www.sec.gov/Archives/edgar/data/1793659/000179365926000048/rsi-20260630.htm) | Rush Street Interactive, Inc. | 2026-06-30 | 46.3% | 25.0% | 20.7, 22.2, 19.7, 27.8, 41.1, 46.3 | Accelerating |
| 88 | [WGS](https://www.sec.gov/Archives/edgar/data/1818331/000162828026051878/wgs-20260630.htm) | GeneDx Holdings Corp. | 2026-06-30 | 11.4% | 33.0% | 39.6, 45.6, 51.9, 26.5, 17.4, 11.4 | Decelerating |
| 89 | [FROG](https://www.sec.gov/Archives/edgar/data/1800667/000119312526340294/frog-20260630.htm) | JFrog Ltd. | 2026-06-30 | 28.7% | 25.4% | 22.0, 23.5, 25.5, 25.2, 25.8, 28.7 | Stable |
| 90 | [EVC](https://www.sec.gov/Archives/edgar/data/1109116/000119312526342382/evc-20260630.htm) | ENTRAVISION COMMUNICATIONS CORPORATION | 2026-06-30 | 126.2% | 24.9% | 17.5, 21.9, 24.2, 25.6, 114.4, 126.2 | Accelerating |
| 91 | [COMP](https://www.sec.gov/Archives/edgar/data/1563190/000156319026000143/comp-20260630.htm) | COMPASS, INC. | 2026-06-30 | 109.0% | 26.1% | 28.6, 21.1, 23.6, 23.1, 99.4, 109.0 | Accelerating |
| 92 | [ZS](https://www.sec.gov/Archives/edgar/data/1713683/000171368326000157/zs-20260731.htm) | Zscaler Inc | 2026-07-31 | 24.9% | 25.2% | 22.6, 21.3, 25.5, 25.9, 25.4, 24.9 | Stable |
| 93 | [PRCT](https://www.sec.gov/Archives/edgar/data/1588978/000158897826000030/prct-20260630.htm) | PROCEPT BioRobotics Corporation | 2026-06-30 | 19.3% | 31.5% | 55.3, 48.4, 42.8, 11.9, 20.2, 19.3 | Decelerating |
| 94 | [MDB](https://www.sec.gov/Archives/edgar/data/1441816/000162828026059830/mdb-20260731.htm) | MONGODB, INC. | 2026-07-31 | 30.5% | 24.5% | 21.9, 23.7, 18.7, 26.7, 25.2, 30.5 | Accelerating |
| 95 | [KRYS](https://www.sec.gov/Archives/edgar/data/1711279/000171127926000057/krys-20260630.htm) | Krystal Biotech, Inc. | 2026-06-30 | 24.1% | 28.0% | 94.9, 36.6, 16.6, 17.5, 31.9, 24.1 | Decelerating |
| 96 | [AVPT](https://www.sec.gov/Archives/edgar/data/1777921/000143774926026267/avpt20260630_10q.htm) | AvePoint, Inc. | 2026-06-30 | 22.0% | 25.4% | 24.9, 30.9, 23.6, 28.6, 26.0, 22.0 | Stable |
| 97 | [EVR](https://www.sec.gov/Archives/edgar/data/1360901/000162828026053320/evr-20260630.htm) | EVERCORE INC. | 2026-06-30 | 19.1% | 26.6% | 19.5, 20.9, 41.7, 32.4, 100.3, 19.1 | Accelerating |
| 98 | [IRTC](https://www.sec.gov/Archives/edgar/data/1388658/000138865826000072/irtc-20260630.htm) | iRhythm Holdings, Inc. | 2026-06-30 | 20.1% | 25.9% | 20.3, 26.1, 30.7, 27.1, 25.7, 20.1 | Stable |
| 99 | [RELY](https://www.sec.gov/Archives/edgar/data/1782170/000162828026053424/rely-20260630.htm) | Remitly Global, Inc. | 2026-06-30 | 20.2% | 25.4% | 34.4, 34.4, 24.7, 25.7, 25.2, 20.2 | Decelerating |
| 100 | [LOAR](https://www.sec.gov/Archives/edgar/data/2000178/000119312526336945/ck0002000178-20260630.htm) | Loar Holdings Inc. | 2026-06-30 | 39.4% | 25.9% | 24.8, 26.9, 22.4, 19.3, 36.1, 39.4 | Accelerating |
| 101 | [SYM](https://www.sec.gov/Archives/edgar/data/1837240/000183724026000043/sym-20260627.htm) | SYMBOTIC INC. | 2026-06-27 | 21.7% | 24.5% | 39.7, 25.9, 9.5, 29.4, 23.1, 21.7 | Stable |
| 102 | [TPB](https://www.sec.gov/Archives/edgar/data/1290677/000143774926025664/tpb20260630_10q.htm) | Turning Point Brands, Inc. | 2026-06-30 | 22.6% | 26.6% | 28.1, 25.1, 31.2, 29.2, 16.8, 22.6 | Decelerating |
| 103 | [CAVA](https://www.sec.gov/Archives/edgar/data/1639438/000162828026055864/cava-20260712.htm) | CAVA Group, Inc. | 2026-07-12 | 31.3% | 24.5% | 28.1, 20.2, 19.9, 20.9, 32.1, 31.3 | Accelerating |
| 104 | [FIVE](https://www.sec.gov/Archives/edgar/data/1177609/000117760926000027/five-20260801.htm) | Five Below, Inc. | 2026-08-01 | 22.9% | 23.4% | 19.5, 23.7, 23.1, 24.3, 32.5, 22.9 | Stable |
| 105 | [TOST](https://www.sec.gov/Archives/edgar/data/1650164/000165016426000164/tost-20260630.htm) | Toast, Inc. | 2026-06-30 | 23.1% | 23.7% | 24.4, 24.8, 25.1, 22.0, 21.9, 23.1 | Stable |
| 106 | [GTLB](https://www.sec.gov/Archives/edgar/data/1653482/000162828026059943/gtlb-20260731.htm) | GITLAB INC. | 2026-07-31 | 21.3% | 23.9% | 26.8, 29.2, 24.6, 23.2, 23.1, 21.3 | Decelerating |
| 107 | [TEAM](https://www.sec.gov/Archives/edgar/data/1650372/000165037226000036/team-20260630.htm) | Atlassian Corporation | 2026-06-30 | 27.6% | 22.8% | 14.1, 22.3, 20.6, 23.3, 31.7, 27.6 | Accelerating |
| 108 | [PRM](https://www.sec.gov/Archives/edgar/data/1880319/000188031926000048/prm-20260630.htm) | PERIMETER SOLUTIONS, INC. | 2026-06-30 | 31.5% | 24.9% | 22.0, 27.8, 9.4, 19.2, 73.6, 31.5 | Accelerating |
| 109 | [CRWD](https://www.sec.gov/Archives/edgar/data/1535527/000153552726000031/crwd-20260731.htm) | CrowdStrike Holdings, Inc. | 2026-07-31 | 25.8% | 22.7% | 19.8, 21.3, 22.2, 23.3, 25.6, 25.8 | Accelerating |
| 110 | [AJG](https://www.sec.gov/Archives/edgar/data/354190/000162828026053489/ajg-20260630.htm) | ARTHUR J. GALLAGHER & CO. | 2026-06-30 | 24.2% | 22.1% | 14.4, 16.1, 19.9, 33.6, 27.7, 24.2 | Accelerating |
| 111 | [EPRT](https://www.sec.gov/Archives/edgar/data/1728951/000172895126000052/eprt-20260630.htm) | ESSENTIAL PROPERTIES REALTY TRUST, INC. | 2026-06-30 | 18.1% | 24.4% | 25.0, 25.4, 23.7, 25.2, 22.8, 18.1 | Stable |
| 112 | [KTOS](https://www.sec.gov/Archives/edgar/data/1069258/000106925826000077/ktos-20260628.htm) | KRATOS DEFENSE & SECURITY SOLUTIONS, INC. | 2026-06-28 | 30.5% | 22.3% | 9.2, 17.1, 26.0, 21.9, 22.6, 30.5 | Accelerating |
| 113 | [PDFS](https://www.sec.gov/Archives/edgar/data/1120914/000143774926026294/pdfs20260630_10q.htm) | PDF SOLUTIONS INC | 2026-06-30 | 18.9% | 23.6% | 15.7, 24.2, 23.1, 24.6, 25.9, 18.9 | Stable |
| 114 | [VIRT](https://www.sec.gov/Archives/edgar/data/1592386/000159238626000028/virt-20260630.htm) | Virtu Financial, Inc. | 2026-06-30 | 19.0% | 24.7% | 30.3, 44.2, 16.7, 16.3, 30.7, 19.0 | Decelerating |
| 115 | [AXGN](https://www.sec.gov/Archives/edgar/data/805928/000080592826000094/axgn-20260630.htm) | Axogen, Inc. | 2026-06-30 | 23.1% | 22.2% | 17.4, 18.3, 23.5, 21.3, 26.6, 23.1 | Accelerating |
| 116 | [AUPH](https://www.sec.gov/Archives/edgar/data/1600620/000160062026000062/auph-20260630.htm) | Aurinia Pharmaceuticals Inc. | 2026-06-30 | 18.9% | 23.3% | 24.2, 22.4, 8.4, 28.8, 24.4, 18.9 | Stable |
| 117 | [AEIS](https://www.sec.gov/Archives/edgar/data/927003/000092700326000032/aeis-20260630x10q.htm) | ADVANCED ENERGY INDUSTRIES, INC. | 2026-06-30 | 30.0% | 23.7% | 23.5, 21.0, 23.8, 17.8, 26.3, 30.0 | Stable |
| 118 | [NOW](https://www.sec.gov/Archives/edgar/data/1373715/000137371526000076/now-20260630.htm) | ServiceNow, Inc. | 2026-06-30 | 24.0% | 21.9% | 18.6, 22.4, 21.8, 20.7, 22.1, 24.0 | Stable |
| 119 | [AMBA](https://www.sec.gov/Archives/edgar/data/1280263/000119312526383365/amba-20260731.htm) | AMBARELLA, INC. | 2026-07-31 | 13.2% | 25.6% | 57.6, 49.9, 31.2, 20.1, 16.9, 13.2 | Decelerating |
| 120 | [VTR](https://www.sec.gov/Archives/edgar/data/740260/000074026026000024/vtr-20260630.htm) | Ventas, Inc. | 2026-06-30 | 21.7% | 21.1% | 13.2, 18.3, 20.4, 21.7, 22.0, 21.7 | Accelerating |
| 121 | [DTM](https://www.sec.gov/Archives/edgar/data/1842022/000184202226000009/dtm-20260630.htm) | DT Midstream, Inc. | 2026-06-30 | 11.0% | 26.4% | 26.2, 26.6, 26.6, 27.3, 10.9, 11.0 | Decelerating |
| 122 | [NTST](https://www.sec.gov/Archives/edgar/data/1798100/000162828026049220/ntst-20260630.htm) | NETSTREIT Corp. | 2026-06-30 | 26.9% | 22.0% | 21.9, 22.0, 16.6, 19.1, 24.3, 26.9 | Stable |
| 123 | [S](https://www.sec.gov/Archives/edgar/data/1583708/000158370826000055/s-20260731.htm) | SENTINELONE, INC | 2026-07-31 | 20.6% | 21.3% | 22.9, 21.7, 22.9, 20.2, 20.8, 20.6 | Stable |

## Higher-growth and less-consistent alternatives

These passed the broader screen (latest three quarters >=8%, six-quarter median >=8%, at least five positive quarters) but not the conservative final screen. They are excluded from the proposed 123.

| Stock | Latest YoY | 6Q median | Quarters >=8% | Reason for separate review |
| --- | ---: | ---: | ---: | --- |
| [ONDS](https://www.sec.gov/Archives/edgar/data/1646188/000119312526349288/onds-20260630.htm) | 1235.4% | 605.6% | 6/6 | historical quarter revenue below USD25m or incomplete window |
| [AMPX](https://www.sec.gov/Archives/edgar/data/1899287/000189928726000059/ampx-20260630.htm) | 125.9% | 162.8% | 6/6 | historical quarter revenue below USD25m or incomplete window |
| [IBRX](https://www.sec.gov/Archives/edgar/data/1326110/000132611026000079/ibrx-20260630.htm) | 93.9% | 416.0% | 6/6 | historical quarter revenue below USD25m or incomplete window |
| [BMNR](https://www.sec.gov/Archives/edgar/data/1829311/000162828026048157/bmnr-20260531.htm) | 2167.9% | 92.6% | 6/6 | historical quarter revenue below USD25m or incomplete window |
| [WAL](https://www.sec.gov/Archives/edgar/data/1212545/000162828026051418/wal-20260630.htm) | 94.5% | 82.4% | 6/6 | historical quarter revenue below USD25m or incomplete window |
| [ASTS](https://www.sec.gov/Archives/edgar/data/1780312/000119312526342550/asts-20260630.htm) | 2626.6% | 1596.1% | 6/6 | historical quarter revenue below USD25m or incomplete window |
| [LQDA](https://www.sec.gov/Archives/edgar/data/1819576/000110465926094410/lqda-20260630x10q.htm) | 1842.7% | 1482.2% | 5/6 | fewer than six quarters >=8%; historical quarter revenue below USD25m or incomplete window |
| [IONQ](https://www.sec.gov/Archives/edgar/data/1824920/000119312526341001/ionq-20260630.htm) | 286.8% | 254.2% | 5/6 | fewer than six quarters >=8%; historical quarter revenue below USD25m or incomplete window |
| [QXO](https://www.sec.gov/Archives/edgar/data/1236275/000162828026056919/qxo-20260630.htm) | 70.3% | 12880.6% | 5/6 | fewer than six quarters >=8%; historical quarter revenue below USD25m or incomplete window |
| [RKT](https://www.sec.gov/Archives/edgar/data/1805284/000162828026054577/rkt-20260630.htm) | 91.9% | 72.0% | 5/6 | fewer than six quarters >=8% |
| [BBIO](https://www.sec.gov/Archives/edgar/data/1743881/000174388126000027/bbio-20260630.htm) | 120.4% | 1320.8% | 5/6 | fewer than six quarters >=8%; historical quarter revenue below USD25m or incomplete window |
| [SMCI](https://www.sec.gov/Archives/edgar/data/1375365/000137536526000022/smci-20260630.htm) | 93.2% | 56.3% | 4/6 | fewer than six quarters >=8% |
| [DKS](https://www.sec.gov/Archives/edgar/data/1089063/000108906326000036/dks-20260801.htm) | 53.2% | 44.8% | 4/6 | fewer than six quarters >=8% |
| [LTC](https://www.sec.gov/Archives/edgar/data/887905/000110465926091183/ltc-20260630x10q.htm) | 64.1% | 42.3% | 5/6 | fewer than six quarters >=8% |
| [MXL](https://www.sec.gov/Archives/edgar/data/1288469/000128846926000051/mxl-20260630.htm) | 55.2% | 45.5% | 5/6 | fewer than six quarters >=8% |
| [SNDK](https://www.sec.gov/Archives/edgar/data/2023554/000162828026057406/sndk-20260703.htm) | 371.6% | 41.9% | 5/6 | fewer than six quarters >=8% |
| [VCTR](https://www.sec.gov/Archives/edgar/data/1570827/000119312526337010/vctr-20260630.htm) | 24.0% | 60.0% | 5/6 | fewer than six quarters >=8% |
| [SANM](https://www.sec.gov/Archives/edgar/data/897723/000089772326000037/sanm-20260627.htm) | 69.7% | 34.9% | 5/6 | fewer than six quarters >=8% |
| [DNOW](https://www.sec.gov/Archives/edgar/data/1599617/000119312526338381/dnow-20260630.htm) | 108.1% | 37.2% | 3/6 | fewer than six quarters >=8% |
| [URGN](https://www.sec.gov/Archives/edgar/data/1668243/000143774926025794/urgn20260630_10q.htm) | 199.2% | 32.4% | 5/6 | fewer than six quarters >=8%; historical quarter revenue below USD25m or incomplete window |
| [STRL](https://www.sec.gov/Archives/edgar/data/874238/000087423826000103/strl-20260630.htm) | 90.1% | 33.8% | 4/6 | fewer than six quarters >=8% |
| [CELH](https://www.sec.gov/Archives/edgar/data/1341766/000134176626000050/celh-20260630.htm) | 10.6% | 100.6% | 5/6 | fewer than six quarters >=8% |
| [COF](https://www.sec.gov/Archives/edgar/data/927628/000092762826000089/cof-20260630.htm) | 26.9% | 41.9% | 5/6 | fewer than six quarters >=8% |
| [SHLS](https://www.sec.gov/Archives/edgar/data/1831651/000183165126000108/shls-20260630.htm) | 47.4% | 35.8% | 5/6 | fewer than six quarters >=8% |
| [DELL](https://www.sec.gov/Archives/edgar/data/1571996/000157199626000046/dell-20260731.htm) | 57.7% | 29.2% | 5/6 | fewer than six quarters >=8% |
| [SCCO](https://www.sec.gov/Archives/edgar/data/1001838/000110465926089169/scco-20260630x10q.htm) | 40.6% | 28.1% | 5/6 | fewer than six quarters >=8% |
| [COHU](https://www.sec.gov/Archives/edgar/data/21535/000143774926025144/cohu20260627_10q.htm) | 38.4% | 29.6% | 4/6 | fewer than six quarters >=8% |
| [ELF](https://www.sec.gov/Archives/edgar/data/1600033/000160003326000040/elf-20260630.htm) | 35.5% | 24.7% | 5/6 | fewer than six quarters >=8% |
| [PIPR](https://www.sec.gov/Archives/edgar/data/1230245/000123024526000032/pipr-20260630.htm) | 24.5% | 28.5% | 5/6 | fewer than six quarters >=8% |
| [SEDG](https://www.sec.gov/Archives/edgar/data/1419612/000117891326003854/zk2635807.htm) | 19.6% | 30.6% | 5/6 | fewer than six quarters >=8% |
| [WT](https://www.sec.gov/Archives/edgar/data/880631/000121465926009661/wti-20260630.htm) | 57.3% | 22.4% | 5/6 | fewer than six quarters >=8% |
| [ALGM](https://www.sec.gov/Archives/edgar/data/866291/000119312526327128/algm-20260626.htm) | 27.5% | 24.0% | 5/6 | fewer than six quarters >=8% |
| [TLN](https://www.sec.gov/Archives/edgar/data/1622536/000162253626000066/tln-20260630.htm) | 18.6% | 26.9% | 5/6 | fewer than six quarters >=8% |
| [CDNA](https://www.sec.gov/Archives/edgar/data/1217234/000121723426000046/cdna-20260630.htm) | 52.2% | 23.0% | 5/6 | fewer than six quarters >=8% |
| [CALX](https://www.sec.gov/Archives/edgar/data/1406666/000140666626000034/calx-20260627.htm) | 21.3% | 24.6% | 5/6 | fewer than six quarters >=8% |
| [CXW](https://www.sec.gov/Archives/edgar/data/1070985/000119312526337295/cxw-20260630.htm) | 27.3% | 21.9% | 5/6 | fewer than six quarters >=8% |
| [SNEX](https://www.sec.gov/Archives/edgar/data/913760/000091376026000038/intl-20260630.htm) | 15.4% | 26.4% | 5/6 | fewer than six quarters >=8% |
| [HRI](https://www.sec.gov/Archives/edgar/data/1364479/000136447926000109/hri-20260630.htm) | 20.2% | 23.6% | 5/6 | fewer than six quarters >=8% |
| [NPKI](https://www.sec.gov/Archives/edgar/data/71829/000007182926000042/nr-20260630.htm) | 19.6% | 25.1% | 5/6 | fewer than six quarters >=8% |
| [MOD](https://www.sec.gov/Archives/edgar/data/67347/000110465926088569/mod-20260630x10q.htm) | 28.0% | 20.2% | 4/6 | fewer than six quarters >=8% |

## Filing and data exceptions

These companies need additional source or comparability work, or no longer meet the screen:

| Stock | Reason |
| --- | --- |
| EOSE | price below USD5 or unavailable |
| SOUN | price below USD5 or unavailable; latest revenue period older than 140 days or missing |
| CLSK | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| KNSA | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| CURB | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| CLOV | price below USD5 or unavailable |
| WSFS | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| UPST | latest financial filing has no revenue facts in selected concepts |
| BE | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| SEZL | newer earnings 8-K needs report review before using older quarter |
| LCID | price below USD5 or unavailable |
| ASND | latest revenue period older than 140 days or missing |
| AVAV | latest quarter below 8%; growth persistence below screen |
| WELL | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| EXE | latest quarter below 8%; growth persistence below screen |
| GBTG | not in current Nasdaq screener listings |
| BLK | newer earnings 8-K needs report review before using older quarter |
| TTAN | latest financial filing has no revenue facts in selected concepts |
| BGC | latest quarter below 8%; growth persistence below screen |
| BLFS | not in current Nasdaq screener listings |
| TTMI | newer earnings 8-K needs report review before using older quarter |
| RMBS | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| HUBS | newer earnings 8-K needs report review before using older quarter |
| INCY | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| IBKR | newer earnings 8-K needs report review before using older quarter |
| SCHW | newer earnings 8-K needs report review before using older quarter |
| GEN | latest quarter below 8%; growth persistence below screen |
| DIOD | newer earnings 8-K needs report review before using older quarter |
| SMTC | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| MS | newer earnings 8-K needs report review before using older quarter |
| JBL | newer earnings 8-K needs report review before using older quarter |
| GRMN | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| DTE | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| EXLS | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| VICR | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| D | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| CM | latest revenue period older than 140 days or missing |
| WDAY | newer earnings 8-K needs report review before using older quarter |
| SXI | latest quarter below 8%; growth persistence below screen |
| HURN | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| HUM | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| PAYX | latest quarter below 8%; growth persistence below screen |
| FAST | newer earnings 8-K needs report review before using older quarter |
| NEO | newer earnings 8-K needs report review before using older quarter |
| FE | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| AEP | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| STAG | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| CHEF | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| DLR | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| LFUS | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| CFG | newer earnings 8-K needs report review before using older quarter |
| ZWS | latest financial filing has no revenue facts in selected concepts; newer earnings 8-K needs report review before using older quarter; latest filing report date newer than extracted revenue quarter; latest revenue period older than 140 days or missing |
| DOLE | latest quarter below 8%; growth persistence below screen |

## Issuer-release spot checks

These are sample checks of the SEC-derived latest-quarter figures against issuer releases, not a manual review of every company:

- [CRDO](https://investors.credosemi.com/news-events/news/news-details/2026/Credo-Technology-Group-Holding-Ltd-Reports-First-Quarter-of-Fiscal-Year-2027-Financial-Results/default.aspx): Issuer reports approximately 115% revenue growth for the quarter ended 1 August 2026.
- [CRWV](https://investors.coreweave.com/news/news-details/2026/CoreWeave-Reports-Strong-Second-Quarter-2026-Results/default.aspx): Issuer Q2 2026 release corroborates the revenue comparison.
- [ALAB](https://ir.asteralabs.com/news-releases/news-release-details/astera-labs-reports-second-quarter-2026-financial-results): Issuer reports USD392.4m revenue and approximately 104% YoY growth for Q2 2026.
- [RDDT](https://investor.redditinc.com/news-events/news-releases/news-details/2026/Reddit-Reports-Second-Quarter-2026-Results/): Issuer reports USD805m revenue and approximately 61% YoY growth for Q2 2026.
- [CVNA](https://investors.carvana.com/news-releases/2026/07-29-2026-210525685): Issuer reports USD7.376bn revenue and approximately 52% YoY growth for Q2 2026.
- [APH](https://investor.amphenol.com/news-and-events/news-details/2026/Amphenol-Reports-Record-Second-Quarter-2026-Results/default.aspx): Issuer reports 55% reported sales growth, including 24 percentage points from acquisitions and approximately 1 point from FX; organic growth is 30%.
- [PLMR](https://ir.palomarspecialty.com/news-releases/news-release-details/palomar-holdings-inc-reports-second-quarter-2026-results): Total GAAP revenue is USD314.423m versus USD203.311m; premium-growth headlines use different revenue definitions.

## Sources and limits

The starting pool is the approximately 2,000 issuers already represented in the project's SEC cache, not an exhaustive screen of every listed stock. Cached growth that already failed persistence criteria was not universally refreshed. Consequently these are 123 qualifying additions from this pool, not a claim about the 123 best revenue growers in the entire market.

The current Nasdaq directory and SEC submissions metadata were fetched on 17 October. Cached revenue facts were retained when the current financial accession was already represented; otherwise fresh Company Facts were downloaded into the isolated research cache. Fresh facts can still omit custom tags or the newest earnings-release figures. Conservative exceptions are listed above. The screen does not parse every exhibit or independently review organic growth for every company.

- [SEC Company Facts and submissions API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Nasdaq screener directory](https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true&limit=25000&offset=0)
- Each selected ticker links to its current supported financial filing. The JSON includes Company Facts and submissions URLs plus verification timestamps.
- [Full evidence and proposed metadata](candidates.json) · [Spreadsheet with all six growth observations](candidates.csv)

Reproduce the research with `scripts/screen_revenue_expansion.py`, `scripts/verify_revenue_expansion.py`, and `scripts/report_revenue_expansion.py`. Raw source responses remain under `.cache/revenue-expansion-2026-10-17/`; none of these scripts activates stocks or writes the application database.
