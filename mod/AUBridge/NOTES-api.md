# AUBridge: заметки по API игры (17.4e)

Источник: `ilspycmd` по `refs/interop/Assembly-CSharp.dll`. Это interop-заглушки: тел методов нет, видны только имена и сигнатуры. Всё, что ниже про "кто кого вызывает", — вывод по именам, на ПК не проверено.

## Окно привязки гостя
- Класс `AskToMergeGuest : MonoBehaviour` (кнопки `GoAheadButton`, `NotRightNowButton`, методы `OnClose`, `Start`, `OnTextUpdated`).
- Владелец: `EOSManager` (поле `askToMergeAccount`). Цепочка входа: `CheckGuestAccountMigrationStuff` -> `BeginMergeGuestAccountFlow` (показ окна) -> `MergeGuestAccountIntoPlatform` (настоящее слияние, шлёт `RequestMergeGuestAccount`) или `EndMergeGuestAccountFlow` -> `BeginFinalPartsOfLoginFlow`.
- Решение: Harmony prefix на `EOSManager.BeginMergeGuestAccountFlow` возвращает false (окно не открывается) и вызывает `EndMergeGuestAccountFlow()`. Выбран именно End, а не `MergeGuestAccountIntoPlatform`: по имени это закрытие потока, продолжающее вход, и оно не должно слать запрос слияния. Кнопки окна не нажимаем.
- Страховка: postfix на `AskToMergeGuest.Start` пишет предупреждение и делает `gameObject.SetActive(false)`.
- Не проверено: что именно делает `EndMergeGuestAccountFlow`. Если вход зависнет после подавления окна, смотреть лог `[AUB]` и состояние входа.

## Объявления
`MainMenuManager.announcementPopUp : AnnouncementPopUp`, у него `Close()`. Раз в секунду, если окно активно, зовём `Close()`. Harmony на корутину `ShowIfNew` не ставим: `RunStartUp` может ждать её завершения.

## Локальный хост
- `MainMenuManager.playLocalButton` (PassiveButton). Его `OnClick.Invoke()` открывает экран «Локально».
- `HostLocalGameButton.OnClick()` — кнопка «Классическая» (`ClickHideNSeek` — прятки, не трогаем). Поле `NetworkMode` (enum `NetworkModes`: LocalGame, OnlineGame, FreePlay).
- Перед нажатием `GameOptionsManager.Instance.normalGameHostOptions` и `currentNormalGameOptions` (`NormalGameOptionsV10`): выставляем `_MapId_k__BackingField = 0` (Skeld) и `_MaxPlayers_k__BackingField = 15`.
- Меню готово, когда `MainMenuManager.finishStartup == true`.

## Локальный join
- `GameDiscovery` (на экране «Локально») слушает UDP-рассылку (`InnerDiscover`), на каждую игру создаёт `JoinGameButton` (`CreateButtonForAddess`, словарь `received`).
- `JoinGameButton.OnClick()` (внутри корутина `JoinLocalGame`), поле `netAddress`. Берём первую активную кнопку с непустым `netAddress` (в онлайн-меню тоже есть JoinGameButton, но без адреса).

## Имя и цвет
- До лобби: `AmongUs.Data.DataManager.Player.Customization.Name` (string) и `.Color` (byte). Готовность: `DataManager.IsPlayerLoaded`.
- В лобби: `PlayerControl.LocalPlayer.CmdCheckName(string)` и `CmdCheckColor(byte)`; текущие значения читаем из `LocalPlayer.Data.PlayerName` и `.DefaultOutfit.ColorId`. Максимум 5 попыток каждого (занятый цвет игра заменит сама).

## Состояние
- `AmongUsClient.Instance.GameState` (`InnerNetClient.GameStates`: NotJoined, Joined, Started, Ended), `AmHost`, `NetworkMode`.
- Игроки: `GameData.Instance.AllPlayers` (`NetworkedPlayerInfo`: `PlayerName`, `DefaultOutfit.ColorId`, `PlayerId`).
- Сцена: `SceneManager.GetActiveScene().name`.

## Мост
Свой `MonoBehaviour` (`Runner`) через `IL2CPPChainloader.AddUnityComponent`; очередь действий разбирается в `Update`, сеть в отдельных потоках.
