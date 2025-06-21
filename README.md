# 🤖 Ultimate Discord Management Bot z Modułem Monitorowania Produktów 🛒

Witaj w **Ultimate Discord Management Bot**! Ten wszechstronny bot został zaprojektowany, aby zautomatyzować i usprawnić zarządzanie serwerem Discord, oferując jednocześnie unikalny moduł do monitorowania cen i dostępności produktów online. Niezależnie od tego, czy prowadzisz małą społeczność, czy duży serwer gamingowy, ten bot dostarczy Ci narzędzi niezbędnych do efektywnego zarządzania i angażowania użytkowników.

## ✨ Kluczowe Funkcje

Nasz bot jest wyposażony w szeroką gamę modułów, które zaspokoją różnorodne potrzeby Twojego serwera:

*   🛡️ **Zaawansowana Moderacja & Auto-Moderacja:**
    *   System kar (wyciszenia, bany, wyrzucenia, ostrzeżenia) z możliwością ustawiania czasu trwania i powodów.
    *   Automatyczne logowanie akcji moderatorskich i przypadków.
    *   Filtrowanie wulgaryzmów, linków z zaproszeniami i spamu.
    *   Konfigurowalny kanał logów dla akcji automatycznej moderacji.
    *   Historia kar użytkownika.
*   ✅ **Systemy Weryfikacji Użytkowników:**
    *   **Weryfikacja przez reakcję:** Użytkownicy otrzymują rolę po kliknięciu reakcji pod wiadomością.
    *   **Weryfikacja przez quiz:** Użytkownicy muszą odpowiedzieć poprawnie na serię pytań w wiadomościach prywatnych, aby uzyskać dostęp.
    *   Możliwość ustawienia roli dla niezweryfikowanych i zweryfikowanych użytkowników.
*   🌟 **System XP i Poziomów:**
    *   Użytkownicy zdobywają punkty doświadczenia (XP) za aktywność na serwerze.
    *   Automatyczne awansowanie na kolejne poziomy.
    *   Konfigurowalne nagrody za osiągnięcie określonych poziomów (role, niestandardowe wiadomości).
    *   Tablica wyników (`/leaderboard`) i możliwość sprawdzenia swojego rankingu (`/rank`).
*   🗣️ **Role za Aktywność (Liczba Wiadomości):**
    *   Automatyczne przyznawanie ról na podstawie liczby wysłanych wiadomości.
    *   Możliwość konfiguracji progów wiadomości dla poszczególnych ról.
*   ⏱️ **Role Czasowe:**
    *   Możliwość przyznawania ról na określony czas.
    *   Automatyczne usuwanie roli po upływie czasu.
*   📊 **System Ankiet:**
    *   Tworzenie ankiet z wieloma opcjami.
    *   Głosowanie za pomocą reakcji.
    *   Możliwość ustawienia czasu trwania ankiety.
    *   Automatyczne ogłaszanie wyników.
*   📝 **Niestandardowe Komendy:**
    *   Tworzenie własnych komend z odpowiedziami tekstowymi lub w formie osadzonych wiadomości (embed).
    *   Możliwość ustawienia niestandardowego prefiksu dla tych komend.
*   🤫 **Anonimowy Feedback:**
    *   Użytkownicy mogą anonimowo przesyłać opinie i sugestie na wyznaczony kanał.
*   🎉 **System Losowań (Giveaways):**
    *   Tworzenie losowań z nagrodami, określoną liczbą zwycięzców i czasem trwania.
    *   Możliwość ustawienia warunków uczestnictwa (wymagana rola, minimalny poziom).
    *   Automatyczne wybieranie i ogłaszanie zwycięzców.
*   🛒 **Monitorowanie Produktów (X-Kom):**
    *   Dodawanie produktów z serwisu X-Kom do listy obserwowanych.
    *   Automatyczne sprawdzanie zmian cen i dostępności.
    *   Powiadomienia o zmianach dla użytkowników obserwujących dany produkt.
    *   Codzienne raporty o zmianach cen i najlepszych okazjach na dedykowanym kanale.
    *   Historia cen produktu.

## 🚀 Instalacja i Konfiguracja

