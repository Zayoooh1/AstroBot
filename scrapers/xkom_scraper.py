import requests
from bs4 import BeautifulSoup
import re

def scrape_xkom_product(url: str) -> dict | None:
    """
    Scrapuje dane produktu (nazwa, cena, dostępność) ze strony X-Kom.
    Zwraca słownik z danymi lub None w przypadku błędu.
    UWAGA: Selektory CSS są PRZYKŁADOWE i mogą wymagać aktualizacji!
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # Rzuci wyjątek dla kodów błędów HTTP 4xx/5xx
        soup = BeautifulSoup(response.content, 'html.parser')

        product_data = {
            "name": None,
            "price_str": None,
            "availability_str": None
        }

        # --- Przykładowe selektory (DO WERYFIKACJI I DOSTOSOWANIA!) ---

        # Nazwa produktu
        # Często w tagu <h1> z określoną klasą lub atrybutem data
        name_tag = soup.find('h1', attrs={'data-name': 'productName'})
        if not name_tag: # Alternatywny popularny selektor
            name_tag = soup.find('h1', class_=re.compile(r'product.*name|title', re.IGNORECASE))
        if name_tag:
            product_data["name"] = name_tag.get_text(strip=True)

        # Cena produktu
        # Może być w divie/spanie z klasą typu "price", "product-price" itp.
        # X-Kom często używa dynamicznego ładowania cen, więc to może być trudne.
        # Poniżej bardzo ogólny przykład.
        price_tag = soup.find('div', class_=re.compile(r'price|PriceContainer', re.IGNORECASE))
        if price_tag:
            # Próba wyciągnięcia ceny, usuwając "zł" i inne znaki, normalizując do formatu "1234.56"
            price_text = price_tag.get_text(separator=' ', strip=True)
            # Prosty regex do wyciągnięcia liczby z groszami
            price_match = re.search(r'(\d{1,3}(?:\s?\d{3})*(?:,\d{2})?)\s*zł', price_text)
            if price_match:
                # Normalizacja: usunięcie spacji jako separatora tysięcy, zamiana przecinka na kropkę
                normalized_price = price_match.group(1).replace('\xa0', '').replace(' ', '').replace(',', '.')
                product_data["price_str"] = normalized_price
            else: # Spróbuj znaleźć cenę w meta tagu, jeśli jest
                meta_price_tag = soup.find('meta', property='product:price:amount')
                if meta_price_tag and meta_price_tag.get('content'):
                    product_data["price_str"] = meta_price_tag.get('content').strip()


        # Dostępność produktu
        # Może być oznaczona klasą, tekstem w specyficznym kontenerze.
        # Np. "Dostępny", "W magazynie", "Niedostępny", "Na zamówienie"
        # To jest bardzo specyficzne dla sklepu.
        availability_tag = soup.find('div', class_=re.compile(r'availability|stock', re.IGNORECASE))
        if availability_tag:
            availability_text = availability_tag.get_text(strip=True)
            product_data["availability_str"] = availability_text
        else: # Przykładowy fallback - szukanie tekstu
            if soup.find(string=re.compile(r"Produkt niedostępny", re.IGNORECASE)):
                product_data["availability_str"] = "Niedostępny"
            elif soup.find(string=re.compile(r"Dostępny w magazynie|Dostępny od ręki", re.IGNORECASE)):
                 product_data["availability_str"] = "Dostępny"
            elif soup.find(string=re.compile(r"Na zamówienie|Sprawdź dostępność", re.IGNORECASE)):
                 product_data["availability_str"] = "Na zamówienie"


        # Jeśli kluczowe dane nie zostały znalezione, możemy uznać scrapowanie za nieudane
        if not product_data["name"] or product_data.get("price_in_cents") is None: # Sprawdzamy price_in_cents
            print(f"Scraping X-Kom: Nie udało się znaleźć nazwy lub ceny (price_in_cents) dla {url}")
            # Zwrócenie częściowych danych, jeśli są, lub None, jeśli nic kluczowego nie ma.
            if product_data["name"] or product_data.get("price_in_cents") is not None or product_data["availability_str"]:
                 return product_data # Zwróć to co masz
            return None

        return product_data

    except requests.exceptions.RequestException as e:
        print(f"Błąd żądania HTTP dla {url}: {e}")
        return None
    except Exception as e:
        print(f"Nieoczekiwany błąd podczas scrapowania {url}: {e}")
        return None

def _parse_price_to_cents(price_text: str) -> int | None:
    """Konwertuje string ceny (np. "1 234,56 zł") na liczbę całkowitą groszy."""
    if not price_text:
        return None
    try:
        # Usuń "zł", spacje (w tym non-breaking space \xa0), zamień przecinek na kropkę
        cleaned_price = price_text.lower().replace('zł', '').replace('\xa0', '').replace(' ', '').replace(',', '.')
        price_float = float(cleaned_price)
        return int(price_float * 100)
    except ValueError:
        print(f"Nie udało się sparsować ceny '{price_text}' na grosze.")
        return None

if __name__ == '__main__':
    # Przykładowy URL do testowania (wymaga aktualnego linku do produktu X-Kom)
    # Pamiętaj, że struktura strony i selektory mogą się zmienić!
    test_url = "https://www.x-kom.pl/p/1070903-karta-graficzna-nvidia-geforce-rtx-4070-super-ventus-2x-oc-12gb-gddr6x.html" # ZASTĄP AKTUALNYM LINKIEM

    print(f"Testowanie scrapera dla X-Kom z URL: {test_url}")
    data = scrape_xkom_product(test_url)
    if data:
        print(f"Nazwa: {data.get('name')}")
        price_cents = data.get('price_in_cents')
        print(f"Cena (grosze): {price_cents}")
        if price_cents is not None:
            print(f"Cena (zł): {price_cents / 100:.2f} zł")
        print(f"Dostępność: {data.get('availability_str')}")
    else:
        print("Nie udało się pobrać danych.")

    test_url_niedostepny = "https://www.x-kom.pl/p/673500-procesor-amd-ryzen-7-amd-ryzen-7-5800x3d.html" # Przykład produktu, który może być niedostępny
    print(f"\nTestowanie scrapera dla (potencjalnie) niedostępnego produktu: {test_url_niedostepny}")
    data_niedostepny = scrape_xkom_product(test_url_niedostepny)
    if data_niedostepny:
        print(f"Nazwa: {data_niedostepny.get('name')}")
        price_cents_n = data_niedostepny.get('price_in_cents')
        print(f"Cena (grosze): {price_cents_n}")
        if price_cents_n is not None:
             print(f"Cena (zł): {price_cents_n / 100:.2f} zł")
        print(f"Dostępność: {data_niedostepny.get('availability_str')}")
    else:
        print("Nie udało się pobrać danych dla produktu niedostępnego.")

    # Można dodać więcej testowych URLi, w tym takie, które mogą nie działać, aby sprawdzić obsługę błędów.
    # np. test_url_error = "https://www.x-kom.pl/nieistniejacyprodukt123"
    # data_error = scrape_xkom_product(test_url_error)
    # print(f"Wynik dla błędnego URL: {data_error}")

```
