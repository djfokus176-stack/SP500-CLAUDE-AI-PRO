# SP500 Signal AI Pro v7.3 — poprawiona wersja przekazanego app(2).py

**Uwaga:** W załączonych zrzutach widać inną aplikację — `CLAUDE LIVE SIGNAL — PROGRAM 2 V6`. Ten pakiet jest **aktualizacją pliku `app(2).py` (v7.2)**, a nie modyfikacją kodu niewysłanego Programu 2.

## Co zmieniono

- Duży panel przy wykresie: `WAIT / OBSERWUJ LONG / OBSERWUJ SHORT / OTWARTA POZYCJA PAPER` oraz ostatnie zamknięcie.
- Wspólna funkcja rozpoznawania układu technicznego dla silnika i panelu; wcześniej mogły powstawać rozbieżności przy zmianach w kodzie.
- Historia strzałek i zamknięć **SIM** bezpośrednio na własnym wykresie Plotly, całkowicie osobna od zapisanych pozycji PAPER. To historyczny backtest, nie historia rzeczywistych alertów.
- Podgląd jeszcze niezamkniętej świecy jako *wczesna, niepotwierdzona obserwacja* — nie generuje transakcji.
- Poprawiony filtr trybu STRICT: brak potwierdzonego trendu HTF nie jest zgodą na wejście.
- Dokładniejszy komunikat HTTP z Capital.com, wskazówki do diagnostyki logowania/API.
- Blokada auto-tradingu DEMO na nieświeżych danych oraz po przekroczeniu spreadu.
- Poprawka funkcji dźwięku: JavaScript jako HTML we wspieranym komponencie, nie jako URL do iframe.

## Instalacja przez GitHub + Streamlit

1. Rozpakuj ZIP.
2. W repozytorium GitHub wybierz **Add file → Upload files** i prześlij `app.py`, `lab.py`, `requirements.txt`, `README.md`, `.gitignore`.
   Jeśli pliki już istnieją, GitHub pozwoli przygotować ich aktualizację — sprawdź przed zatwierdzeniem, czy nadpisujesz właściwy projekt.
3. W Streamlit Community Cloud upewnij się, że aplikacja korzysta z **tego samego repozytorium**, gałęzi `main` i ścieżki `app.py`.
4. W Streamlit **Manage app → Settings → Secrets** ustaw sekrety (przykładowy szablon poniżej; NIE umieszczaj haseł w repozytorium):

```toml
CAPITAL_DEMO = "1"
CAPITAL_API_KEY = "TU_KLUCZ_API"
CAPITAL_IDENTIFIER = "TU_LOGIN"
CAPITAL_PASSWORD = "TU_HASLO_DO_KLUCZA_API"
APP_PASSWORD = "DODATKOWE_HASLO_DO_APLIKACJI"
```

5. Zapisz sekrety i uruchom ponownie aplikację. Poczekaj na **potwierdzone świeże świece US500**. Sprawdź sekcję **Diagnostyka**.

**Ważne:** API Capital.com korzysta z hasła utworzonego w procesie generowania klucza API; nie musi to być zwykłe hasło logowania na stronę. Sprawdź również, czy używasz właściwego środowiska (DEMO/LIVE) i czy klucz jeszcze działa.

## Dlaczego nadal może pokazywać WAIT?

- Brak danych logowania/API Capital.com albo HTTP 401/403.
- Brak notowań, uśpienie aplikacji, opóźnione dane, brak sesji rynkowej.
- Zbyt duży spread, trwające okno makro, limit dzienny albo brak zgodnej formacji.
- Sygnał potwierdzamy tylko po zamknięciu świecy; wskazania z niezakończonej świecy mogą się zmieniać.

**Nie testowano z Twoim kontem Capital.com** (nie otrzymaliśmy dostępu ani kluczy). Nie da się obiecać, że połączenie już działa. Pakiet pozostaje narzędziem PAPER/DEMO, a wyniki symulacji nie stanowią dowodu przewagi na rynku.
