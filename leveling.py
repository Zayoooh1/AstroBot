# Stałe dla systemu XP
XP_PER_MESSAGE_MIN = 15
XP_PER_MESSAGE_MAX = 25
XP_COOLDOWN_SECONDS = 60

# Formuła na XP wymagane do osiągnięcia danego poziomu (kumulatywnie od poziomu 0)
# Poziom 0 -> 0 XP (start)
# Poziom 1 -> XP_FOR_LEVEL_BASE
# Poziom L -> XP_FOR_LEVEL_BASE + (L-1)*XP_FOR_LEVEL_BASE*XP_MULTIPLIER (prosta liniowa)
# Lub bardziej popularna: 5 * (level^2) + 50 * level + 100 (kumulatywne XP dla danego poziomu)
# Wybierzmy drugą, bardziej progresywną formułę.
# xp_for_level(0) powinno dać 0, jeśli poziom 0 to start.
# xp_for_level(1) to XP potrzebne do wbicia z 0 na 1.
# xp_for_level(level) to suma XP potrzebna od początku do osiągnięcia 'level'.

def xp_for_level_up(target_level: int) -> int:
    """Zwraca ilość XP potrzebną, aby osiągnąć `target_level` z poziomu `target_level - 1`."""
    if target_level <= 0:
        return 0 # Nie ma XP do zdobycia dla poziomu 0 lub niższych
    # To jest XP potrzebne TYLKO na ten konkretny poziom
    return (5 * ((target_level -1) ** 2) + 50 * (target_level -1) + 100)

def total_xp_for_level(level: int) -> int:
    """Zwraca CAŁKOWITĄ ilość XP potrzebną od samego początku, aby osiągnąć dany `level`."""
    if level <= 0:
        return 0

    required_xp = 0
    for l in range(1, level + 1):
        # XP potrzebne do przejścia z l-1 na l
        required_xp += (5 * ((l - 1) ** 2) + 50 * (l - 1) + 100)
    return required_xp


def get_level_from_xp(xp: int) -> int:
    """Oblicza, na jakim poziomie jest użytkownik na podstawie jego całkowitego XP."""
    if xp < 0: # Teoretycznie XP nie powinno być ujemne
        return 0

    level = 0
    while True:
        xp_needed_for_next_level = total_xp_for_level(level + 1)
        if xp_needed_for_next_level == 0 and level == 0 and xp < (5 * (0**2) + 50*0 + 100) : # Specjalny przypadek dla poziomu 0 i pierwszego progu
             xp_needed_for_next_level = (5 * (0**2) + 50*0 + 100) # XP na poziom 1

        if xp >= xp_needed_for_next_level:
            if xp_needed_for_next_level == 0 and level > 0: # Osiągnięto maksymalny poziom lub błąd w formule
                break
            level += 1
        else:
            break
    return level

def xp_to_next_level(current_xp: int, current_level: int) -> tuple[int, int]:
    """
    Oblicza, ile XP brakuje do następnego poziomu oraz ile XP jest wymagane na następny poziom.
    Zwraca krotkę: (xp_needed_to_reach_next_level, total_xp_for_next_level_gate).
    Jeśli użytkownik jest na maksymalnym poziomie (wg rozsądnego limitu), może zwrócić (0, current_xp) lub specjalne wartości.
    """
    if current_level < 0: current_level = 0 # Na wszelki wypadek

    xp_for_next_lvl_gate = total_xp_for_level(current_level + 1)

    if current_xp >= xp_for_next_lvl_gate and xp_for_next_lvl_gate != 0 : # Powinien już być na wyższym poziomie, może być błąd synchronizacji
        # W praktyce get_level_from_xp powinno to wykryć wcześniej.
        # Ale jeśli tak się stanie, oznacza to, że do następnego (jeszcze wyższego) poziomu potrzeba standardowej ilości.
        # To jest bardziej zabezpieczenie.
        # Rekalculacja poziomu byłaby tu dobra.
        # Na razie załóżmy, że current_level jest poprawny.
        pass

    xp_needed = xp_for_next_lvl_gate - current_xp
    return max(0, xp_needed), xp_for_next_lvl_gate


