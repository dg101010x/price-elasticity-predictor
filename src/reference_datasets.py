"""
The external price/quantity datasets the benchmarks are fitted from.

Why these and not others
------------------------
The headline estimates on this site come from one catalogue in one market
(UK wholesale gift and homeware, 2009-2011). The page says so, twice. The
obvious question a price-setter asks next -- "is -0.7 normal, or is my
catalogue weird?" -- can't be answered from that dataset at all.

So this module collects the price/quantity datasets that are *actually*
fetchable without an account: no Kaggle token, no academic registration, no
Dataverse guestbook. Every one ships inside a CRAN package (GPL or MIT) or
the PyPI `wooldridge` package, and is mirrored as a plain CSV by
Rdatasets or as package data on the read-only CRAN GitHub mirror.

Eligibility, deliberately
-------------------------
Each entry records its license and its original citation, and nothing here
is redistributed by this repository: `data/csv/` is gitignored, the loader
re-fetches from source, and the only thing committed is the fitted numbers
(`data/processed/benchmarks.json`). A regression coefficient is not a copy
of the dataset it was fitted from.

Ruled out on purpose, and why -- these are documented rather than silently
skipped, because "not included" and "not available" are different claims:

  gt::pizzaplace        49,574 real pizza orders with SKU-level prices, and
                        exactly zero within-SKU price variation across the
                        year (91 SKUs, 91 distinct prices). Nothing to
                        regress: price never moves.
  hdm::BLP              2,217 car models with prices and market shares, but
                        OLS on log share is biased toward zero by unobserved
                        quality -- that bias is the entire reason the BLP
                        method exists. Publishing the OLS number next to
                        honest estimates would be misleading.
  Ecdat::BudgetFood     budget shares without prices; a demand system needs
  Ecdat::Tobacco        price data this doesn't carry.
  ISLR::Carseats        simulated data. Fine for teaching regression, not
                        evidence about any real market.
  Stat2Data::Grocery    36 store-weeks that look like a promotion experiment
                        until you check: `Price` correlates 0.98 with
                        `Sales`, so it is derived from the sales figure
                        rather than set before it. Regressing one on the
                        other measures the arithmetic, not the shopper. It
                        fitted at +3.3 before being dropped, which is what
                        that kind of mistake looks like when it isn't caught.
  Kilts Dominick's      the full 100M-row scanner archive still needs
  (raw)                 academic registration -- but bayesm ships a licensed
                        11-brand extract of it, which is what's used below.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_DIR = ROOT / "data" / "csv"
RAW_DIR = ROOT / "data" / "raw_downloads"

RDATASETS_CSV = "https://raw.githubusercontent.com/vincentarelbundock/Rdatasets/master/csv/{package}/{item}.csv"
RDATASETS_DOC = "https://vincentarelbundock.github.io/Rdatasets/doc/{package}/{item}.html"
CRAN_MIRROR_DATA = "https://raw.githubusercontent.com/cran/{package}/master/data/{item}.rda"


@dataclass
class ReferenceDataset:
    """One external dataset, plus everything needed to cite it honestly."""

    key: str                    # stable id, used as the benchmark's id
    filename: str               # what it lands as in data/csv/
    market: str                 # plain-English "what is being priced"
    package: str                # CRAN/PyPI package that ships it
    item: str                   # dataset name inside that package
    license: str
    citation: str
    region: str
    period: str
    data_type: str              # panel | time series | cross-section | choice panel
    key_elasticity_columns: str
    description: str
    kind: str = "rdatasets"     # rdatasets | cran_rda | wooldridge
    note: str = ""
    source_url: str = ""
    doc_url: str = ""

    def __post_init__(self) -> None:
        if not self.source_url:
            self.source_url = (
                CRAN_MIRROR_DATA.format(package=self.package, item=self.item)
                if self.kind == "cran_rda"
                else f"https://pypi.org/project/{self.package}/"
                if self.kind == "wooldridge"
                else RDATASETS_CSV.format(package=self.package, item=self.item)
            )
        if not self.doc_url and self.kind == "rdatasets":
            self.doc_url = RDATASETS_DOC.format(package=self.package, item=self.item)


REFERENCE_DATASETS: list[ReferenceDataset] = [
    ReferenceDataset(
        key="dominicks_oj",
        filename="dominicks_oj.csv",
        market="Orange juice, US supermarket shelf",
        package="bayesm",
        item="orangeJuice",
        license="GPL (>= 2)",
        citation=(
            "Dominick's Finer Foods store-level scanner data, distributed as "
            "bayesm::orangeJuice (Rossi, Allenby & McCulloch, Bayesian "
            "Statistics and Marketing)."
        ),
        region="83 Chicago-area stores",
        period="1989-1994, weekly",
        data_type="store-brand-week panel",
        key_elasticity_columns="store,brand,week,logmove,price1..price11,deal,feat",
        description=(
            "106,139 store-brand-weeks covering 11 orange juice brands: log "
            "units moved, the price of every brand on the shelf that week, "
            "and in-store display (deal) and feature-ad (feat) flags. This "
            "is the real thing -- a full scanner panel with promotions -- "
            "and the only dataset here with enough cross-price structure to "
            "measure what a competitor's discount does to your volume."
        ),
        kind="cran_rda",
        note=(
            "The raw Kilts Center Dominick's archive needs academic "
            "registration; this 11-brand extract is redistributed on CRAN "
            "under GPL, which is why it's reachable here at all."
        ),
    ),
    ReferenceDataset(
        key="cigarettes_state_panel",
        filename="cigar_state_panel.csv",
        market="Cigarettes, US states",
        package="Ecdat",
        item="Cigar",
        license="GPL (>= 2)",
        citation="Baltagi & Levin (1992); Baltagi et al. (2000). Ecdat::Cigar.",
        region="46 US states",
        period="1963-1992, annual",
        data_type="state-year panel",
        key_elasticity_columns="state,year,price,sales,cpi,ndi,pimin",
        description=(
            "1,380 state-years of per-capita cigarette sales against retail "
            "price, with CPI for deflation and the minimum price in "
            "neighbouring states (which is how cross-border bootlegging "
            "shows up in the data). Thirty years of tax-driven price "
            "variation -- the closest thing to a natural experiment in this "
            "collection."
        ),
    ),
    ReferenceDataset(
        key="cigarettes_stock_watson",
        filename="cigarettes_sw.csv",
        market="Cigarettes, US states (tax-instrumented)",
        package="AER",
        item="CigarettesSW",
        license="GPL-2 | GPL-3",
        citation="Stock & Watson, Introduction to Econometrics. AER::CigarettesSW.",
        region="48 US states",
        period="1985 and 1995",
        data_type="state panel",
        key_elasticity_columns="state,year,packs,price,tax,taxs,income,cpi",
        description=(
            "The textbook instrumental-variables dataset: packs per capita "
            "and average price, with the general sales tax split out from "
            "the cigarette-specific tax. The sales-tax share moves price "
            "without being caused by how much people smoke, which is what "
            "makes an honest causal estimate possible here and nowhere else "
            "in this collection except the fish market."
        ),
    ),
    ReferenceDataset(
        key="gasoline_oecd",
        filename="gasoline_oecd.csv",
        market="Motor fuel, OECD countries",
        package="AER",
        item="OECDGas",
        license="GPL-2 | GPL-3",
        citation="Baltagi & Griffin (1983). AER::OECDGas / Ecdat::Gasoline.",
        region="18 OECD countries",
        period="1960-1978, annual",
        data_type="country-year panel",
        key_elasticity_columns="country,year,gas,price,income,cars",
        description=(
            "342 country-years of motor gasoline consumption per car against "
            "real fuel price, already in logs. A necessity with no close "
            "substitute, which is what an inelastic number is supposed to "
            "look like."
        ),
    ),
    ReferenceDataset(
        key="natural_gas_states",
        filename="natural_gas_states.csv",
        market="Residential natural gas, US states",
        package="AER",
        item="NaturalGas",
        license="GPL-2 | GPL-3",
        citation="Balestra & Nerlove (1966); Greene, Econometric Analysis. AER::NaturalGas.",
        region="6 US states",
        period="1967-1989, annual",
        data_type="state-year panel",
        key_elasticity_columns="state,year,consumption,price,eprice,oprice,heating,income",
        description=(
            "Residential gas consumption against its own price *and* the "
            "price of electricity and heating oil, with heating degree-days. "
            "One of the few datasets here that can separate 'people used "
            "less' from 'people switched to the substitute'."
        ),
    ),
    ReferenceDataset(
        key="rail_freight_cartel",
        filename="rail_freight_cartel.csv",
        market="Rail freight, 1880s US grain routes",
        package="AER",
        item="CartelStability",
        license="GPL-2 | GPL-3",
        citation="Porter (1983), 'A Study of Cartel Stability'. AER::CartelStability.",
        region="Joint Executive Committee railroads",
        period="1880-1886, weekly",
        data_type="weekly time series",
        key_elasticity_columns="price,quantity,cartel,season,ice",
        description=(
            "328 weeks of grain shipment volumes and rates, flagged for "
            "whether the cartel was holding or had collapsed that week. "
            "Price wars move the supply curve without moving demand, so the "
            "collapses trace out the demand curve -- the identification "
            "argument that made this paper famous."
        ),
    ),
    ReferenceDataset(
        key="fulton_fish",
        filename="fish_prices.csv",
        market="Whiting, Fulton Fish Market",
        package="wooldridge",
        item="fish",
        license="GPL-3",
        citation="Graddy (1995), 'Testing for Imperfect Competition at the Fulton Fish Market'.",
        region="New York wholesale market",
        period="Dec 1991 - May 1992, daily",
        data_type="daily time series",
        key_elasticity_columns="avgprc,totqty,wave2,speed2,mon..thurs",
        description=(
            "97 trading days of whiting prices and volumes, with wave height "
            "and wind speed offshore. Storms keep boats in port and push "
            "prices up without changing how much fish anyone wanted to buy "
            "that day -- the cleanest instrument in economics, and already "
            "sitting unused in this repo's data directory."
        ),
        kind="wooldridge",
        note="Already downloaded by src/data_loader.py; now actually fitted.",
    ),
    ReferenceDataset(
        key="individual_smoking",
        filename="smoking_prices.csv",
        market="Cigarettes, individual smokers",
        package="wooldridge",
        item="smoke",
        license="GPL-3",
        citation="Mullahy (1997). wooldridge::smoke.",
        region="United States",
        period="1979-1980 cross-section",
        data_type="cross-section",
        key_elasticity_columns="cigs,cigpric,income,educ,age,restaurn",
        description=(
            "807 individuals: cigarettes smoked per day against the state "
            "cigarette price. Reported here precisely because it finds "
            "almost nothing -- state prices barely move within a single "
            "year, and a dataset without price variation cannot measure "
            "price response no matter how many rows it has."
        ),
        kind="wooldridge",
        note="Already downloaded by src/data_loader.py; now actually fitted.",
    ),
    ReferenceDataset(
        key="economics_journals",
        filename="economics_journals.csv",
        market="Academic journal subscriptions",
        package="AER",
        item="Journals",
        license="GPL-2 | GPL-3",
        citation="Bergstrom (2001), 'Free Labor for Costly Journals?'. AER::Journals.",
        region="180 economics journals",
        period="2000",
        data_type="cross-section",
        key_elasticity_columns="subs,price,citations,pages,foundingyear",
        description=(
            "Library subscriptions against price per citation. A textbook "
            "demand curve with an unusually clean quality control, and the "
            "standard worked example of a log-log elasticity regression."
        ),
    ),
    ReferenceDataset(
        key="avocados_california",
        filename="avocados_california.csv",
        market="Hass avocados, California retail",
        package="causaldata",
        item="avocado",
        license="MIT",
        citation="Hass Avocado Board retail scan data, via causaldata::avocado (Huntington-Klein).",
        region="California",
        period="2015-2018, weekly",
        data_type="weekly time series",
        key_elasticity_columns="Date,AveragePrice,TotalVolume",
        description=(
            "169 weeks of average price and total units sold, straight off "
            "retailers' checkout scanners. A single fresh commodity with "
            "obvious substitutes, at the opposite end of the shelf from "
            "cigarettes."
        ),
    ),
    ReferenceDataset(
        key="ice_cream",
        filename="ice_cream.csv",
        market="Ice cream, US households",
        package="Ecdat",
        item="Icecream",
        license="GPL (>= 2)",
        citation="Hildreth & Lu (1960). Ecdat::Icecream.",
        region="United States",
        period="1951-1953, four-weekly",
        data_type="time series",
        key_elasticity_columns="cons,price,income,temp",
        description=(
            "30 four-week periods of consumption, price, income and mean "
            "temperature. Tiny, and included because temperature is the "
            "textbook example of a demand shifter you must control for or "
            "the price coefficient absorbs the weather."
        ),
    ),
    ReferenceDataset(
        key="us_gasoline_market",
        filename="us_gasoline_market.csv",
        market="Motor fuel, US national",
        package="AER",
        item="USGasG",
        license="GPL-2 | GPL-3",
        citation="Greene, Econometric Analysis, Table F2.2. AER::USGasG.",
        region="United States",
        period="1960-1995, annual",
        data_type="time series",
        key_elasticity_columns="gas,price,income,newcar,usedcar",
        description=(
            "36 years of national per-capita fuel consumption against real "
            "price and income. The aggregate counterpart to the OECD panel: "
            "same product, one country, much less identifying variation."
        ),
    ),
    ReferenceDataset(
        key="recreation_trips",
        filename="recreation_trips.csv",
        market="Boating trips, Lake Somerville",
        package="AER",
        item="RecreationDemand",
        license="GPL-2 | GPL-3",
        citation="Ozuna & Gomez (1995); Cameron & Trivedi (1998). AER::RecreationDemand.",
        region="Texas",
        period="1980 survey",
        data_type="cross-section",
        key_elasticity_columns="trips,costS,costC,costH,income,quality,ski",
        description=(
            "659 households and what a trip cost them to take, which is the "
            "price of a good nobody sells. Included as the widest possible "
            "contrast with a supermarket shelf."
        ),
    ),
    # --- household brand-choice scanner panels -----------------------------
    # Quantity is not observed here; the observation is which brand a shopper
    # picked, given every brand's price that day. Fitted by conditional
    # logit, reported separately from the quantity regressions, and never
    # mixed with them in the same chart.
    ReferenceDataset(
        key="choice_ketchup",
        filename="choice_ketchup.csv",
        market="Ketchup brands",
        package="Ecdat",
        item="Ketchup",
        license="GPL (>= 2)",
        citation="Kim, Allenby & Rossi (2002). Ecdat::Ketchup.",
        region="US supermarket panel",
        period="scanner panel",
        data_type="brand-choice panel",
        key_elasticity_columns="Ketchup.choice,price.heinz,price.hunts,price.delmonte,price.stb",
        description="4,956 purchase occasions across four ketchup brands, with every brand's price at the moment of choice.",
    ),
    ReferenceDataset(
        key="choice_catsup",
        filename="choice_catsup.csv",
        market="Catsup brands (with promotions)",
        package="Ecdat",
        item="Catsup",
        license="GPL (>= 2)",
        citation="Jain, Vilcassim & Chintagunta (1994). Ecdat::Catsup.",
        region="US supermarket panel",
        period="scanner panel",
        data_type="brand-choice panel",
        key_elasticity_columns="choice,price.*,disp.*,feat.*",
        description="2,798 purchase occasions across four catsup SKUs, carrying display and feature flags alongside price.",
    ),
    ReferenceDataset(
        key="choice_tuna",
        filename="choice_tuna.csv",
        market="Canned tuna brands",
        package="Ecdat",
        item="Tuna",
        license="GPL (>= 2)",
        citation="Chintagunta (2002)-style tuna panel. Ecdat::Tuna.",
        region="US supermarket panel",
        period="scanner panel",
        data_type="brand-choice panel",
        key_elasticity_columns="Tuna.choice,price.skw,price.cosw,price.sko,price.coso,price.pw",
        description="13,705 purchase occasions across five canned tuna products -- the largest choice panel here.",
    ),
    ReferenceDataset(
        key="choice_yogurt",
        filename="choice_yogurt.csv",
        market="Yogurt brands (with promotions)",
        package="Ecdat",
        item="Yogurt",
        license="GPL (>= 2)",
        citation="Jain, Vilcassim & Chintagunta (1994). Ecdat::Yogurt.",
        region="US supermarket panel",
        period="scanner panel",
        data_type="brand-choice panel",
        key_elasticity_columns="choice,price.*,feat.*",
        description="2,412 purchase occasions across four yogurt brands, with feature-advertising flags.",
    ),
    ReferenceDataset(
        key="choice_crackers",
        filename="choice_crackers.csv",
        market="Cracker brands (with promotions)",
        package="Ecdat",
        item="Cracker",
        license="GPL (>= 2)",
        citation="Jain, Vilcassim & Chintagunta (1994). Ecdat::Cracker.",
        region="US supermarket panel",
        period="scanner panel",
        data_type="brand-choice panel",
        key_elasticity_columns="choice,price.*,disp.*,feat.*",
        description="3,292 purchase occasions across four cracker brands, with display and feature flags.",
    ),

    # --- real retail scanner / POS data from outside the US and UK ---------
    # Added in 2.2. Each is real transaction data (not simulated -- the
    # "African retail" sets that turn up on Hugging Face and Kaggle are
    # generated, and are not here), openly licensed, and fetchable without an
    # account. Quantity is observed, so these are fitted like the quantity
    # panels above. See `REJECTED_2_2` for what was looked at and left out.
    ReferenceDataset(
        key="poland_rice_sugar_milk",
        filename="poland_rsm.csv",
        market="Rice, sugar and milk, Polish supermarket",
        package="zenodo:18342253",
        item="dataRSM",
        license="CC BY 4.0",
        citation=(
            "Bia\u0142ek, J. (2026), 'A real scanner data set on sold rice, sugar and milk "
            "products', Zenodo, doi:10.5281/zenodo.18342253. Collected by Statistics Poland."
        ),
        region="One supermarket, 4 outlets, Poland",
        period="Dec 2024 - Jan 2026, monthly",
        data_type="outlet-product-month panel",
        key_elasticity_columns="time,prices,quantities,retID,EAN_code,category",
        description=(
            "8,090 outlet-product-months of shelf price (PLN) and units sold for "
            "152 rice, sugar and milk products, straight off a Polish "
            "supermarket's scanners. The most recent data in the collection."
        ),
        kind="zenodo_csv",
        source_url="https://zenodo.org/records/18342253/files/dataRSM.csv?download=1",
        doc_url="https://doi.org/10.5281/zenodo.18342253",
    ),
    ReferenceDataset(
        key="poland_milk_daily",
        filename="poland_milk_daily.csv",
        market="Milk products, Polish supermarket",
        package="PriceIndices",
        item="dataCOICOP",
        license="GPL-3",
        citation="Bia\u0142ek, J., PriceIndices (CRAN), dataset dataCOICOP: real scanner data on milk.",
        region="One supermarket chain, Poland",
        period="Dec 2020 - Feb 2022, daily",
        data_type="outlet-product-day panel",
        key_elasticity_columns="time,prices,quantities,retID,codeIN,category",
        description=(
            "139,600 outlet-product-days of milk sales: prices in PLN, units "
            "sold, and a COICOP product class. The biggest panel in the "
            "collection from outside the United States."
        ),
        kind="cran_rda",
    ),
    ReferenceDataset(
        key="poland_coffee",
        filename="poland_coffee.csv",
        market="Coffee, Polish supermarket",
        package="PriceIndices",
        item="coffee",
        license="GPL-3",
        citation="Bia\u0142ek, J., PriceIndices (CRAN), dataset coffee: real scanner data.",
        region="One supermarket chain, 20 outlets, Poland",
        period="Dec 2017 - Oct 2020, daily",
        data_type="outlet-product-day panel",
        key_elasticity_columns="time,prices,quantities,prodID,retID",
        description="42,561 outlet-product-days across 79 coffee products (instant, ground and beans), quantity in kilograms.",
        kind="cran_rda",
    ),
    ReferenceDataset(
        key="poland_sugar",
        filename="poland_sugar.csv",
        market="Sugar, Polish supermarket",
        package="PriceIndices",
        item="sugar",
        license="GPL-3",
        citation="Bia\u0142ek, J., PriceIndices (CRAN), dataset sugar: real scanner data.",
        region="One supermarket chain, 20 outlets, Poland",
        period="Dec 2017 - Oct 2020, daily",
        data_type="outlet-product-day panel",
        key_elasticity_columns="time,prices,quantities,prodID,retID",
        description=(
            "7,666 outlet-product-days across 11 sugar products, quantity in "
            "kilograms. The category is a staple, but the estimate is for "
            "one sugar product at one outlet, so it counts shoppers moving to "
            "the next sugar on the shelf as well as people buying less."
        ),
        kind="cran_rda",
    ),
    ReferenceDataset(
        key="indonesia_pharmacy",
        filename="indonesia_pharmacy.csv",
        market="Pharmacy products, Indonesia",
        package="mendeley:2ym7v78wtd",
        item="transaction",
        license="CC BY 4.0",
        citation=(
            "Gustriansyah, R. (2022), 'Retail sales dataset of a pharmacy in Indonesia', "
            "Mendeley Data, V1, doi:10.17632/2ym7v78wtd.1."
        ),
        region="One pharmacy, Indonesia",
        period="Jan - Dec 2015, per prescription line",
        data_type="product-month panel (from 399,738 sales lines)",
        key_elasticity_columns="TGL,KD_OBAT,QTY,HNA,HJ",
        description=(
            "399,738 sales lines over 2,043 products from a real pharmacy's "
            "database. The retail price is the wholesale cost times a fixed "
            "1.375 markup on nearly every line, so every price change in this "
            "data is a cost change passed through -- price moves for reasons "
            "that have nothing to do with that month's local demand."
        ),
        kind="mendeley_sql",
        source_url="https://data.mendeley.com/public-files/datasets/2ym7v78wtd/files/efcdaafb-7511-4dbe-8728-dd48f68d5d3e/file_downloaded",
        doc_url="https://doi.org/10.17632/2ym7v78wtd.1",
        note="One pharmacy and one year: a product-level number for a single shop, not for Indonesia.",
    ),
]

# What was examined for 2.2 and left out, and why. "Not included" and "not
# available" are different claims, so the reason is recorded with each.
REJECTED_2_2 = {
    "africa-synth-* (Hugging Face)": "Synthetic point-of-sale records for Nigeria. Generated data says nothing about how Nigerian shoppers respond to price.",
    "Aries Supermarket / Kaggle 'supermarket sales'": "A widely circulated 1,000-row teaching table with uniform random columns; no real price variation, and Kaggle needs a login.",
    "Mendeley v8h8wn4w37 (multi-country retail)": "Mixes real and synthetic records with no flag separating them.",
    "Mendeley 27x8mjm8k4 (retail transactions and stocks)": "Country, period and price columns not documented, so the market cannot be stated.",
    "Zenodo 19680571 (Dortmund retail sales)": "CC0 and real, but carries sales quantity only -- no price.",
    "WFP / HDX food prices (Africa, Asia, MENA)": "CC BY-IGO and downloadable, but prices only: no quantity, so no elasticity.",
    "Billion Prices Project (Harvard Dataverse)": "Daily online prices for Latin American retailers, prices only.",
    "Agmarknet mandi prices (India)": "Prices and arrivals, but data.gov.in needs an API key and the public mirrors need a Kaggle login or only start in September 2026.",
    "Olist Brazilian e-commerce (Kaggle)": "Real, but CC BY-NC-SA and behind a Kaggle login.",
}

BY_KEY = {d.key: d for d in REFERENCE_DATASETS}


# ---------------------------------------------------------------------------
# Fetching. Nothing here caches into git -- data/csv/ is gitignored, and
# these functions are what refills it.
# ---------------------------------------------------------------------------


def fetch(spec: ReferenceDataset, force: bool = False):
    """Download one dataset and return it as a DataFrame, writing the CSV copy
    into data/csv/ so src/build_manifest.py can profile it like any other."""
    import pandas as pd

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CSV_DIR / spec.filename

    if out_path.exists() and not force:
        return pd.read_csv(out_path)

    if spec.kind == "rdatasets":
        df = pd.read_csv(spec.source_url)
        df = df.drop(columns=[c for c in ("rownames",) if c in df.columns])
    elif spec.kind == "wooldridge":
        import wooldridge as woo
        df = woo.dataWoo(spec.item)
    elif spec.kind == "cran_rda":
        df = _fetch_cran_rda(spec)
    elif spec.kind == "zenodo_csv":
        df = pd.read_csv(spec.source_url, sep=";", decimal=",")
    elif spec.kind == "mendeley_sql":
        df = _fetch_pharmacy(spec)
    else:                                                   # pragma: no cover
        raise ValueError(f"unknown fetch kind: {spec.kind}")

    df.to_csv(out_path, index=False)
    return df


def _fetch_cran_rda(spec: ReferenceDataset):
    """Read an R data file off the read-only CRAN GitHub mirror.

    bayesm::orangeJuice is an R *list* (`yx` plus store demographics), which
    is why this needs `rdata` rather than pyreadr -- pyreadr handles data
    frames only and returns an empty dict for a list, silently.
    """
    import pandas as pd
    import rdata

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    local = RAW_DIR / f"{spec.package}_{spec.item}.rda"
    if not local.exists():
        import requests
        resp = requests.get(spec.source_url, timeout=120)
        resp.raise_for_status()
        local.write_bytes(resp.content)

    converted = rdata.read_rda(str(local))
    obj = converted[spec.item]
    frame = obj["yx"] if isinstance(obj, dict) else obj
    df = pd.DataFrame(frame)
    df.columns = [str(c) for c in df.columns]
    if "time" in df.columns and df["time"].dtype.kind == "f":
        # R Dates arrive as days since 1970-01-01.
        df["time"] = pd.to_datetime(df["time"], unit="D").dt.strftime("%Y-%m-%d")
    return df.reset_index(drop=True)


def _fetch_pharmacy(spec: ReferenceDataset):
    """The Indonesian pharmacy dataset ships as one MariaDB dump inside a zip.
    Only the `transaction` table is wanted: one row per prescription line, with
    quantity, wholesale cost (HNA) and retail price (HJ)."""
    import io
    import re
    import zipfile

    import pandas as pd
    import requests

    resp = requests.get(spec.source_url, timeout=300)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
        name = next(n for n in z.namelist() if n.endswith(".sql"))
        text = z.read(name).decode("latin-1")

    line = re.compile(r"\('([^']*)', '([^']*)', '([^']*)', '([^']*)', ([-\d.eE]+), ([-\d.eE]+), ([-\d.eE]+)\)")
    rows, inside = [], False
    for ln in text.splitlines():
        if ln.startswith("INSERT INTO `transaction`"):
            inside = True
        elif inside:
            m = line.search(ln)
            if m:
                rows.append(m.groups())
            elif ln.startswith(("/*", "--")):
                inside = False
    df = pd.DataFrame(rows, columns=["NO_RESEP", "TGL", "KD_CUST", "KD_OBAT", "QTY", "HNA", "HJ"])
    for c in ("QTY", "HNA", "HJ"):
        df[c] = df[c].astype(float)
    return df


def fetch_all(force: bool = False) -> dict:
    """Fetch every reference dataset. Returns {key: DataFrame or Exception}."""
    results: dict = {}
    for spec in REFERENCE_DATASETS:
        try:
            results[spec.key] = fetch(spec, force=force)
        except Exception as exc:                            # noqa: BLE001
            results[spec.key] = exc
    return results
