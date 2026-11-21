# Kirkeårsdata for ordetbe.no

Dette repoet henter **Kirkeårets tekster** fra Den norske kirkes ressursbank én gang i måneden
og lagrer dem som én fil: [`data/kirkear.json`](data/kirkear.json).

WordPress-tillegget **Ordet.be Kirkeår** leser bare denne filen. Nettstedet er derfor ikke
avhengig av kirken.no, og tillegget har alltid en lagret kopi av siste gode versjon.

## Slik virker det

1. GitHub kjører jobben den 3. hver måned (og når du trykker «Run workflow»).
2. Skriptet laster ned kalender-PDF-ene for inneværende og de fire neste kirkeårene.
   Kirken publiserer dem flere år fram i tid.
3. PDF-ene tolkes, og hvert kirkeår kontrolleres:
   - minst 50 dager
   - nesten alle søndager funnet
   - tekstrekken stemmer med rotasjonen (2025/26 = I, 2026/27 = II, 2027/28 = III, …)
4. Bare godkjente år lagres. Feiler ett år, beholdes de gamle dataene for det året.
   Jobben markeres som feilet, og GitHub sender deg e-post.

Kostnad: 0 kr. Et offentlig repo har ubegrenset gratis kjøretid i GitHub Actions.

## Oppsett (én gang, ca. 10 minutter)

1. Opprett et **offentlig** repo på GitHub, f.eks. `kirkear-data`, og last opp alle filene herfra.
   Dataene er ikke hemmelige, og et offentlig repo gjør at WordPress kan lese filen uten passord.
2. Gå til **Settings → Actions → General → Workflow permissions** og velg **Read and write permissions**.
3. Gå til **Actions → Oppdater kirkeårsdata → Run workflow**. Vent til den er grønn (1–2 minutter).
4. Åpne `data/kirkear.json`, trykk **Raw** og kopier adressen. Den ser slik ut:
   `https://raw.githubusercontent.com/1457ms/kirkear-data/main/data/kirkear.json`
5. Lim adressen inn i WordPress under **Verktøy → Kirkeår → Adresse til datafilen**.

## Hvis jobben feiler

- Åpne kjøringen under **Actions**. Loggen sier hvilket år som feilet og hvorfor.
- Nederst på siden ligger vedlegget **feilsok**, med teksten slik den ble lest ut av PDF-ene.
  Den trengs hvis tolkingen må justeres, for eksempel fordi Kirken har endret oppsettet.
- Nettstedet fortsetter med de lagrede dataene i mellomtiden. Det har normalt data for flere år framover.

**Nødløsning:** `data/kirkear.json` er en vanlig tekstfil og kan rettes direkte på GitHub
(blyantikonet). Formatet per dag er:

```json
{"date": "2026-11-29", "name": "1. søndag i adventstiden", "rekke": "II",
 "readings": [{"ref": "Jes 62,10–12", "title": "…"}, {"ref": "…"}, {"ref": "…"}]}
```

## Vedlikehold

- **Ingen fast vedlikehold.** Jobben kjører hver måned, også når ingenting er endret.
  Da oppdateres feltet `checked`, så GitHub ikke slår av jobben etter 60 dager uten aktivitet.
- WordPress-tillegget varsler hvis jobben ikke har kjørt på 45 dager, eller hvis dataene snart tar slutt.

## Lokal test

```bash
pip install -r requirements.txt
python -m pytest -q tests
python scripts/hent_kirkear.py --pdf "2026-2027 kirkeårskalender.pdf" --aar 2026
```
