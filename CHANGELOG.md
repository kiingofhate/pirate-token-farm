# История изменений (Changelog)

Все заметные улучшения, новые возможности и исправления ошибок в **Pirate Token Farm**.

---

## Последнее обновление

### Что добавлено
- **Поддержка английской версии Fortnite (EN + RU):**
  - Добавлены шаблоны интерфейса для английского клиента Fortnite (`PLAY`, `PLAY AGAIN`, `RETURN TO LOBBY`, `CONNECTING...`, `ESC DONE`, `Solo`, `Squad` и `Fill`) с автоматическим переключением между русской и английской версиями без изменения настроек.
  - Для английского лобби проверяются оба маркера (`Squad` и `Fill`, с защитой от ложного срабатывания на `No Fill`).
- **Строгая многоступенчатая проверка состояний в окне выбора режима:**
  - Языконезависимое определение выбранного режима «Отряд» по жёлтому индикатору под 4-й иконкой в «Размер команды».
  - Последовательная проверка всех состояний перед любым действием и закрытием окна: выбор 4-й иконки «Отряд» → снятие блокировки «Заполнение команды» (`ЗАПОЛНИТЬ` / `FILL`) → обязательная перепроверка на 2 кадрах подряд → закрытие (`Esc` / `ESC ГОТОВО` / `ESC DONE`) → повторная проверка плашки режима в лобби перед нажатием «Играть».
- **Автопроверка и восстановление режима «Отряд, Заполнить»:**
  - Перед стартом матча в лобби (в методе 2 и при каждом выходе в лобби) программа проверяет плашку режима над кнопкой «Играть».
  - В методе 1 («Играть снова») каждые 10-15 минут после завершения матча бот вместо «Играть снова» выходит в лобби, проверяет режим и возвращает «Отряд, Заполнить», если игра сбросила выбор на «Одиночки».
  - При выборе режима скрипт дожидается разблокировки строки «Заполнение команды» после клика по «Отряд», проверяет состояние «ЗАПОЛНИТЬ» / «FILL» по цвету переключателя (HSV) и тексту подписи, меняет его только если стоит «НЕ ЗАПОЛНЯТЬ» / «NO FILL», и закрывает окно клавишей Esc или кнопкой «Готово» / «DONE» с проверкой закрытия.
- **Поддержка всех разрешений и форматов мониторов (720p, 1080p, 1440p, 4K, 4:3, 16:10, 21:9):**
  - Плотная 28-шаговая сетка масштабирования (`0.50x .. 2.15x`) и автоматическая нормализация нестандартных пропорций.
  - Поиск по внутреннему ядру кнопок (`CORE_BOXES`) и двухполярное распознавание «Играть снова» и «Вернуться в лобби» как в жёлтом, так и в тёмном выделении, с полной изоляцией от 3D-фона.
- **Защита фокуса, курсора и лобби:**
  - Автоматическая остановка автофарма и мгновенное отпускание всех клавиш при сворачивании или потере фокуса окна Fortnite.
  - Перевод курсора в центр экрана и строго горизонтальное движение камеры (`dy = 0`) в Анти-АФК, чтобы мышь не задевала карту сверху или панель уведомлений снизу.
  - Задержка на удары киркой после клика «Играть» и в главном меню, чтобы исключить случайное нажатие «Отмена».

### Что исправлено
- Исправлен сбой якорной привязки кнопки «ESC ГОТОВО» (`0.96x` вместо `1.00x`), из-за которого области проверки текста смещались вниз на 24px, цикл преждевременно выходил при заблокированном «Заполнении команды» и выключал уже активное «ЗАПОЛНИТЬ» в «НЕ ЗАПОЛНЯТЬ».
- Исправлена ошибка, из-за которой в окне выбора режима переключатель «Заполнить» нажимался до окончания серверного обновления «Одиночки -> Отряд» (когда строка была «ЗАБЛОКИРОВАНО»), что приводило к переключению на «НЕ ЗАПОЛНЯТЬ».
- Исправлено закрытие модального окна настройки режима: добавлено плавное пробуждение Slate-наведения курсора, нажатие клавиши Esc и резервный клик по «ESC ГОТОВО» / «ESC DONE» с проверкой исчезновения окна.
- Исправлено распознавание вырезанной области режима на 4K-мониторах (`is_roi=True`, `expected_scale`).
- Исправлено застревание метода 1 на послематчевом экране, если присутствует только кнопка «Вернуться в лобби» без «Играть снова».
- Исправлен пропуск клика «Играть снова» на другом ПК за счёт пробуждения Slate-наведения (`MOUSEEVENTF_MOVE`), увеличенных задержек клика, подтверждающего повторного клика и `SetProcessDpiAwarenessContext` (Per-Monitor V2) для Windows DPI 125%-175%.

---

## English Summary

### Added
- **English Fortnite client support (EN + RU):** Added English UI templates (`PLAY`, `PLAY AGAIN`, `RETURN TO LOBBY`, `CONNECTING...`, `ESC DONE`, `Solo`, `Squad`, `Fill`) with automatic Russian/English detection and explicit `No Fill` rejection.
- **Strict multi-state modal verification:** Verifies the 4th Squads icon yellow indicator, unlocked Team Fill state, and Fill ON state across 2 consecutive frames before closing, then re-verifies the lobby mode pill before clicking Play.
- **Automatic Squads & Team Fill recovery:** Checks the lobby mode pill above Play before queueing in Method 2 and every 10-15 minutes via lobby return in Method 1; switches from Solo to Squads (4 players) and ensures Fill is ON without accidentally toggling it OFF while unlocking.
- **Multi-resolution & Ultrawide matching (`720p .. 4K`, `4:3`, `16:10`, `21:9`):** 28-step scale pyramid (`0.50x .. 2.15x`), inner-core button matching isolated from 3D backgrounds, dual-polarity matching for Play Again / Return to Lobby, and ROI scale hints for 4K.
- **Focus & cursor safety:** Auto-stops autofarm immediately when Fortnite is minimized or loses focus, keeps Anti-AFK camera movement strictly horizontal (`dy = 0`) around screen center, and prevents accidental double-clicks on Play/Cancel.

### Fixed
- Fixed `esc_gotovo` scale tie-break (`0.96x` preempting `1.00x`) and centered modal offsets so async Fill locks no longer trigger early exit or accidental Fill OFF toggles.
- Fixed modal Fill toggle accidentally flipping `ЗАПОЛНИТЬ` to `НЕ ЗАПОЛНЯТЬ` when Fortnite delayed unlocking Team Fill after clicking Squads.
- Fixed modal dismissal reliability by waiting for async party updates to settle, closing via `Esc` with `ESC ГОТОВО` / `ESC DONE` fallback click, and verifying modal exit.
- Fixed Slate UI hover registration and Windows Per-Monitor DPI V2 coordinate alignment across different PCs and monitor scales.