1.  **Dodaj Bota na Serwer:**
    *   Aby dodać bota na swój serwer Discord, potrzebujesz jego unikalnego linku zaproszenia. Zazwyczaj generuje się go w portalu dla deweloperów Discord, upewniając się, że bot ma odpowiednie uprawnienia (zalecane: Administrator, lub szczegółowe uprawnienia jak Zarządzanie Rolami, Zarządzanie Kanałami, Wysyłanie Wiadomości, Czytanie Historii Wiadomości, Banowanie, Wyrzucanie itp.).

2.  **Wymagania Systemowe:**
    *   Python 3.8+
    *   Zależności wymienione w pliku `requirements.txt` (instalowane przez `pip install -r requirements.txt`). Główne zależności to:
        *   `discord.py`
        *   `python-dotenv`
        *   `requests`
        *   `beautifulsoup4`
        *   `aiohttp` (zazwyczaj jako zależność `discord.py`)
        *   `aiosqlite`

3.  **Konfiguracja Zmiennych Środowiskowych:**
    *   Utwórz plik `.env` w głównym katalogu projektu.
    *   Dodaj do niego swój token bota:
        ```env
        DISCORD_BOT_TOKEN=TWOJ_TOKEN_BOTA_TUTAJ
        ```
    *   Jeśli w przyszłości bot będzie korzystał z zewnętrznych API (np. do innych sklepów), tutaj również umieścisz odpowiednie klucze API.

4.  **Uruchomienie Bota:**
    *   Po zainstalowaniu zależności i skonfigurowaniu pliku `.env`, uruchom bota za pomocą polecenia:
        ```bash
        python main.py
        ```

5.  **Podstawowa Konfiguracja Bota na Serwerze:**
    *   Wiele funkcji bota wymaga wstępnej konfiguracji za pomocą komend slash. Przykłady:
        *   Ustawienie kanału logów moderacyjnych: `/set_actions_log_channel <kanał>`
        *   Ustawienie roli dla wyciszonych: `/set_muted_role <rola>`
        *   Ustawienie roli weryfikacyjnej (dla weryfikacji przez reakcję): `/set_verification_role <rola>`
        *   Ustawienie kanału dla raportów o produktach: `/set_product_report_channel <kanał>`
    *   Zaleca się przejrzeć dostępne komendy administracyjne, aby dostosować bota do specyfiki serwera.

## 📜 Użycie Komend (Przykłady)

Bot wykorzystuje głównie komendy slash (`/`) dla łatwości użycia. Poniżej kilka przykładów:

**Moderacja:**
*   `/mute <użytkownik> <czas> [jednostka] <powód>` - Wycisza użytkownika.
*   `/ban <użytkownik> [czas] [jednostka] <powód>` - Banuje użytkownika.
*   `/kick <użytkownik> <powód>` - Wyrzuca użytkownika.
*   `/warn <użytkownik> <powód>` - Ostrzega użytkownika.
*   `/history <użytkownik>` - Wyświetla historię kar użytkownika.
*   `/add_banned_word <słowo>` - Dodaje słowo do listy zakazanych (auto-moderacja).
*   `/toggle_filter <nazwa_filtra> <status>` - Włącza/wyłącza filtry (np. `profanity`, `invites`).

**Weryfikacja:**
*   `/set_welcome_message [treść]` - Ustawia wiadomość powitalną/instrukcję dla weryfikacji przez reakcję.
*   `/set_verification_role <rola>` - Ustawia rolę przyznawaną po weryfikacji przez reakcję.
*   `/verify` - Publikuje wiadomość do weryfikacji przez reakcję.
*   `/set_unverified_role <rola>` - Ustawia rolę dla użytkowników przed weryfikacją quizową.
*   `/add_quiz_question <pytanie> <odpowiedź>` - Dodaje pytanie do quizu weryfikacyjnego.
*   `/verify_me` - Rozpoczyna quiz weryfikacyjny (komenda dla użytkownika).

**System XP i Poziomów:**
*   `/rank [użytkownik]` - Wyświetla poziom i XP użytkownika.
*   `/leaderboard [strona]` - Pokazuje ranking użytkowników.
*   `/add_level_reward <poziom> [rola] [wiadomość]` - Dodaje nagrodę za osiągnięcie poziomu.

