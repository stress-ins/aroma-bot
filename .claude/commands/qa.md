Ты — QA Engineer Software Factory.

Запусти полный набор тестов и сформируй отчёт.

## Шаги

### 1. Backend тесты
```bash
.venv/bin/python -m pytest tests/ -q --ignore=tests/ui -n auto --tb=short
```

### 2. UI тесты (Playwright)
```bash
.venv/bin/python -m pytest tests/ui/ -q --tb=short
```

### 3. Smoke тесты (если есть)
```bash
.venv/bin/python -m pytest tests/smoke/ -q --tb=short 2>/dev/null || echo "No smoke tests"
```

### 4. Проверка покрытия новых изменений
- Посмотри `git diff origin/main...HEAD` — какие файлы изменились
- Проверь, есть ли тесты для каждого изменённого модуля
- Если нет — отметь в отчёте как MISSING COVERAGE

### 5. UX Review (если затронуты карточки масел)
```python
# Только если изменились карточки
from bot.agents.ux_reviewer import review_card_ux
result = await review_card_ux(card_data)
# Проверить: result["score"] >= 0.7
```

### 6. Aromatherapy Expert (если затронуты данные масел)
```python
# Только если изменились данные карточек
from bot.agents.aromatherapy_expert import verify_card_content
result = await verify_card_content(card, dry_run=True)
# Проверить: result["passed"] == True
```

## Формат отчёта

```
## QA Report

### Backend Tests
- Total: N | Passed: N | Failed: N | Skipped: N
- Duration: Xs

### UI Tests
- Total: N | Passed: N | Failed: N
- Duration: Xs

### Coverage Check
- [ ] Все изменённые модули имеют тесты
- Missing: ...

### UX Review (если применимо)
- Score: X.XX | Passed: yes/no

### Expert Verification (если применимо)
- Passed: yes/no | Issues: ...

### Verdict: GREEN / RED / YELLOW (с пояснением)
```

Если что-то RED — перечисли конкретные падающие тесты и предложи fix.
