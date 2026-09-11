"""Shared CLI help for the menu, order input and command-line help."""
HELP_COMMANDS = ('--help', '--h', '-h')
USAGE = '''Použití WHS Asistenta

1 – Zpracovat WHS objednávky; 2 – Kontrola bez změn.
Volba 2 pouze vypíše aktuální stav. Neprovádí realizaci, HW ani uzavření;
parametr --r v tomto režimu nemění rozsah kontroly.
Vkládejte WHS order, nejlépe jeden na řádek. Prázdný řádek spustí dávku.
Před zpracováním ověřte rozsah jednotlivých WHS a potvrďte y/n.

Parametry za WHS order:
  --r, --realizace   Pouze realizace zásuvky, bez instalace HW a uzavření.
  Bez parametru     Celý postup podle aktuálního stavu objednávky.

Příklad smíšené dávky:
  WHS_SO_08000006785
  WHS_SO_08000006786 --r

HW se provádí až ve stavu Registrace CM provedena a s vyplněným údajem MAC.
Při čekání na CM zadejte stejné ID znovu po registraci; proces naváže HW.
Celý postup zahrnuje i potvrzení uzavření před termínem realizace.
Výsledek HW a uzavření zatím ověřujete ručně přes y/n.

Příkazy na samostatném řádku v menu nebo při vkládání WHS:
  --help, --h, -h    Tato nápověda. Rozepsaná dávka zůstává zachovaná.
  Ctrl+C            Během dávky přeruší automat; při zadávání ukončí zpracování.

Při zadávání WHS listují šipky nahoru/dolů historií tohoto běhu.
Vybraný příkaz můžete upravit a potvrdit Enterem. Historie zůstává mezi dávkami,
po ukončení zpracování se vymaže. Hesla a potvrzení y/n do ní nevstupují.

WHS order musí mít prefix WHS_SO_ a přesně 11 číslic.
Parametr --r patří za konkrétní WHS, nikoli za příkaz pro spuštění programu.
'''


def show_help(command):
    if command.strip() in HELP_COMMANDS:
        print(USAGE)
        return True
    return False