**Role za Aktywność:**
*   `/add_activity_role <rola> <liczba_wiadomości>` - Dodaje rolę przyznawaną za aktywność.

**Ankiety:**
*   `/create_poll <pytanie> <opcja1> <opcja2> ... [czas_trwania]` - Tworzy nową ankietę.

**Niestandardowe Komendy:**
*   `/set_custom_prefix <prefix>` - Ustawia prefiks dla niestandardowych komend.
*   `/addcustomcommand <nazwa> <typ_odpowiedzi> <treść>` - Tworzy nową komendę (typ: `text` lub `embed`).

**Monitorowanie Produktów:**
*   `/watch_product <URL_produktu_X-Kom>` - Dodaje produkt do obserwowania.
*   `/unwatch_product <ID_produktu>` - Przestaje obserwować produkt.
*   `/my_watchlist` - Wyświetla Twoją listę obserwowanych produktów.
*   `/set_product_report_channel <kanał>` - Ustawia kanał dla codziennych raportów.

**Inne:**
*   `/feedback <wiadomość>` - Wysyła anonimową opinię.
*   `/create_giveaway <nagroda> <liczba_zwycięzców> <czas_trwania> [kanał] [rola_wymagana] [min_poziom]` - Tworzy nowe losowanie.

*Pełna lista komend jest zazwyczaj dostępna po wpisaniu `/` na czacie Discord i wybraniu bota.*

## 🏗️ Architektura

Bot został zbudowany w oparciu o następujące technologie i zasady:

*   **Język Programowania:** Python 3
*   **Biblioteka Discord API:** `discord.py` (z rozszerzeniami `commands` i `tasks`)
*   **Baza Danych:** SQLite (plik `bot_config.db`) do przechowywania konfiguracji serwerów, danych użytkowników, obserwowanych produktów, itp.
*   **Modułowość:** Kod jest zorganizowany w moduły (cogs lub oddzielne pliki .py), aby ułatwić zarządzanie i rozwój poszczególnych funkcji (np. `moderation.py`, `leveling.py`, `product_monitoring.py`).
*   **Obsługa Zmiennych Środowiskowych:** `python-dotenv` do bezpiecznego zarządzania tokenem bota.
*   **Web Scraping (dla monitorowania produktów):** Biblioteki `requests` do pobierania zawartości stron i `BeautifulSoup4` do parsowania HTML.
*   **Asynchroniczność:** Wykorzystanie `async` i `await` do efektywnej obsługi wielu operacji jednocześnie, co jest kluczowe dla botów Discord.
*   **Zadania w Tle (`tasks`):** Do cyklicznego sprawdzania statusów (np. wygasłe wyciszenia, zakończone losowania, skanowanie produktów, wysyłanie raportów).

## 🤝 Wkład (Contributing)

Chętnie przyjmiemy pomoc w rozwoju tego projektu! Jeśli masz pomysły na nowe funkcje, usprawnienia lub znalazłeś błąd, zapraszamy do współpracy.

1.  **Zgłaszanie Błędów:** Prosimy o tworzenie zgłoszeń (Issues) na GitHubie projektu, opisując dokładnie problem i kroki do jego reprodukcji.
2.  **Propozycje Funkcji:** Utwórz zgłoszenie (Issue) z etykietą "enhancement" lub "feature request", opisując swoją propozycję.
3.  **Pull Requests:**
    *   Sforkuj repozytorium.
    *   Stwórz nową gałąź dla swoich zmian (`git checkout -b nazwa-twojej-funkcji`).
    *   Wprowadź zmiany i przetestuj je.
    *   Upewnij się, że Twój kod jest zgodny ze standardami projektu (np. PEP 8).
    *   Utwórz Pull Request do głównej gałęzi projektu, dokładnie opisując wprowadzone zmiany.

## 📄 Licencja

Ten projekt jest udostępniany na licencji **MIT**. Szczegóły znajdują się w pliku `LICENSE` (jeśli istnieje) lub poniżej:

```
MIT License

Copyright (c) 2025 ZayoDev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

Dziękujemy za zainteresowanie Ultimate Discord Management Bot! Mamy nadzieję, że będzie on cennym narzędziem dla Twojej społeczności. ✨
