# Косметика: каталог, владение, выставление облика (08.10.2026, с ноутбука)

Пометки: [ФАКТ] из interop-сигнатур или кода мода на GitHub; [ВЫВОД] по именам/опыту; [ПРОВЕРИТЬ] на ПК.
В interop нет тел методов, поэтому логика проверок - только вывод.

## 1. Каталог
- [ФАКТ] `HatManager` (синглтон `HatManager.Instance`): массивы `allHats/allSkins/allVisors/allPets/allNamePlates`, плюс `allBundles`, `allStarBundles`, `allFeaturedItems`. Методы: `GetHatById/GetSkinById/GetVisorById/GetPetById/GetNamePlateById(string id)`, `GetUnlockedHats/Skins/Visors/Pets/NamePlates()`, `CheckValidCosmetic(string id)`, `CheckLongModeValidCosmetic(id, ignoreLongMode)`.
- [ФАКТ] Базовый класс `CosmeticData` (ScriptableObject): `ProdId` (строковый id, то что идёт в RPC и в сохранение), `ProductId`, `BundleId`, `EpicId`, `Free`, `NotInStore`, `beanCost`, `starCost`, `paidOnMobile`, `limitedTime`, `freeRedeemableCosmetic`, `unlockOnSelectPlatforms`, `ChipOffset`, `displayOrder`, `SetProdId()`.
- [ФАКТ] Пустые значения: статические `EmptyId` у HatData/SkinData/VisorData/PetData/NamePlateData; у PlayerCustomizationData есть `DEFAULT_HAT/SKIN/VISOR/PET/NAME_PLATE`.
- [ВЫВОД] "Бесплатно/у всех": `Free == true` (в т.ч. пустой id и базовые). `NotInStore` - нет в магазине (награды, события), но это не "бесплатно". `BundleId` - предмет входит в набор; покупка набора может открывать его через bundleKey.
- Специфика: HatData: `InFront, NoBounce, BlocksVisors, RelatedSkin`; VisorData: `BehindHats`.

## 2. Владение
- [ФАКТ] `DataManager.Player.Purchases` (`PlayerPurchasesData`): поле `List<string> purchases`, методы `GetPurchase(itemKey, bundleKey)`, `SetPurchased(key)`, `ClearPurchase`, `ClearAllPurchases`, `UpdateLegacyPurchases`. Есть также `Player.Store` (PlayerStoreData).
- [ВЫВОД] `GetUnlocked*()` фильтрует каталог по `Free || GetPurchase(ProdId, BundleId)`. Для Epic прогресс ведётся на серверах Innersloth (README AUnlocker: "progress is stored on the Innersloth servers"), локальный файл - кэш/сохранение игрока (`PlayerData.FileName`, зашифрованные группы).
- [ФАКТ, мод AUnlocker/MalumMenu] Разблокировка у них чисто локальная: Harmony-префикс на `PlayerPurchasesData.GetPurchase` возвращает true, постфикс на `HatManager.Initialize` ставит `Free = true` всем предметам. Серверный аккаунт не меняется, без мода снова закрыто.
- [ВЫВОД] Проверки владения хостом нет: `CheckName/CheckColor` на хосте есть (имя, цвет), а для шапок/скинов/питомцев/рамок есть только `RpcSet*` без `CmdCheck*` (в interop нет `CmdCheckHat` и т.п.). Единственное похожее - `HatManager.CheckValidCosmetic(id)`, но кто его вызывает - неизвестно ([ПРОВЕРИТЬ] через поиск ссылок/логи).

