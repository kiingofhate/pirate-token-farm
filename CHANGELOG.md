# История изменений (Changelog)

Все заметные улучшения, новые возможности и исправления ошибок в **Pirate Token Farm**.

---

## Последнее обновление

### Что добавлено
- **Автопроверка и восстановление режима «Отряд, Заполнить»:**
  - Перед стартом матча в лобби (в методе 2 и при каждом выходе в лобби) программа проверяет плашку режима над кнопкой «Играть».
  - В методе 1 («Играть снова») каждые 10-15 минут после завершения матча бот вместо «Играть снова» выходит в лобби, проверяет режим и возвращает «Отряд, Заполнить», если игра сбросила выбор на «Одиночки».
  - При выборе режима скрипт дожидается разблокировки строки «Заполнение команды» после клика по «Отряд», проверяет состояние «ЗАПОЛНИТЬ» по цвету переключателя (HSV) и тексту подписи, меняет его только если стоит «НЕ ЗАПОЛНЯТЬ», и закрывает окно клавишей Esc или кнопкой «Готово» с проверкой закрытия.
- **Поддержка всех разрешений и форматов мониторов (720p, 1080p, 1440p, 4K, 4:3, 16:10, 21:9):**
  - Плотная 28-шаговая сетка масштабирования (`0.50x .. 2.15x`) и автоматическая нормализация нестандартных пропорций.
  - Поиск по внутреннему ядру кнопок (`CORE_BOXES`) и двухполярное распознавание «Играть снова» и «Вернуться в лобби» как в жёлтом, так и в тёмном выделении, с полной изоляцией от 3D-фона.
- **Защита фокуса, курсора и лобби:**
  - Автоматическая остановка автофарма и мгновенное отпускание всех клавиш при сворачивании или потере фокуса окна Fortnite.
  - Перевод курсора в центр экрана и строго горизонтальное движение камеры (`dy = 0`) в Анти-АФК, чтобы мышь не задевала карту сверху или панель уведомлений снизу.
  - Задержка на удары киркой после клика «Играть» и в главном меню, чтобы исключить случайное нажатие «Отмена».

### Что исправлено
- Исправлена ошибка, из-за которой в окне выбора режима переключатель «Заполнить» нажимался до окончания серверного обновления «Одиночки -> Отряд» (когда строка была «ЗАБЛОКИРОВАНО»), что приводило к переключению на «НЕ ЗАПОЛНЯТЬ».
- Исправлено закрытие модального окна настройки режима: добавлено плавное пробуждение Slate-наведения курсора, нажатие клавиши Esc и резервный клик по «ESC ГОТОВО» с проверкой исчезновения окна.
- Исправлено распознавание вырезанной области режима на 4K-мониторах (`is_roi=True`, `expected_scale`).
- Исправлено застревание метода 1 на послематчевом экране, если присутствует только кнопка «Вернуться в лобби» без «Играть снова».
- Исправлен пропуск клика «Играть снова» на другом ПК за счёт пробуждения Slate-наведения (`MOUSEEVENTF_MOVE`), увеличенных задержек клика, подтверждающего повторного клика и `SetProcessDpiAwarenessContext` (Per-Monitor V2) для Windows DPI 125%-175%.

---

## English Summary

### Added
- **Automatic Squads & Team Fill recovery:** Checks the lobby mode pill above Play before queueing in Method 2 and every 10-15 minutes via lobby return in Method 1; switches from Solo to Squads (4 players) and ensures Fill is ON without accidentally toggling it OFF while unlocking.
- **Multi-resolution & Ultrawide matching (`720p .. 4K`, `4:3`, `16:10`, `21:9`):** 28-step scale pyramid (`0.50x .. 2.15x`), inner-core button matching isolated from 3D backgrounds, dual-polarity matching for Play Again / Return to Lobby, and ROI scale hints for 4K.
- **Focus & cursor safety:** Auto-stops autofarm immediately when Fortnite is minimized or loses focus, keeps Anti-AFK camera movement strictly horizontal (`dy = 0`) around screen center, and prevents accidental double-clicks on Play/Cancel.

### Fixed
- Fixed modal Fill toggle accidentally flipping `ЗАПОЛНИТЬ` to `НЕ ЗАПОЛНЯТЬ` when Fortnite delayed unlocking Team Fill after clicking Squads.
- Fixed modal dismissal reliability by waiting for async party updates to settle, closing via `Esc` with `ESC ГОТОВО` fallback click, and verifying modal exit.
- Fixed Slate UI hover registration and Windows Per-Monitor DPI V2 coordinate alignment across different PCs and monitor scales.
