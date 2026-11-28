# Задачи

Статусы stage 1 сверены с прогонами на ПК.

## Stage 1

- [x] Зафиксировать Freqtrade `2026.10` и структуру репозитория.
- [x] Собрать spot dry-run конфиг на BTC/USDT и ETH/USDT, 15m, 1000 USDT. Биржа по умолчанию Bybit, запасная OKX.
- [x] Блокировать `dry_run=false`, фьючерсы, шорты, ключи биржи и API наружу.
- [x] Добавить базовую стратегию `BaselineTrendStrategy` как пробу движка.
- [x] Добавить оператор `labctl`: init, download, validate, backtest, verify, up, start, pause, stop, down.
- [x] Проверять дырки, дубликаты и битые OHLC без заполнения пропусков.
- [x] Сравнивать два архива бэктеста без полей времени запуска.
- [x] Прогнать unit-тесты в среде сборки. `python3 -m pytest`: 15 passed, Python 3.12.3. Это проверки конфига, ряда и сравнения архивов, без рыночных данных.
- [x] Скачать реальные свечи на ПК: `./scripts/lab.sh download`.
- [x] Выполнить первый бэктест и повторный прогон: `./scripts/lab.sh verify` дал `matched: true`, 98 сделок.
- [x] Запустить spot dry-run после совпавших прогонов: `./scripts/lab.sh up`, затем `./scripts/lab.sh start`.

## Futures research, итерация 1

Только бэктест, исторические данные и бумажные расчёты. Конфиги фьючерсов не проходят в режим торговли: entrypoint пускает их только в download-data и backtesting, preflight требует `dry_run=true` и isolated.

- [x] Конфиг исследования `configs/futures_research.json` и база `configs/config.futures-research.json`.
- [x] Проверить 30 кандидатов USDT-M на Bybit: `./scripts/futures.sh universe`.
- [x] Первая волна из 14 ликвидных контрактов. Отбор по сегодняшней ликвидности, поэтому все результаты помечены LIMITED_VALIDATION.
- [x] Свечи 15m, 1h, 4h, mark и funding с 2023-01-01: `./scripts/futures.sh download`.
- [x] Часовой открытый интерес: `./scripts/futures.sh open-interest`.
- [x] Шесть long/short стратегий в `strategies/futures`.
- [x] Скрининг development-окна: `./scripts/futures.sh screen`.
- [x] Событийное исследование паттернов: `./scripts/futures.sh events`.
- [x] Свечи 5m и скрининг 5m.

## Futures research, итерация 2

- [x] Протокол отбора до прогонов: `docs/futures-iteration-2-protocol.md`.
- [x] Данные по 28 листингованным кандидатам: `./scripts/futures.sh download --set listed --timeframes 1h 4h`, `./scripts/futures.sh open-interest --set listed`.
- [x] Набор монет по датам: `./scripts/futures.sh pit-universe`, прогоны `screen --universe pit`.
- [x] Стратегии на funding, OI и кросс-секционном моментуме.
- [x] Отчёт: `docs/futures-iteration-2.md`. Кандидатов в validation по протоколу нет.
- [ ] Итерация 3: протокол для FtOiBreakout 4h.
- [ ] Бумажные портфели. Не начинать, пока кандидат не прошёл validation.

Не доступны в этой итерации (DATA_UNAVAILABLE): история стакана, история ликвидаций, long/short ratio за весь период.

## Stage 2 и дальше

Не начато, кроме futures research выше. Сюда входят пять отдельных стратегий, режим рынка, риск на сделку, walk-forward, out-of-sample, отчёты, PostgreSQL, FastAPI, Telegram и Grafana.

Параметры stage 1 (ставка 100 USDT, стоп 8%, пороги EMA и ADX) — условия пробы движка. Под доходность они не подбирались.
