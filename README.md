# LM Ekonomiska kartan – alla skalor

Rita eller välj ett område i QGIS och få Lantmäteriets ekonomiska karta över det som georefererade kartblad, i 1:10 000 där den serien finns och i 1:20 000 där den inte gör det. Du behöver inte veta vilken skala eller vilken fil som gäller var.

## ⬇️ [Ladda ner senaste versionen](https://github.com/kaje-home/lm-ekonomiska-kartan-alla-skalor/releases/latest/download/lm_ekokarta.zip)

En zip-fil som installeras i QGIS, se Snabbstart här nedanför.

## Snabbstart

1. **Installera.** Ladda ner zip-filen ovan. Öppna QGIS och välj **Insticksprogram → Hantera och installera insticksprogram…**, fliken **Installera från ZIP**. Peka på filen och tryck *Installera insticksprogram*.
2. **Öppna.** Välj **Insticksprogram → Ekonomiska kartan → Hämta ekonomiska kartan…**, eller knappen med kartbladet i verktygsfältet.
3. **Område.** Välj *Kartfönstrets utbredning*, ett *Polygonlager* (gärna bara markerade objekt) eller *Rita i kartan*.
4. **Utmapp.** Välj en tom mapp **utanför OneDrive**, till exempel `C:\Ekokartan\Uttag1`.
5. **Hämta.** När det är klart ligger kartan och ett bladlager i en grupp överst i lagerlistan.

Ingen inloggning behövs. Kräver QGIS 3.40 eller nyare (QGIS 4 går också). Provat i QGIS 3.44 och 4.2. Pluginet är experimentellt i version 0.1.

## Vad skiljer det här pluginet från andra

