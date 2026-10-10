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

## Duman testi sonuçları (2026-10-10, kit v3, Latif'in çalışma alanı)

Takımın tek çalışma alanı ve tek anahtarı Latif'inki (issue #3). Hepsi `examples/base-agent.json` ile.

| Adım | Sonuç | Süre |
|---|---|---|
| `GET /api/v2/workspaces` | tek çalışma alanı döndü, `freya.workspace_id()` onu seçiyor | — |
| `validate_workflow` (dryRun) | `{"valid": true, "dryRun": true}`. Hatalı workflow'da ne döndüğü henüz denenmedi | 0,4 sn |
| `save_workflow` ilk çağrı | yarattı, `{workflow_id, agent_id}` döndü | 0,5 sn |
| `save_workflow` ikinci çağrı | güncelledi + modeli `experimental-5`'e çekti + yayınladı (sürüm 1) | 1,3 sn |
| `/chat/message` 2 tur | çalışıyor: "Am I speaking with the account holder?" → borcu söylemeden doğum tarihini sordu | 1,5–2,2 sn/tur |
| `run_cases.py --brief A --only PUB-01` | simülasyon `completed`, **32 sn**, en yavaş ajan turu 3 sn | 32 sn |

PUB-01 sonucu **FAIL**. Bu beklenen bir sonuç, README'ye göre örnek ajan 13 vakanın 2'sini geçiyor. Bilgi verici olan kısım:
- Banka kaydı doğruydu: `verify > verify > get_account > promise > close_call`.
- Kalan konuşma kontrolü: söz kaydedildikten sonra "SMS ile onay gönderilecek" cümlesi söylenmedi.
- Demek ki **Outcome geçip Policy/Honesty'de kalmak** gerçek bir risk. Brief'teki zorunlu cümleler (`statement` türü) önemli.

Notlar:
- `create_workflow` modeli ayarlamıyor. İlk kayıttan sonra bir kez daha `save_workflow` (güncelle + yayınla) gerekiyor, yoksa sohbet başlamayabilir (`freya.py` yorumu).
- `.freya-agents.json`, `.personas.json`, `results/` çalışma alanına özgü, `.gitignore`'a eklendi.
