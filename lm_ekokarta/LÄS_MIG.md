# LM Ekonomiska kartan – alla skalor

Fristående tillägg till QGIS, inte från Lantmäteriet. Hämtar Lantmäteriets ekonomiska karta (öppna data, CC0) över ett område och levererar georefererade blad i 1:10 000 eller 1:20 000; 1:20 000-bladen georefereras mot kartans eget tryckta rutnät. Där båda skalorna finns avgör utgåvevalet (nyaste eller äldsta) vilket blad som tas.

Öppna **Insticksprogram → Ekonomiska kartan → Hämta ekonomiska kartan…**, välj område och utmapp och tryck *Hämta*. I utmappen hamnar bladen (`blad/`, tryckåret i filnamnet), en VRT över hela området, bladlagret `blad.gpkg` och `rapport.txt` med källa, år, metod och lägesfel per blad.

Samma sak finns som Processing-algoritm, `lmeko:hamta_ekonomiska_kartan`, för batch och Model Designer.

Bladen är från olika år (1942–1988), och VRT:n blandar dem. Ett blad som inte klarar kontrollerna lämnas utanför, med orsaken i rapporten. Hela beskrivningen, med kända begränsningar: README på https://github.com/kaje-home/lm-ekonomiska-kartan-alla-skalor
