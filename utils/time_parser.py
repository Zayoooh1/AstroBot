import re

def parse_duration(duration_str: str) -> int | None:
    """
    Parsuje string czasu trwania (np. "10m", "2h", "3d", "1w") na sekundy.
    Zwraca liczbę sekund lub None jeśli format jest nieprawidłowy.
    Obsługiwane jednostki: s (sekundy), m (minuty), h (godziny), d (dni), w (tygodnie).
    """
    if not duration_str:
        return None

    match = re.fullmatch(r"(\d+)([smhdw])", duration_str.lower())
    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    if unit == 's':
        return value
    elif unit == 'm':
        return value * 60
    elif unit == 'h':
        return value * 60 * 60
    elif unit == 'd':
        return value * 60 * 60 * 24
    elif unit == 'w':
        return value * 60 * 60 * 24 * 7

    return None # Nie powinno się zdarzyć jeśli regex pasuje

if __name__ == '__main__':
    print(f"10s -> {parse_duration('10s')}")
    print(f"5m -> {parse_duration('5m')}")
    print(f"2h -> {parse_duration('2h')}")
    print(f"3d -> {parse_duration('3d')}")
    print(f"1w -> {parse_duration('1w')}")
    print(f"1 -> {parse_duration('1')}")
    print(f"m -> {parse_duration('m')}")
    print(f"10min -> {parse_duration('10min')}")
    print(f" -> {parse_duration('')}")
    print(f"60s -> {parse_duration('60s')}")
