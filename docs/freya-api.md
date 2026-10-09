# Freya platform API notu

Anahtarsız, dokümandan derlendi (docs.freyavoice.ai, 2026-10-08). **Canlıda denenmedi**; starter kit ile çelişirse kit geçerlidir. Duman testi sonuçları altına eklenecek.

## Bağlantı
- Base: `https://app.freyavoice.ai/api/v2` · Auth: `Authorization: Bearer <anahtar>` (app.freyavoice.ai → Settings → API Keys; çalışma alanına bağlı, bir kez gösterilir)
- Yanıt zarfı: `{success, data:{message, result}}`
- Ayrı model API'leri: `stt.freyavoice.ai`, `tts.freyavoice.ai/v1`
- Spec: `https://docs.freyavoice.ai/api-reference/openapi.json` (106 işlem). Doküman dizini: `https://docs.freyavoice.ai/llms.txt` (her sayfanın `.md` hâli var).
- **Uyarı:** `openapi.json` içinde `/simulations`, `/personas`, `/unit-tests`, `/branches`, `/chat` YOK. Bu uçlar yalnızca ayrı doküman sayfalarında (staging spec'ten üretilmiş). Canlıda çalıştıkları doğrulanmadı.

## Ajan (`POST /agents`, `PUT /agents/{id}`)
- `workspaceId`, `name` (≤100), `config.llmConfig`: `provider`, `model`, `systemPrompt` (≤100.000 karakter), `firstMessage`, `firstMessageMode`, `maxTokens` (≤4000), `temperature` (0–2), `thinkingBudget`, `tools[]`
- `tools[]`: `{type:"function", function:{name, handler, description, parameters(JSON schema), transition_to}, config:{maxPerNTurns, alwaysRunsAt:[each_turn|start_of_call|end_of_call], timeoutMs}}`. **`handler` biçimi belgelenmemiş.**
- `config.ttsConfig`: provider, model, voiceId, language, speed
- Sürümler: `GET/POST /agents/{id}/versions`, `PUT .../versions/{vid}` (aktifleştir), `POST .../versions/rollback`
- Workflow'da yalnızca okuma uçları var (`GET /workflow`, `/workflow/{id}`, şablonlar). Oluşturma ucu listede yok.

## Test döngüsü
- **Persona** (`POST /personas`, toplu ≤200): `name`, `prompt`, `successCriteria`, `systemPrompt`, `evaluationPrompt`, `tags`, `agentIds`
- **Simülasyon** (`POST /simulations`): `name`, `agentId`, `selectedPersonaIds` (1–1000), `mode: voice|chat`, `runsPerPersona` (1–50), `maxConcurrentCalls`, `maxCallDurationSeconds` (60–3600), `maxRetries`, `assertions[]` (UUID), `agentVersionId`, LLM geçersiz kılmaları (assistant, persona, analysis, routing, extraction)
- **Sonuç:** `GET /simulations/{id}`, `GET /simulations/{id}/iterations` → `totalRuns, passedRuns, failedRuns, inconclusiveRuns, errorRuns, passRate`; `POST /simulations/{id}/rerun` yeni iterasyon açar; `GET /simulations/version-persona-runs?entityVersionId=` sürüm bazlı geçti/kaldı
- **Chat:** `POST /chat/message` ajanı metinle tur tur sürer (`agentId`, `message`, `callId`, `versionId`, `fromMessageId` ile dallanma). Plan B için kendi persona simülatörümüzün temeli.
- **Unit test** (`POST /unit-tests`): deterministik iddialar: `routing`, `extraction` (exists/equals/contains/regex/absent), `tool_call` (araç + argümanlar)

## Bilinmeyenler
- Hackathon bu API'yi mi, özel bir harness/SDK'yı mı kullanıyor?
- Rate limit, kredi maliyeti, simülasyon süresi/koşu hakkı.
- `handler` biçimi; `assertions` UUID'lerinin neyi gösterdiği; puanın hesaplanması.