Det finns redan ett plugin, [Geodata: Ekonomiska kartan (Lantmäteriet)](https://github.com/matself/qgis-plugin-ekonomiska-kartan), som söker och laddar 1:10 000-bladen med Lantmäteriets världsfil. Det här gör mer än så:

| | Det här pluginet | 1:10 000-pluginet |
|---|---|---|
| 1:10 000 | ja, med granskad världsfil | ja |
| **1:20 000 (Norrlands inland, ~1 050 blad)** | **ja, georefererat automatiskt** | nej – serien saknar georeferens |
| Väljer skala efter området | ja | – |
| Klippt per blad, genomskinliga kanter | ja (alfaband) | nej |
| Omprojicerat till SWEREF 99 TM (eller valfritt) | ja | nej (RT 90) |
| VRT över hela området | ja | nej |
| Rapport per blad: källa, år, metod, lägesfel | ja | – |
| Processing-algoritm (batch, Model Designer) | ja | nej |

Över stora delar av Jämtland, Härjedalen och Norrbottens och Västerbottens inland finns ekonomiska kartan **bara** i 1:20 000. Lantmäteriet levererar de bladen som skanningar av hela det tryckta arket, med marginal och teckenförklaring, utan världsfil och utan koordinater. Det här pluginet räknar ut var bladet ligger ur bladnamnet och georefererar det mot kartans eget tryckta kilometerrutnät.

## Vad du får

I utmappen:

| Fil | Innehåll |
|---|---|
| `blad/19e6g_1971_10k.tif` | ett 1:10 000-blad, 1 m pixlar |
| `blad/J141-20F6-7g-h74_1974_20k.tif` | ett 1:20 000-blad, 2 m pixlar |
| `ekonomiska_kartan_1965-1977.vrt` | alla blad i en mosaik, i ordning efter utgåvevalet |
| `blad.gpkg` | bladrutorna med källa, år, metod och lägesfel per blad |
| `rapport.txt` | samma sak som text, en rad per blad |

**Varje blad klipps mot sin ruta och får ett alfaband.** Utanför bladrutan är bilden genomskinlig, så det blir inga vita eller svarta kanter, och grannblad täcker inte varandra. I SWEREF 99 TM är rutnätet vridet knappt en grad (omkring 0,7°) mot RT 90, så kilarna finns på varje blad.

**Tryckåret står i varje filnamn**, i bladlagret och i rapporten. Bladen är från olika år, och **VRT:n blandar dem**: ett blad från 1965 kan ligga bredvid ett från 1977. Vill du veta vilket år du tittar på, tänd bladlagret. Lantmäteriet anger 1935–1978 för serien. Filnamnen på de öppna bladen bär tryckår från 1942 till 1988.

**Utgåva.** Omkring 330 blad i 1:10 000 finns från mer än ett år. Välj *Nyaste*, *Äldsta* eller *Alla utgåvor*. Med alla utgåvor får varje år en egen fil, och VRT:n visar den nyaste överst.

**Där båda skalorna finns gäller utgåvevalet även mellan dem.** Med *Nyaste* tas det yngsta bladet och med *Äldsta* det äldsta, oavsett skala; är bladen från samma år tas 1:10 000. Vägras bladet tas nästa. Ett blad som ingen ruta behöver hämtas inte. Ett 1:20 000-blad täcker fyra 1:10 000-rutor, så båda skalorna kan ändå hamna i samma mosaik. VRT:n ordnas efter samma regel, och rapporten skriver för varje ruta där skalorna överlappar vilket blad som ligger överst, vad som ligger under och vad som inte hämtades. Med *Båda serierna* hämtas alla blad i båda skalorna, ordnade efter samma regel.

**1:10 000-bladen från 1950-talet i Norrland kan vara nästan rena fotokartor**: flygbilden med lite tryckt kartinnehåll. Ett sådant blad kan vinna över ett yngre 1:20 000-blad med *Äldsta*, eller med *Nyaste* där inget yngre blad finns. Se tryckåret i bladlagret innan du klassar markslag (nedan).

**Koordinatsystem.** Förvalt är SWEREF 99 TM (EPSG:3006). Väljer du RT 90 2,5 gon V (EPSG:3021), seriens eget system, omsamplas 1:10 000-bladen inte alls. Det är att föredra om du ska klassa pixlar efter färg (se nedan).

## Hur 1:20 000-bladen georefereras

Bladnamnet, till exempel `J141-20F6-7g-h74`, ger bladets läge i RT 90: samma 5 km-rutnät som 1:10 000-serien, två rutor brett och högt. Var kartytan ligger i skanningen säger inget, och skanningarna är vridna upp till en knapp grad och papperet har krympt omkring en halv procent. Pluginet använder därför kartans eget tryckta rutnät som referens, inte landskapet:

- **Rutnätsmetoden**, på blad med heldraget kilometerrutnät: rutnätets 81 korsningar mäts och blir passpunkter. Felet (lämna-en-utanför, 95 %) får vara högst 4 m; provade blad ligger på 1,2–2,8 m.
- **Kantmetoden**, på blad där rutnätet bara är tryckt som streck i marginalen: kartytans kant, kilometerstrecken och ibland ett kors mitt på bladet. Felet får vara högst 6 m. Prövat mot rutnätsbladen underskattar måttet det verkliga felet med omkring 2 m, så 6 m motsvarar omkring 8 m.

Båda ger en GeoTIFF över exakt bladets 10 × 10 km med 2 m pixlar. **Ett blad som inte klarar kontrollerna lämnas utanför, med orsaken i rapporten.** Hellre ett blad för lite än ett som ligger fel. Lägesfelet gäller georefereringen, inte kartans innehåll: vad kartan själv visar är osäkrare än så.

Metoden behöver inga andra kartor och fungerar lika i fjällen som i odlingsbygden. Den är densamma som i LM Fältunderlag och beskrivs utförligt i dess kravspecifikation.

## Användning utanför arkeologin

Ekonomiska kartan är en fotokarta med tryckt fastighetsindelning, bebyggelse, vägar, åker och äng, ortnamn och fornlämningar, gjord mellan 1940- och 1980-talet. Den visar markanvändningen innan mycket av dagens skogsbruk, igenväxning och tätortsutbyggnad.

- **Jordbruksmark och åkerarealer.** Åkern är tryckt med egen färg. Med bladen i ett fast koordinatsystem går den att digitalisera eller klassa efter färg och jämföra med dagens blockdatabas eller marktäcke. Välj RT 90 för färgklassning: då omsamplas inte 1:10 000-bladen, och färgerna förblir som de trycktes. 1:20 000-bladen omsamplas alltid ett varv (de georefereras).
- **Markslag ur fotokartor.** 1:10 000-bladen från 1950-talet i Norrland kan vara nästan rena fotokartor, med lite eller inget av den tryckta åker- och ängsfärgen. Klassar du markslag efter kartans färger och tecken fungerar de bladen inte som de yngre: markslaget får tolkas ur flygbildens gråtoner, med andra regler och större osäkerhet. Ett uttag kan blanda båda sorterna, så klassa per blad efter tryckåret, eller välj *Nyaste* för att få det yngre kartbladet där det finns.
- **Skogshistoria och igenväxning:** hagar, slåtterängar och fäbodvallar som i dag är skog.
- **Bebyggelse och vägar:** torp, gårdar och stigar som inte längre finns.
- **Ortnamn:** namn på myrar, slåtter och vallar som inte står på dagens kartor.

Tänk på årtalen: ett uttag över ett större område blandar ofta blad från olika årtionden.

## Processing, batch och Model Designer

Algoritmen heter `lmeko:hamta_ekonomiska_kartan` och finns i verktygslådan under *LM Ekonomiska kartan*. Dialogen fyller bara i den.

| Parameter | |
|---|---|
| `LAGER`, `UTBREDNING`, `GEOMETRI` | området; minst ett, flera förenas |
| `BUFFERT` | meter runt området |
| `SKALA` | 0 automatiskt, 1 bara 1:10 000, 2 bara 1:20 000, 3 båda |
| `UTGAVA` | 0 nyaste, 1 äldsta, 2 alla |
| `CRS` | bladens koordinatsystem, förval EPSG:3006 |
| `ARKIV` | valfri mapp där nedladdade och georefererade blad sparas |
| `VRT` | bygg VRT |
| `UTMAPP` | utmappen |

Utdata: `VRT_LAGER`, `BLAD` (bladlagret), `RAPPORT`, `LEVERERADE`, `UTELAMNADE` och `AR` (tryckåren). Kör den i batch för flera områden till var sin utmapp, gärna med samma arkiv.

```python
processing.run("lmeko:hamta_ekonomiska_kartan", {
    "UTBREDNING": "1440000,1450000,6960000,6975000 [EPSG:3021]",
    "UTMAPP": r"C:\Ekokartan\Uttag1", "ARKIV": r"C:\Ekokartan\Arkiv"})
```

## Arkiv

Utan arkiv laddas bladen ned till utmappen och städas bort efteråt. Med ett arkiv sparas de och hämtas inte igen:

- `ekonomiska_kartan/` – 1:10 000-bladen med världsfil, som Lantmäteriet levererar dem
- `ekonomiska_kartan/20k/` – för varje 1:20 000-blad den råa skanningen (~80–120 MB), den georefererade filen och utfallet i en `.json`

Georefereringen ger samma svar varje gång, så ett blad som redan provats provas inte om, lyckat eller inte, så länge metoden inte ändrats. Arkivet har samma uppställning som i LM Fältunderlag, och de två kan dela arkiv.

## Kända begränsningar

- **Sjörika blad** ger störst fel med kantmetoden: långa strandlinjer stör mätningen av kartytans kant. På ett blad över Strömsund var 95 % av felet under 6,8 m och det största 11,3 m. Rapporten anger felet per blad.
- **Beskurna skanningar.** Ett fåtal 1:20 000-blad (5 000 × 5 000 px, t.ex. J141-28M4-5c-d68) är skannade utan pappersmarginal. Bladgränsen syns inte, och de lämnas utanför med orsaken *ingen pappersmarginal*.
- **Svartvita blad är inte provade.** Kantmetoden vägrar skanningar som inte är i färg.
- **Några udda skanningsformat** i 1:20 000-serien är inte provade.
- **Ihoptryckta 1:10 000-blad.** Enligt en genomgång i 1:10 000-pluginet ovan är omkring 190 utgåvor skannade större än sin ruta, och Lantmäteriets världsfil trycker ihop hela skanningen till rutan. De bladen ligger fel och lämnas utanför, med orsaken. De finns ofta i en annan utgåva.
- **1:10 000-bladens läge mäts inte.** De använder Lantmäteriets världsfil som den är, granskad men inte mätt.
- **Ljus kantlinje i skarvar.** Där ett blad ligger ett par meter fel kan bladets egen kant synas som en ljus linje, 1–2 pixlar bred, mot grannbladet. Det syns mest på blad som georefererats mot kilometerstrecken i marginalen.
- **Kartan är inte rikstäckande.** Delar av landet, framför allt fjällen, saknas i båda serierna. En ruta utan karta står i bladlagret som *saknas*.
- **FTP och proxy.** Bladen hämtas med anonym FTP, och QGIS proxyinställningar följer inte med. Bakom en brandvägg som stänger FTP går det inte.
- **Ett blad i taget.** Georefereringen tar omkring 0,6 GB minne per 1:20 000-skanning, så bladen tas ett i taget.

## Data och licens

Kartdatan är Lantmäteriets öppna data, **CC0**, och hämtas direkt från `ftp://download-opendata.lantmateriet.se/Ekonomiska_kartan/`. Ingen inloggning eller avgift. Källhänvisning är inte ett krav enligt CC0, men skriv gärna *Ekonomiska kartan, Lantmäteriet*. Bladindelningskartor finns som PDF i katalogen `Bladindelningskartor` på samma FTP.

**Fristående tillägg, inte från Lantmäteriet.** Frågor om pluginet hör hemma i förrådets ärenden här på GitHub, inte hos Lantmäteriets support. Det kommer utan garantier; kontrollera lägesfelet i rapporten innan du bygger något på ett blad.

Pluginet är fri programvara under GNU General Public License version 2 (se `LICENSE`).

## Uppdateringar

Vill du få nya versioner som vanliga uppdateringar i QGIS: gör så här en gång.

1. **Insticksprogram → Hantera och installera insticksprogram…**, fliken **Inställningar**.
2. Bocka i *Visa även experimentella insticksprogram*.
3. Tryck **Lägg till…** under *Förråd av insticksprogram*. Namn: `Ekonomiska kartan`. Adress: `https://raw.githubusercontent.com/kaje-home/lm-ekonomiska-kartan-alla-skalor/main/plugins.xml`. Tryck OK.

Ändringarna version för version står i `CHANGELOG.md`.

## Felanmälan och källkod

Skriv ett ärende under *Issues*. Ta med raden för bladet ur `rapport.txt`; den säger det mesta.

Georefereringen ligger i `lm_ekokarta/lm_ekokarta_karna/`, som bara kräver numpy och GDAL och inte QGIS. Samma kärna används av LM Fältunderlag; `kontroll/jamfor_karna.py` kontrollerar att kopiorna är lika.
