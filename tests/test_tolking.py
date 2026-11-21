"""Tester for tolkingen. Kjør: python -m pytest tests  (eller python tests/test_tolking.py)"""
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hent_kirkear as hk  # noqa: E402

EKSEMPEL = """[Utskrift: 03.01.2024] Kirkeårets tekster 2026-2027 – side 1
KALENDER OVER KIRKEÅRSDAGER I DEN NORSKE KIRKE
Fra og med 1. søndag i adventstiden 2026 leses tekstene etter rekke II.
1. søndag i adventstiden – Søndag 29. november 2026
II Jes 62,10–12 Se, din frelse kommer
Rom 13,11–14 Natten er snart slutt
Luk 4,16–22a Jesus i synagogen i Nasaret
Matt 21,1–11 Jesus rir inn i Jerusalem
2. søndag i adventstiden – Søndag 6. desember 2026
II
Jes 11,1–10 Et skudd fra Isais stubbe
1 Tess 5,1–11 Herrens dag
Luk 21,25–33 Tegn i sol og måne
Julaften – Torsdag 24. desember 2026
A Jes 9,1–6 Et barn er født oss
Luk 2,1–14 Jesu fødsel
2. søndag i påsketiden – Søndag 4. april 2027
II 1 Mos 2,8–9; 3,1–8 Livets tre
eller
Apg 3,1–10 Peter helbreder en lam mann
1 Pet 1,3–9 Et levende håp
Joh 21,1–14 Jesus viser seg ved sjøen
Vingårdssøndag/14. søndag i
treenighetstiden – Søndag 22. august 2027
II Jes 64,4b–65,2 Herren søker folket
Fil 2,12–16 Arbeid på frelsen
Matt 20,1–16 Arbeiderne i vingården
[Utskrift: 03.01.2024] Kirkeårets tekster 2026-2027 – side 9
Domssøndag/Kristi kongedag – Søndag 21. november
II Salme 2,1–12 Kongen på Sion
Åp 1,4b–8 Han kommer med skyene
Matt 25,31–46 Den ytterste dom
1. søndag i adventstiden – Søndag 28. november 2027
III Jes 12,1–6 Lovsang for Herrens frelse
"""


def tolk():
    return hk.tolk_linjer(EKSEMPEL.splitlines(), 2026)


def test_forste_advent():
    assert hk.forste_advent(2026) == dt.date(2026, 11, 29)
    assert hk.forste_advent(2027) == dt.date(2027, 11, 28)
    assert hk.forste_advent(2022) == dt.date(2022, 11, 27)  # juledag på søndag
    assert hk.forste_advent(2025) == dt.date(2025, 11, 30)


def test_forventet_rekke():
    assert hk.forventet_rekke(dt.date(2026, 11, 22)) == "I"
    assert hk.forventet_rekke(dt.date(2026, 11, 29)) == "II"
    assert hk.forventet_rekke(dt.date(2027, 11, 28)) == "III"
    assert hk.forventet_rekke(dt.date(2028, 12, 3)) == "I"


def test_overskrifter_og_rekke():
    dager, _ = tolk()
    navn = [(d.dato.isoformat(), d.navn, d.rekke) for d in dager]
    assert navn[0] == ("2026-11-29", "1. søndag i adventstiden", "II")
    assert navn[1] == ("2026-12-06", "2. søndag i adventstiden", "II")
    assert navn[2] == ("2026-12-24", "Julaften", "A")
    assert ("2027-08-22", "Vingårdssøndag/14. søndag i treenighetstiden", "II") in navn
    # År mangler i overskriften -> utledes
    assert ("2027-11-21", "Domssøndag/Kristi kongedag", "II") in navn


def test_lesninger_eller_og_fortelling():
    dager, _ = tolk()
    d1 = dager[0]
    assert [l["ref"] for l in d1.lesninger] == ["Jes 62,10–12", "Rom 13,11–14", "Luk 4,16–22a"]
    assert d1.ekstra[0]["ref"] == "Matt 21,1–11"
    pask = next(d for d in dager if d.navn.startswith("2. søndag i påsketiden"))
    assert pask.lesninger[0]["ref"] == "1 Mos 2,8–9; 3,1–8"
    assert pask.lesninger[0]["alt"][0]["ref"] == "Apg 3,1–10"
    assert len(pask.lesninger) == 3


def test_avgrensning():
    dager, _ = tolk()
    inne = hk.avgrens_kirkeaar(dager, 2026)
    assert all(d.dato < dt.date(2027, 11, 28) for d in inne)
    assert inne[0].navn == "1. søndag i adventstiden"


def test_kontroll_avviser_for_lite():
    dager, _ = tolk()
    feil, _ = hk.kontroller(hk.avgrens_kirkeaar(dager, 2026), 2026)
    assert feil  # for få dager -> skal aldri lagres


def test_ekte_pdf_rundtur(tmp_path=None):
    """Lager en PDF med samme tekst og sjekker at PDF-lesingen gir samme resultat."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    import io

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for linje in EKSEMPEL.splitlines():
        if y < 60:
            c.showPage()
            y = 800
        c.drawString(40, y, linje)
        y -= 14
    c.save()
    dager, _ = hk.tolk_linjer(hk.pdf_til_linjer(buf.getvalue()), 2026)
    assert [d.navn for d in dager] == [d.navn for d in tolk()[0]]


if __name__ == "__main__":
    for navn, f in list(globals().items()):
        if navn.startswith("test_"):
            f()
            print("OK", navn)
