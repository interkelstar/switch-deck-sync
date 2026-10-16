# Carry your SRM artwork on the card

Steam ROM Manager (SRM) chooses artwork and adds games to Steam. Switch Deck Sync
adds its own app shortcut. Existing game shortcuts remain in place.

## Export directly to the card

1. Open **Install.desktop** and choose **Transfer SRM artwork → Export or import with SRM**.
   Select the reader with your prepared card. The wizard shows both folder locations
   and creates the artwork parent folder if needed.
2. Open Steam ROM Manager through EmuDeck. Enable the parsers for the games you want,
   generate the app list, and choose your artwork.
3. Choose **Export image choices**. Select the card's **Emulation/artwork** folder.
4. SRM creates **srm-image-choices** there. Keep the entire folder on the card.

An existing export saved elsewhere can be copied using **Transfer SRM artwork → Copy
an existing SRM export to this card**. Select the SRM export folder, not Steam's grid
folder. The wizard verifies the copies and retains any earlier export beside it.

## Import on the other computer

1. Connect the card and complete the optional portable-library setup.
2. Open SRM and generate the app list using the relevant parsers.
3. Choose **Import image choices** and select **Emulation/artwork/srm-image-choices**.
4. Review the games and artwork, then use SRM's **Save apps to Steam**.

SRM matches imported images by image pool. Keep the same image queries/matching for
the games on both computers. Use SRM's preview to check the result before saving.

This uses SRM's own export without converting the files. Current SRM uses
**_selections.json**; some older exports use **selections.json**. The selections file
and every referenced image travel together. An image export does not include parser
settings or decide which games to add to Steam.

[EmuDeck guide](https://github.com/EmuDeck/emudeck.github.io/blob/main/docs/tools/steamos/steam-rom-manager.md)
· [SRM export/import implementation](https://github.com/SteamGridDB/steam-rom-manager/blob/master/src/renderer/services/preview.service.ts)

## Русский

В мастере выбери **Перенести обложки SRM → Экспортировать или импортировать через SRM**.
Он покажет пути на выбранной карте.

На исходном компьютере создай список игр в SRM, выбери обложки и нажми
**Export image choices**. В качестве назначения выбери **Emulation/artwork** на карте.
SRM создаст внутри папку **srm-image-choices**.

На другом компьютере создай список игр в SRM, нажми **Import image choices** и выбери
**Emulation/artwork/srm-image-choices**. Проверь результат в предпросмотре и сохрани
выбранные игры через **Save apps to Steam**.

Для готового экспорта с внутреннего накопителя используй действие мастера
**Скопировать готовый экспорт SRM на карту**. Исходная папка и предыдущий экспорт
сохраняются. Выбор игр, запросы поиска обложек и настройки SRM относятся к компьютеру.
