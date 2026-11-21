"""Tester for tolkingen. Kjør: python -m pytest -q tests"""
import datetime as dt
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import hent_kirkear as hk  # noqa: E402

# Samme oppsett som Kirkens PDF: to spalter, fet overskrift, kursiv tekst,
# kolonner for rekke (x=53), henvisning (x=75) og tittel (x=146). Høyre spalte +280.
VENSTRE = [
    ("B", "1. søndag i adventstiden – Søndag 29. november 2026"),
    ("T", "II", "Jes 61,1–3", "Et nådens år med gjengjeld"),
    ("T", "", "Åp 5,1–5", "Boken med de sju segl"),
    ("T", "", "Luk 4,16–22a", "Jesus står frem i Nasaret"),
    ("B", "Julenatt /Ottesang – Torsdag 24. desember/Fredag 25."),
    ("B", "desember 2026"),
    ("T", "A", "Mika 5,1–4a", "Fredsfyrsten fra Betlehem"),
    ("T", "", "1 Joh 1,1–4", "Livets ord"),
    ("T", "", "Matt 1,18–25", "Josef og Jesu fødsel"),
]
HOYRE = [
    ("B", "2. søndag i åpenbaringstiden – Søndag 10. januar 2027"),
    ("T", "II", "2 Mos 1,22–", "Moses blir født"),
    ("T", "", "2,10", ""),
    ("T", "", "Ef 1,7–12", "Guds viljes mysterium"),
    ("T", "", "Mark 1,3–11", "Døperen Johannes og Jesu dåp"),
    ("B", "2. søndag i påsketiden – Søndag 4. april 2027"),
    ("T", "II", "Jer 31,1–6", "Enda en gang vil jeg bygge deg"),
    ("T", "", "eller Apg 1,1–5", "Løftet om Ånden"),
    ("T", "", "1 Joh 5,1–5", "Troen seirer"),
    ("T", "", "Joh 21,15–19", "Elsker du meg?"),
    ("B", "16. søndag i treenighetstiden – Søndag 27. september 2028"),
    ("T", "III", "Salme 13,2–6", "Hvor lenge"),
]


def lag_pdf() -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    hoyde = A4[1]
    c.setFont("Times-Roman", 9)
    c.drawString(24, hoyde - 40, "KALENDER OVER KIRKEÅRSDAGER – innledning")
    for spalte, linjer in ((0, VENSTRE), (280, HOYRE)):
        y = hoyde - 83
        for l in linjer:
            if l[0] == "B":
                c.setFont("Times-BoldItalic", 9)
                c.drawString(53 + spalte, y, l[1])
            else:
                c.setFont("Times-Italic", 9)
                for x, tekst in ((53, l[1]), (75, l[2]), (146, l[3])):
                    if tekst:
                        c.drawString(x + spalte, y, tekst)
            y -= 11
    c.setFont("Times-Roman", 9)
    c.drawString(360, 60, "[Utskrift: 03.01.2024] Kirkeårets tekster 2026-2027 – side 1")
    c.save()
    return buf.getvalue()


def tolk():
    return hk.tolk_rader(hk.pdf_til_rader(lag_pdf()), 2026)


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


def test_spalter_og_overskrifter():
    dager, _ = tolk()
    navn = [(d.dato.isoformat(), d.navn, d.rekke) for d in dager]
    assert navn[0] == ("2026-11-29", "1. søndag i adventstiden", "II")
    # Overskrift over to linjer, to datoer -> siste dato, ingen «retting»
    assert navn[1] == ("2026-12-25", "Julenatt/Ottesang", "A")
    # Høyre spalte leses etter venstre
    assert navn[2] == ("2027-01-10", "2. søndag i åpenbaringstiden", "II")


def test_lesninger():
    dager, _ = tolk()
    assert [l["ref"] for l in dager[0].lesninger] == ["Jes 61,1–3", "Åp 5,1–5", "Luk 4,16–22a"]
    # Henvisning brutt over to linjer
    assert dager[2].lesninger[0]["ref"] == "2 Mos 1,22–2,10"
    # «eller» gir alternativ tekst
    pask = dager[3]
    assert pask.lesninger[0]["alt"][0]["ref"] == "Apg 1,1–5"
    assert [l["ref"] for l in pask.lesninger] == ["Jer 31,1–6", "1 Joh 5,1–5", "Joh 21,15–19"]


def test_trykkfeil_i_dato_rettes():
    dager, merknader = tolk()
    assert dager[4].dato == dt.date(2028, 9, 24)
    assert any("Rettet trykkfeil" in m for m in merknader)


def test_kontroll_avviser_for_lite():
    dager, _ = tolk()
    feil, _ = hk.kontroller(hk.avgrens_kirkeaar(dager, 2026), 2026)
    assert feil  # for få dager -> skal aldri lagres


if __name__ == "__main__":
    for navn, f in list(globals().items()):
        if navn.startswith("test_"):
            f()
            print("OK", navn)
