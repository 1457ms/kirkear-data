#!/usr/bin/env python3
"""
Henter «Kirkeårets tekster»-PDF-ene fra Den norske kirkes ressursbank,
tolker dem og lagrer resultatet i data/kirkear.json.

Filen leses av WordPress-tillegget «Ordet.be Kirkeår». Tillegget er aldri
avhengig av kirken.no direkte – bare av denne filen.

Sikkerhetsprinsipper:
  * Skriptet skriver aldri en fil som ikke består kontrollene. Ved feil
    stopper jobben, og den forrige gode filen blir liggende.
  * Gamle data slettes ikke selv om kirken.no skulle mangle en PDF.

Bruk:
  python scripts/hent_kirkear.py                  # vanlig kjøring
  python scripts/hent_kirkear.py --pdf fil.pdf    # tolk lokal PDF (feilsøking)
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

ROT = Path(__file__).resolve().parent.parent
DATAFIL = ROT / "data" / "kirkear.json"
FEILSOK = ROT / "feilsok"

OVERSIKT_URL = "https://ressursbanken.kirken.no/nb-NO/gudstjenesteliv/liturgi2/liturgier/"
PDF_MAL = (
    "https://ressursbanken.kirken.no/globalassets/kirken.no/om-troen/"
    "gudstjeneste---liturgi/{a}-{b}%20kirke%C3%A5rskalender.pdf"
)
TILLATTE_VERTER = {"ressursbanken.kirken.no", "www.kirken.no", "kirken.no"}
MAKS_PDF_BYTES = 15 * 1024 * 1024
SCHEMA = 1

MANEDER = {
    "januar": 1, "februar": 2, "mars": 3, "april": 4, "mai": 5, "juni": 6,
    "juli": 7, "august": 8, "september": 9, "oktober": 10, "november": 11,
    "desember": 12,
}
REKKER = ("I", "II", "III")

# ---------------------------------------------------------------------------
# Regulære uttrykk
# ---------------------------------------------------------------------------
_VERS = r"[0-9]+[a-d]?(?:\s?[–—-]\s?[0-9]+(?:,[0-9]+)?[a-d]?)?(?:\.[0-9]+[a-d]?(?:[–—-][0-9]+[a-d]?)?)*"
_KAP = rf"[0-9]+(?:,\s?{_VERS})?"
REF = rf"(?:[1-5]\s?)?[A-ZÆØÅ][A-Za-zæøåÆØÅ]{{0,12}}\.?\s{_KAP}(?:\s?;\s?{_KAP})*"

LESNING_RE = re.compile(rf"^(?:(?P<rekke>III|II|I|A)\s*)?(?P<ref>{REF})(?:\s+(?P<tittel>\S.*))?$")
REKKE_ALENE_RE = re.compile(r"^(III|II|I|A)$")
ELLER_RE = re.compile(r"^eller\b", re.I)
SIDEHODE_RE = re.compile(r"^\[?Utskrift|Kirkeårets tekster \d{4}\s*[-–]\s*\d{4}|^side \d+$|^\d+$", re.I)
_MND = "|".join(MANEDER)
OVERSKRIFT_RE = re.compile(
    rf"^(?P<navn>\S.*?)\s+[–—-]\s+(?P<resten>[A-Za-zÆØÅæøå].*?(?P<dag>\d{{1,2}})\.\s*(?P<mnd>{_MND})(?:\s+(?P<aar>\d{{4}}))?)\s*$",
    re.I,
)


def rens(tekst: str) -> str:
    tekst = unicodedata.normalize("NFC", tekst)
    tekst = tekst.replace(" ", " ").replace("*", "")
    return re.sub(r"\s+", " ", tekst).strip()


def forste_advent(aar: int) -> dt.date:
    """1. søndag i advent = søndagen 22.–28. dager før juledag (27. nov–3. des)."""
    juledag = dt.date(aar, 12, 25)
    fjerde = juledag - dt.timedelta(days=(juledag.weekday() + 1) % 7 or 7)
    return fjerde - dt.timedelta(weeks=3)


def forventet_rekke(dato: dt.date) -> str:
    """Kirkeåret som starter 1. advent 2025 bruker rekke I, deretter II, III, I …"""
    start = dato.year if dato >= forste_advent(dato.year) else dato.year - 1
    return REKKER[(start - 2025) % 3]


# ---------------------------------------------------------------------------
# Tolking
# ---------------------------------------------------------------------------
@dataclass
class Dag:
    dato: dt.date
    navn: str
    rekke: str = ""
    lesninger: list = field(default_factory=list)
    ekstra: list = field(default_factory=list)

    def som_dict(self) -> dict:
        return {
            "date": self.dato.isoformat(),
            "name": self.navn,
            "rekke": self.rekke,
            "readings": self.lesninger,
            "extra": self.ekstra,
        }


def _velg_aar(dag: int, mnd: int, forrige: dt.date | None, startaar: int) -> dt.date:
    if forrige is None:
        return dt.date(startaar if mnd >= 11 else startaar + 1, mnd, dag)
    kandidater = []
    for aar in (forrige.year, forrige.year + 1):
        try:
            kandidater.append(dt.date(aar, mnd, dag))
        except ValueError:
            pass
    gyldige = [d for d in kandidater if d >= forrige - dt.timedelta(days=14)]
    return min(gyldige or kandidater, key=lambda d: abs((d - forrige).days))


def tolk_linjer(linjer: list[str], startaar: int) -> tuple[list[Dag], list[str]]:
    """Gjør tekstlinjer fra én kalender-PDF om til en liste med dager."""
    dager: list[Dag] = []
    merknader: list[str] = []
    ventende: list[str] = []      # linjer som kan være starten på et navn
    gjeldende: Dag | None = None
    ventende_rekke = ""
    eller = False
    forrige_dato: dt.date | None = None

    for ra in linjer:
        linje = rens(ra)
        if not linje or SIDEHODE_RE.search(linje):
            continue

        m = OVERSKRIFT_RE.match(linje)
        if m:
            navn = m.group("navn")
            # Navn brutt over to linjer: «Vingårdssøndag/14. søndag i» + «treenighetstiden – …»
            if ventende and (navn[:1].islower() or ventende[-1].endswith(("/", " i", " og", "-"))):
                navn = ventende[-1] + " " + navn
            navn = rens(navn)
            dag, mnd = int(m.group("dag")), MANEDER[m.group("mnd").lower()]
            try:
                if m.group("aar"):
                    dato = dt.date(int(m.group("aar")), mnd, dag)
                else:
                    dato = _velg_aar(dag, mnd, forrige_dato, startaar)
            except ValueError:
                merknader.append(f"Ugyldig dato i overskrift: {linje}")
                ventende = []
                continue
            gjeldende = Dag(dato=dato, navn=navn)
            dager.append(gjeldende)
            forrige_dato = dato
            ventende, ventende_rekke, eller = [], "", False
            continue

        if gjeldende is not None:
            if REKKE_ALENE_RE.match(linje):
                ventende_rekke = linje
                continue
            if ELLER_RE.match(linje):
                eller = True
                continue
            lm = LESNING_RE.match(linje)
            if lm:
                rekke = lm.group("rekke") or ventende_rekke
                if rekke and not gjeldende.rekke:
                    gjeldende.rekke = rekke
                ventende_rekke = ""
                post = {"ref": rens(lm.group("ref")), "title": rens(lm.group("tittel") or "")}
                if eller and gjeldende.lesninger:
                    gjeldende.lesninger[-1].setdefault("alt", []).append(post)
                elif len(gjeldende.lesninger) < 3:
                    gjeldende.lesninger.append(post)
                else:
                    gjeldende.ekstra.append(post)
                eller = False
                ventende = []
                continue

        # Ukjent linje: kan være første del av et navn som er brutt over to linjer.
        if len(linje) <= 60 and not linje.endswith((".", ":")):
            ventende.append(linje)
        else:
            ventende = []
    return dager, merknader


def avgrens_kirkeaar(dager: list[Dag], startaar: int) -> list[Dag]:
    """Behold bare dager fra 1. advent startaar til (ikke med) 1. advent året etter."""
    fra, til = forste_advent(startaar), forste_advent(startaar + 1)
    return [d for d in dager if fra <= d.dato < til]


def kontroller(dager: list[Dag], startaar: int) -> tuple[list[str], list[str]]:
    """Returnerer (feil, advarsler). Feil stopper jobben."""
    feil, adv = [], []
    if len(dager) < 50:
        feil.append(f"{startaar}/{startaar + 1}: bare {len(dager)} dager funnet (forventet 70–90).")
        return feil, adv

    fra, til = forste_advent(startaar), forste_advent(startaar + 1)
    sondager = {d.dato for d in dager if d.dato.weekday() == 6}
    alle = {fra + dt.timedelta(weeks=i) for i in range((til - fra).days // 7)}
    mangler = sorted(alle - sondager)
    if len(mangler) > len(alle) * 0.10:
        feil.append(f"{startaar}/{startaar + 1}: {len(mangler)} søndager mangler – tolkingen virker feil.")
    elif mangler:
        adv.append(f"{startaar}/{startaar + 1}: søndager uten treff: " + ", ".join(d.isoformat() for d in mangler))

    forventet = REKKER[(startaar - 2025) % 3]
    med_rekke = [d for d in dager if d.rekke in REKKER]
    avvik = [d for d in med_rekke if d.rekke != forventet]
    if med_rekke and len(avvik) > len(med_rekke) * 0.15:
        feil.append(f"{startaar}/{startaar + 1}: rekken avviker fra forventet ({forventet}) på {len(avvik)} dager.")
    for d in avvik:
        adv.append(f"{d.dato} {d.navn}: rekke {d.rekke} (vanlig dette året: {forventet})")

    uten = [d for d in dager if d.dato.weekday() == 6 and not d.lesninger]
    if len(uten) > 5:
        feil.append(f"{startaar}/{startaar + 1}: {len(uten)} søndager uten bibeltekster.")
    return feil, adv


# ---------------------------------------------------------------------------
# Nedlasting
# ---------------------------------------------------------------------------
def _hent(url: str, maks: int) -> bytes:
    import requests  # importeres her så testene ikke trenger nettverk

    vert = urllib.parse.urlparse(url).hostname or ""
    if urllib.parse.urlparse(url).scheme != "https" or vert not in TILLATTE_VERTER:
        raise ValueError(f"Ikke tillatt adresse: {url}")
    with requests.get(url, timeout=60, stream=True, headers={"User-Agent": "ordetbe-kirkear/1.0"}) as svar:
        if svar.status_code == 404:
            raise FileNotFoundError(url)
        svar.raise_for_status()
        data = b""
        for bit in svar.iter_content(65536):
            data += bit
            if len(data) > maks:
                raise ValueError(f"For stor fil: {url}")
        return data


def finn_pdf_adresser(idag: dt.date) -> dict[int, str]:
    """Finn PDF-er for inneværende og kommende kirkeår (fra oversiktssiden + kjent mønster)."""
    start = idag.year if idag >= forste_advent(idag.year) else idag.year - 1
    adresser = {aar: PDF_MAL.format(a=aar, b=aar + 1) for aar in range(start, start + 5)}
    try:
        html = _hent(OVERSIKT_URL, 3 * 1024 * 1024).decode("utf-8", "replace")
        for lenke in re.findall(r'href="([^"]+?\.pdf)"', html, re.I):
            navn = urllib.parse.unquote(lenke)
            m = re.search(r"(\d{4})-(\d{4})\s*kirkeårskalender\.pdf$", navn, re.I)
            if m and int(m.group(2)) == int(m.group(1)) + 1 and int(m.group(1)) >= start:
                adresser[int(m.group(1))] = urllib.parse.urljoin(OVERSIKT_URL, lenke)
    except Exception as e:  # oversiktssiden er bare en ekstra kilde
        print(f"Merk: kunne ikke lese oversiktssiden ({e}). Bruker kjent adressemønster.")
    return adresser


def pdf_til_linjer(pdf: bytes) -> list[str]:
    import pdfplumber

    linjer: list[str] = []
    with pdfplumber.open(io.BytesIO(pdf)) as dok:
        for side in dok.pages:
            linjer.extend((side.extract_text() or "").splitlines())
    return linjer


def tolk_pdf(pdf: bytes, startaar: int, feilsok_navn: str | None = None):
    linjer = pdf_til_linjer(pdf)
    if feilsok_navn:
        FEILSOK.mkdir(exist_ok=True)
        (FEILSOK / f"{feilsok_navn}.txt").write_text("\n".join(linjer), encoding="utf-8")
    dager, merknader = tolk_linjer(linjer, startaar)
    return avgrens_kirkeaar(dager, startaar), merknader


# ---------------------------------------------------------------------------
# Sammenslåing og lagring
# ---------------------------------------------------------------------------
def les_eksisterende() -> dict:
    if DATAFIL.exists():
        return json.loads(DATAFIL.read_text(encoding="utf-8"))
    return {"schema": SCHEMA, "days": [], "years": {}}


def slaa_sammen(gammel: dict, nye: dict[int, list[Dag]], idag: dt.date) -> list[dict]:
    behold = []
    for d in gammel.get("days", []):
        dato = dt.date.fromisoformat(d["date"])
        start = dato.year if dato >= forste_advent(dato.year) else dato.year - 1
        if start in nye:
            continue  # erstattes av nye data
        if dato < idag - dt.timedelta(days=3 * 365):
            continue  # rydd bort svært gamle data
        behold.append(d)
    for dager in nye.values():
        behold.extend(d.som_dict() for d in dager)
    behold.sort(key=lambda d: (d["date"], d["name"]))
    return behold


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", help="Tolk en lokal PDF (krever --aar) og skriv resultatet til skjermen")
    ap.add_argument("--aar", type=int, help="Startår for kirkeåret i PDF-en, f.eks. 2026")
    args = ap.parse_args()

    if args.pdf:
        if not args.aar:
            ap.error("--aar må oppgis sammen med --pdf")
        dager, merknader = tolk_pdf(Path(args.pdf).read_bytes(), args.aar, "lokal")
        feil, adv = kontroller(dager, args.aar)
        print(json.dumps([d.som_dict() for d in dager], ensure_ascii=False, indent=1))
        for m in merknader + adv:
            print("ADVARSEL:", m, file=sys.stderr)
        for f in feil:
            print("FEIL:", f, file=sys.stderr)
        return 1 if feil else 0

    idag = dt.date.today()
    gammel = les_eksisterende()
    nye: dict[int, list[Dag]] = {}
    aar_info = dict(gammel.get("years", {}))
    alle_feil, alle_adv = [], []

    for startaar, url in sorted(finn_pdf_adresser(idag).items()):
        try:
            pdf = _hent(url, MAKS_PDF_BYTES)
        except FileNotFoundError:
            print(f"{startaar}/{startaar + 1}: ingen PDF publisert ennå.")
            continue
        dager, merknader = tolk_pdf(pdf, startaar, f"{startaar}-{startaar + 1}")
        feil, adv = kontroller(dager, startaar)
        alle_adv += merknader + adv
        if feil:
            alle_feil += feil
            continue
        nye[startaar] = dager
        aar_info[str(startaar)] = {"source": url, "days": len(dager), "rekke": REKKER[(startaar - 2025) % 3]}
        print(f"{startaar}/{startaar + 1}: {len(dager)} dager OK")

    for a in alle_adv:
        print("ADVARSEL:", a)
    for f in alle_feil:
        print("FEIL:", f)

    dager = slaa_sammen(gammel, nye, idag)
    siste = max((d["date"] for d in dager), default=None)
    if not siste or dt.date.fromisoformat(siste) < idag:
        print("FEIL: Ingen kommende datoer i datafilen. Lagrer ikke.")
        return 1

    ny = {
        "schema": SCHEMA,
        "checked": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "covers_until": siste,
        "years": dict(sorted(aar_info.items())),
        "warnings": alle_adv[:200],
        "days": dager,
    }
    DATAFIL.parent.mkdir(exist_ok=True)
    DATAFIL.write_text(json.dumps(ny, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Lagret {len(dager)} dager, dekker til {siste}.")
    # Feil i ett år stopper jobben (så du får e-post), men gode år er likevel lagret.
    return 1 if alle_feil else 0


if __name__ == "__main__":
    sys.exit(main())