if __name__ == '__main__':
    # Testy
    print(f"XP na poziom 1 (z 0): {total_xp_for_level(1)}") # Oczekiwane 100
    print(f"XP na poziom 2 (z 0): {total_xp_for_level(2)}") # Oczekiwane 100 (na 1) + (5*1^2 + 50*1 + 100) = 100 + 155 = 255
    print(f"XP na poziom 3 (z 0): {total_xp_for_level(3)}") # Oczekiwane 255 (na 2) + (5*2^2 + 50*2 + 100) = 255 + (20+100+100) = 255 + 220 = 475

    print("\nTesty get_level_from_xp:")
    test_xps = [0, 50, 99, 100, 150, 254, 255, 474, 475, 1000]
    for xp_val in test_xps:
        lvl = get_level_from_xp(xp_val)
        xp_next, gate_next = xp_to_next_level(xp_val, lvl)
        print(f"XP: {xp_val} -> Poziom: {lvl}. Do nast. ({lvl+1}): {xp_next} (Próg: {gate_next})")

    print(f"\nTest xp_for_level_up (ile na konkretny level-up):")
    print(f"XP aby wbić poziom 1: {xp_for_level_up(1)}") # 100
    print(f"XP aby wbić poziom 2: {xp_for_level_up(2)}") # 155
    print(f"XP aby wbić poziom 3: {xp_for_level_up(3)}") # 220

    # Sprawdzenie sumy xp_for_level_up
    print(f"Suma XP na poziom 3 (manualnie): {xp_for_level_up(1) + xp_for_level_up(2) + xp_for_level_up(3)}") # 100+155+220 = 475. Zgadza się.

    print(f"Poziom dla 255 XP: {get_level_from_xp(255)}") # Powinno być 2
    xp_needed, next_gate = xp_to_next_level(255, 2)
    print(f"Dla 255 XP (poziom 2), do następnego ({2+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") # 220, 475

    xp_needed, next_gate = xp_to_next_level(100, 1)
    print(f"Dla 100 XP (poziom 1), do następnego ({1+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") # 155, 255

    xp_needed, next_gate = xp_to_next_level(0, 0)
    print(f"Dla 0 XP (poziom 0), do następnego ({0+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") # 100, 100

    xp_needed, next_gate = xp_to_next_level(99, 0)
    print(f"Dla 99 XP (poziom 0), do następnego ({0+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") # 1, 100

    # Test dla get_level_from_xp z xp_for_level_up(1) - 1
    almost_level_1_xp = xp_for_level_up(1) -1
    print(f"Poziom dla {almost_level_1_xp} XP: {get_level_from_xp(almost_level_1_xp)}") # Powinno być 0

    # Test dla get_level_from_xp z xp_for_level_up(1)
    level_1_xp = xp_for_level_up(1)
    print(f"Poziom dla {level_1_xp} XP: {get_level_from_xp(level_1_xp)}") # Powinno być 1

    # Test dla sumy XP na poziom 2 - 1
    almost_level_2_xp = total_xp_for_level(2) - 1
    print(f"Poziom dla {almost_level_2_xp} XP ({total_xp_for_level(2)}-1): {get_level_from_xp(almost_level_2_xp)}") # Powinno być 1

    # Test dla sumy XP na poziom 2
    level_2_xp = total_xp_for_level(2)
    print(f"Poziom dla {level_2_xp} XP ({total_xp_for_level(2)}): {get_level_from_xp(level_2_xp)}") # Powinno być 2

    # Test dla sumy XP na poziom 3
    level_3_xp = total_xp_for_level(3)
    print(f"Poziom dla {level_3_xp} XP ({total_xp_for_level(3)}): {get_level_from_xp(level_3_xp)}") # Powinno być 3

    print(f"Test get_level_from_xp dla 474xp: {get_level_from_xp(474)}") # Powinno być 2
    print(f"Test get_level_from_xp dla 475xp: {get_level_from_xp(475)}") # Powinno być 3
    print(f"Test get_level_from_xp dla 476xp: {get_level_from_xp(476)}") # Powinno być 3

    #Test get_level_from_xp dla 0
    print(f"Test get_level_from_xp dla 0xp: {get_level_from_xp(0)}") # Powinno być 0

    #Test xp_to_next_level dla 0xp, poziom 0
    xp_needed, next_gate = xp_to_next_level(0, 0)
    print(f"Dla 0 XP (poziom 0), do następnego ({0+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #100, 100

    #Test xp_to_next_level dla 99xp, poziom 0
    xp_needed, next_gate = xp_to_next_level(99, 0)
    print(f"Dla 99 XP (poziom 0), do następnego ({0+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 100

    #Test xp_to_next_level dla 100xp, poziom 1
    xp_needed, next_gate = xp_to_next_level(100, 1)
    print(f"Dla 100 XP (poziom 1), do następnego ({1+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #155, 255

    #Test xp_to_next_level dla 254xp, poziom 1
    xp_needed, next_gate = xp_to_next_level(254, 1)
    print(f"Dla 254 XP (poziom 1), do następnego ({1+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 255

    #Test xp_to_next_level dla 255xp, poziom 2
    xp_needed, next_gate = xp_to_next_level(255, 2)
    print(f"Dla 255 XP (poziom 2), do następnego ({2+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #220, 475

    #Test xp_to_next_level dla 474xp, poziom 2
    xp_needed, next_gate = xp_to_next_level(474, 2)
    print(f"Dla 474 XP (poziom 2), do następnego ({2+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 475

    #Test xp_to_next_level dla 475xp, poziom 3
    xp_needed, next_gate = xp_to_next_level(475, 3)
    print(f"Dla 475 XP (poziom 3), do następnego ({3+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #295, 770

    #Test xp_to_next_level dla 769xp, poziom 3
    xp_needed, next_gate = xp_to_next_level(769, 3)
    print(f"Dla 769 XP (poziom 3), do następnego ({3+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 770

    #Test xp_to_next_level dla 770xp, poziom 4
    xp_needed, next_gate = xp_to_next_level(770, 4)
    print(f"Dla 770 XP (poziom 4), do następnego ({4+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #380, 1150

    #Test xp_to_next_level dla 1149xp, poziom 4
    xp_needed, next_gate = xp_to_next_level(1149, 4)
    print(f"Dla 1149 XP (poziom 4), do następnego ({4+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 1150

    #Test xp_to_next_level dla 1150xp, poziom 5
    xp_needed, next_gate = xp_to_next_level(1150, 5)
    print(f"Dla 1150 XP (poziom 5), do następnego ({5+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #475, 1625

    #Test xp_to_next_level dla 1624xp, poziom 5
    xp_needed, next_gate = xp_to_next_level(1624, 5)
    print(f"Dla 1624 XP (poziom 5), do następnego ({5+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 1625

    #Test xp_to_next_level dla 1625xp, poziom 6
    xp_needed, next_gate = xp_to_next_level(1625, 6)
    print(f"Dla 1625 XP (poziom 6), do następnego ({6+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #580, 2205

    #Test xp_to_next_level dla 2204xp, poziom 6
    xp_needed, next_gate = xp_to_next_level(2204, 6)
    print(f"Dla 2204 XP (poziom 6), do następnego ({6+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 2205

    #Test xp_to_next_level dla 2205xp, poziom 7
    xp_needed, next_gate = xp_to_next_level(2205, 7)
    print(f"Dla 2205 XP (poziom 7), do następnego ({7+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #695, 2900

    #Test xp_to_next_level dla 2899xp, poziom 7
    xp_needed, next_gate = xp_to_next_level(2899, 7)
    print(f"Dla 2899 XP (poziom 7), do następnego ({7+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 2900

    #Test xp_to_next_level dla 2900xp, poziom 8
    xp_needed, next_gate = xp_to_next_level(2900, 8)
    print(f"Dla 2900 XP (poziom 8), do następnego ({8+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #820, 3720

    #Test xp_to_next_level dla 3719xp, poziom 8
    xp_needed, next_gate = xp_to_next_level(3719, 8)
    print(f"Dla 3719 XP (poziom 8), do następnego ({8+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 3720

    #Test xp_to_next_level dla 3720xp, poziom 9
    xp_needed, next_gate = xp_to_next_level(3720, 9)
    print(f"Dla 3720 XP (poziom 9), do następnego ({9+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #955, 4675

    #Test xp_to_next_level dla 4674xp, poziom 9
    xp_needed, next_gate = xp_to_next_level(4674, 9)
    print(f"Dla 4674 XP (poziom 9), do następnego ({9+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 4675

    #Test xp_to_next_level dla 4675xp, poziom 10
    xp_needed, next_gate = xp_to_next_level(4675, 10)
    print(f"Dla 4675 XP (poziom 10), do następnego ({10+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1100, 5775

    #Test xp_to_next_level dla 5774xp, poziom 10
    xp_needed, next_gate = xp_to_next_level(5774, 10)
    print(f"Dla 5774 XP (poziom 10), do następnego ({10+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 5775

    #Test xp_to_next_level dla 5775xp, poziom 11
    xp_needed, next_gate = xp_to_next_level(5775, 11)
    print(f"Dla 5775 XP (poziom 11), do następnego ({11+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1255, 7030

    #Test xp_to_next_level dla 7029xp, poziom 11
    xp_needed, next_gate = xp_to_next_level(7029, 11)
    print(f"Dla 7029 XP (poziom 11), do następnego ({11+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 7030

    #Test xp_to_next_level dla 7030xp, poziom 12
    xp_needed, next_gate = xp_to_next_level(7030, 12)
    print(f"Dla 7030 XP (poziom 12), do następnego ({12+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1420, 8450

    #Test xp_to_next_level dla 8449xp, poziom 12
    xp_needed, next_gate = xp_to_next_level(8449, 12)
    print(f"Dla 8449 XP (poziom 12), do następnego ({12+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 8450

    #Test xp_to_next_level dla 8450xp, poziom 13
    xp_needed, next_gate = xp_to_next_level(8450, 13)
    print(f"Dla 8450 XP (poziom 13), do następnego ({13+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1595, 10045

    #Test xp_to_next_level dla 10044xp, poziom 13
    xp_needed, next_gate = xp_to_next_level(10044, 13)
    print(f"Dla 10044 XP (poziom 13), do następnego ({13+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 10045

    #Test xp_to_next_level dla 10045xp, poziom 14
    xp_needed, next_gate = xp_to_next_level(10045, 14)
    print(f"Dla 10045 XP (poziom 14), do następnego ({14+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1780, 11825

    #Test xp_to_next_level dla 11824xp, poziom 14
    xp_needed, next_gate = xp_to_next_level(11824, 14)
    print(f"Dla 11824 XP (poziom 14), do następnego ({14+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 11825

    #Test xp_to_next_level dla 11825xp, poziom 15
    xp_needed, next_gate = xp_to_next_level(11825, 15)
    print(f"Dla 11825 XP (poziom 15), do następnego ({15+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1975, 13800

    #Test xp_to_next_level dla 13799xp, poziom 15
    xp_needed, next_gate = xp_to_next_level(13799, 15)
    print(f"Dla 13799 XP (poziom 15), do następnego ({15+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 13800

    #Test xp_to_next_level dla 13800xp, poziom 16
    xp_needed, next_gate = xp_to_next_level(13800, 16)
    print(f"Dla 13800 XP (poziom 16), do następnego ({16+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #2180, 15980

    #Test xp_to_next_level dla 15979xp, poziom 16
    xp_needed, next_gate = xp_to_next_level(15979, 16)
    print(f"Dla 15979 XP (poziom 16), do następnego ({16+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 15980

    #Test xp_to_next_level dla 15980xp, poziom 17
    xp_needed, next_gate = xp_to_next_level(15980, 17)
    print(f"Dla 15980 XP (poziom 17), do następnego ({17+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #2395, 18375

    #Test xp_to_next_level dla 18374xp, poziom 17
    xp_needed, next_gate = xp_to_next_level(18374, 17)
    print(f"Dla 18374 XP (poziom 17), do następnego ({17+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 18375

    #Test xp_to_next_level dla 18375xp, poziom 18
    xp_needed, next_gate = xp_to_next_level(18375, 18)
    print(f"Dla 18375 XP (poziom 18), do następnego ({18+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #2620, 21000-5

    #Test xp_to_next_level dla 20994xp, poziom 18
    xp_needed, next_gate = xp_to_next_level(20994, 18)
    print(f"Dla 20994 XP (poziom 18), do następnego ({18+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 20995

    #Test xp_to_next_level dla 20995xp, poziom 19
    xp_needed, next_gate = xp_to_next_level(20995, 19)
    print(f"Dla 20995 XP (poziom 19), do następnego ({19+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #2855, 23850

    #Test xp_to_next_level dla 23849xp, poziom 19
    xp_needed, next_gate = xp_to_next_level(23849, 19)
    print(f"Dla 23849 XP (poziom 19), do następnego ({19+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #1, 23850

    #Test xp_to_next_level dla 23850xp, poziom 20
    xp_needed, next_gate = xp_to_next_level(23850, 20)
    print(f"Dla 23850 XP (poziom 20), do następnego ({20+1}) potrzeba {xp_needed}. Próg następnego: {next_gate}") #3100, 26950