## 3. Как выставить облик
- [ФАКТ] `DataManager.Player.Customization` (`PlayerCustomizationData`): строковые свойства `Hat, Skin, Visor, Pet, NamePlate`, `Name`, `Color` (byte), события `On*Changed`. Это то, что игра берёт в лобби при создании игрока.
- [ФАКТ] `PlayerControl`: `RpcSetHat(string hatId)`, `RpcSetSkin(string)`, `RpcSetVisor(string)`, `RpcSetPet(string)`, `RpcSetNamePlate(string)` (id = `ProdId`); локальные `SetHat(hatId, colorId)`, `SetSkin(skinId, color)`, `SetVisor(visorId, colorId)`, `SetPet(petId[, colorId])`, `SetNamePlate(id)`; `RawSet*` - низкоуровневые.
- [ФАКТ] AUnlocker вызывает `__instance.SetHat("",0)` и т.п. напрямую - так в ней скрывают косметику локально.
- План: id взять из `HatManager.Instance.allHats[i].ProdId`; записать в `DataManager.Player.Customization.Hat = id` (+ `DataManager.Player.Save()`) ДО входа в лобби, либо в лобби вызвать `PlayerControl.LocalPlayer.RpcSetHat(id)` (и остальные).

## 4. Что будет с чужой косметикой
- [ВЫВОД] Хост и клиенты только принимают id по RPC и подгружают спрайт по `GetHatById`; владения не сверяют, так что применится у всех (в локальной игре точно, сервер аккаунтов не участвует). Исключение: неизвестный id (нет в каталоге) - `GetHatById` вернёт null/пустую шляпу. Рискованное место - `CheckValidCosmetic`: если игра сбрасывает невалидное при загрузке `Customization` или в меню "Гардероб", id может откатиться на дефолт. Окончательно - только проверка вживую.
- Для нашего проекта (локальный режим) обход владения, скорее всего, вообще не нужен, достаточно `Free`/купленных.

## 5. Одна короткая проверка на ПК (когда освободится; не выполнять сейчас)
1. Найти файл: `dir "%USERPROFILE%\AppData\LocalLow\Innersloth\Among Us"` (файлы `playerData*`, `settings*`; формат бинарный/зашифрованный, читать их не надо).
2. Мод-проба (через `mod/AUBridge`, команда "cosmetics"): в игре вызвать `HatManager.Instance`, записать в лог: число `allHats`, для каждого `ProdId, Free, NotInStore, BundleId`, и признак `GetUnlockedHats()` (список ProdId). Заодно `DataManager.Player.Purchases.purchases` (список строк) и `Customization.Hat/Skin/Visor/Pet/NamePlate`.
3. В лобби с двумя копиями: на копии A `RpcSetHat(<id, которого нет в GetUnlockedHats>)`, на копии B прочитать `Data.DefaultOutfit.HatId` игрока A (или посмотреть экран) - подтвердит пункт 4.
4. Проверить, вызывает ли кто-то `CheckValidCosmetic` (лог Harmony-префикса на нём 1 раз).
Источники: github.com/astra1dev/AUnlocker (src/Patches/CosmeticsPatches.cs), ссылка в нём на MalumMenu CosmeticsUnlocker.cs.

## 6. Реализовано в мосте (08.10.2026, не проверено вживую)
- Код: `AUBridge/Cosmetics.cs`, команды `cosmetics` и `setoutfit` в `Bridge.cs`, применение в `Runner.ApplyIdentity` (локально через `Customization`, в лобби через `RpcSet*`, до 5 попыток на поле), аргумент `--aub-outfit` в `AubConfig` (Plugin.cs).
- Владение: `owned = Free || DataManager.Player.Purchases.GetPurchase(ProdId, BundleId)`. Патчей, открывающих платное, нет и не будет: чужое = ошибка `not owned`.
- Имя предмета: `CosmeticData.GetItemName()` (может вернуть ключ перевода или пустое; тогда поля `name` нет).
- [ПРОВЕРИТЬ на ПК] (1) сколько предметов реально `free`/`owned` на Epic-аккаунте; (2) размер ответа `cosmetics` целиком (< 256 КБ?); (3) совпадает ли `DefaultOutfit.HatId` с ProdId после `RpcSetHat` (иначе ретраи впустую - максимум 5); (4) не откатывает ли игра чужие `Customization` в лобби; (5) `GetItemName()` без локализатора.
