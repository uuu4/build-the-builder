# Arayüz sözleşmesi (taslak v0.4.1, 2026-10-10)

**v0.4.1** (Latif'in ajanı, #3): ajanın `workflow.json`'a elle müdahalesi **yalnızca `lint` hatasını gidermek için** (yeniden koşturma doğrulamasında koşudan koşuya fark prompt metnine insin) · iki gizli brief **sırayla** koşar, `build.py` çalışan simülasyon varsa `cases-run`'ı atlar. Sahiplik: O katmanı Latif'in tarafında.

**v0.4 değişiklikleri** (Emre kararı: **hibrit**): builder = deterministik `build.py` + Claude Agent SDK ajanı (kit örneği gibi) + ajanın çağırdığı kod araçları (`builder.cli`). §0 baştan yazıldı (katmanlar, adım tablosu, skill'ler, süre, yedek yol). §2: `compile_workflow` → `cli compile` (girdi `params.json` + ajanın yazdığı `prompts.json`); C→B yama önerisi kalktı, **ajan düzeltir**. §3: test kod araçlarıyla, ajan okur. §4: trace = SDK akışı + `cli event`. RuleTable şeması (§1) ve derleyici kuralları değişmedi.

**v0.3 değişiklikleri** (§5 kit docs'undan kapandı, Latif'in ajanının #3 raporu; iddialar `docs/workflow-format.md` (WF), `docs/tools-and-code.md` (TC), `docs/api.md`, `freya.py`, `tools/run_cases.py` üzerinde tek tek doğrulandı, **canlıda denenmedi**): §2'ye "Derleyici kuralları (kit)" bölümü, §3'e pratik banka oturumu kısıtı, §5 kapandı. Açık karar: `close_call` nereden çağrılır (§2).

**v0.2 değişiklikleri** (13 pratik vaka okundu, kit'in `public-test-set.json`'u): yeni türler `band`, `attempts`, `statement`, `callback` · `identity_fields`'e alan başına yeniden sorma · `amount_min.floor_field` · rotalara `already_paid` ve `restructuring` · **araç hatasında önce yeniden dene** (PUB-10 tekrar deneyip sözü kaydetmeyi bekliyor; v0.1'deki "hata → doğrudan kapat" bu vakayı kaybettirirdi) · sonuç değerleri sabit bir listeden değil tool API'den.

**v0.1 değişiklikleri** (Latif'in ajanının incelemesi, #3): `installments` türü eklendi · `date_window.from` içine `now` · `rules.validate` runtime'da çakışmada **uyarı** verir (sert hata yalnızca test modunda) · `outcomes` global rotaları da kapsar.

**Durum:** kit (`docs/`, `freya.py`, `minimal_builder.py`, `public-test-set.json`) gelmeden yazıldı, hepsi **tahmin**. Kit ile çelişirse kit geçerli, bu dosya güncellenir. Kırıcı değişiklik olursa sürümü artır ve issue #3'e not düş.

Amaç: üç parçayı ayrı kişiler/ajanlar bağımsız yazabilsin. Parçalar arasındaki tek temas noktası bu dosyadaki üç arayüz.

## 0. Mimari (v0.4: hibrit) ve ortak kurallar

```
python3 builder/build.py <brief_path> <tool_api_path>      # tek komut, elle müdahale yok
```

**Üç katman** (Emre kararı 2026-10-10: hibrit):

1. **`builder/build.py` (deterministik orkestra).** Süreyi tutar, Claude Agent SDK ajanını başlatır, ajan bitince ya da süre dolunca **kendisi** son geçerli workflow'u doğrular, kaydeder, export eder ve trace'i kapatır. Ajan çökse ya da takılsa bile teslim edilebilir bir çıktı bırakır.
2. **Ajan (Claude Agent SDK, kit örneğindeki gibi).** Brief'i okur, kural tablosunu ve düğüm prompt'larını yazar, araçları çağırır, testleri okur, düzeltir. Bilgisi **skill**'lerden gelir. Model `BUILDER_MODEL` (varsayılan `claude-opus-5-5`, kit örneğiyle aynı).
3. **Kod araçları (`python3 -m builder.cli <komut>`).** Hata yapılmaması gereken her şey: OpenAPI'den araç tanımı, parametre türetme, `check` kodu, omurga derleme, lint, dryRun + kaydetme, vaka çalıştırma, trace olayı. Ajan bunları Bash ile çağırır; girdi/çıktı her zaman dosya (JSON), stdout'a kısa özet.

| Adım | Kim | Komut / çıktı |
|---|---|---|
| 1. brief'i oku, kural tablosu yaz | ajan | `out/<slot>/rules.json` (§1 şeması) |
| 2. tabloyu doğrula | kod | `cli rules-validate` → uyarı listesi |
| 3. araç tanımları | kod | `cli tools <tool_api>` → `out/<slot>/tools.json` |
| 4. parametreler | kod | `cli params` → `out/<slot>/params.json` (§2 `BackboneParams`) |
| 5. düğüm prompt'ları | ajan | `out/<slot>/prompts.json` (§2) |
| 6. derle | kod | `cli compile` → `out/<slot>/workflow.json` (omurga şablonu + 3 + 4 + 5) |
| 7. (yalnızca lint hatası varsa) elle düzeltme | ajan | `workflow.json`'da yalnızca lint'in gösterdiği yer; sonra 8 **zorunlu**, sayısı trace'te |
| 8. lint + dryRun + kaydet | kod | `cli deploy` → `out/<slot>/deployed.json` (`workflow_id`, `agent_id`) |
| 9. test | kod çalıştırır, ajan okur | `cli check-test` (yerel), `cli cases-run` (Freya) → `out/<slot>/test-*.json` |
| 10. düzelt | ajan | 5 ya da 7'ye döner; bütçe izin verdikçe |
| 11. kapanış | `build.py` | lint + kaydet + `export_workflow` → `submission/<slot>.workflow.json`, trace → `traces/<slot>.log` |

**Sahiplik (öneri, insanlar netleştirir):** S = skill'ler (brief okuma, omurga bilgisi, Freya kuralları, süreç), K = kod araçları (`builder/cli`, şablonlar, testleri), O = orkestra + test + trace + paketleme (`build.py`, `cases-run`, trace, export, sızıntı testi).

**Skill'ler** (`.claude/skills/`, kit örneğindeki gibi `setting_sources=["project"]`):
- `build-phone-agent`: süreç (yukarıdaki tablo), bütçe kuralları, ne zaman durulur.
- `read-collections-brief`: §1 şeması, kaynak sıralama, memo'nun ezmesi, alıntı zorunluluğu, belirsiz kuralda güvenli değer.
- `collections-backbone`: omurga ve global düğümler, her düğümün işi, sayı kuralları ve zorunlu cümlelerin prompt'a yazılışı.
- `freya-workflow-rules`: §2 "Derleyici kuralları (kit)" özeti; ajanın `workflow.json`'u elle düzenlerken uyacağı kurallar.
Skill'lerde **hiçbir brief değeri yok** (sızıntı testi skill'leri de tarar).

**Süre (30 dk/brief):** `build.py` başlarken `BUILD_DEADLINE` (epoch) ortam değişkenini koyar. Öneri: ajana 25 dk, son 5 dk `build.py`'nin kapanışı. `cli cases-run`, kalan süre bir koşuya yetmiyorsa (`< 12 dk`) **koşmayı reddeder** ve bunu söyler. **İki gizli brief sırayla koşar** (çalışma alanı başına aynı anda 1 simülasyon; paralel koşan ikincinin `cases-run`'ı kuyrukta 30 dk'yı yer). `build.py` başlarken çalışan bir simülasyon varsa beklemez, o koşuda `cases-run`'ı devre dışı bırakır ve `budget_stop` olayı yazar. Toplam 2 × 30 dk, 3 saatlik pencerenin içinde. Süre dolunca `build.py` ajanı durdurur ve son geçerli `workflow.json`'la kapanır; geçerli yoksa `cli compile`'ı mevcut `params.json` + varsayılan prompt'larla koşturup onu teslim eder (**yedek yol**).

Önerilen dizin: `builder/{build.py, cli/, templates/, trace.py}`, `.claude/skills/<ad>/SKILL.md`, `tests/`, `out/`, `traces/`, `submission/`.

Ortak kurallar:
- **Sızıntı yok:** kodda, şablonlarda ve skill'lerde pratik ya da gizli brief'e özgü değer yok (tatil günleri, sonuç adları, tutar/limit sabitleri). `tests/test_no_leak.py` denetler. Değerler yalnızca çalışma zamanında üretilen dosyalardan gelir.
- **Trace:** ajanın her mesajı ve araç çağrısı SDK akışından, kod araçlarının olayları aynı dosyaya (§4).
- **Ara çıktılar diske** (`out/<slot>/...`). Her kod aracı tek başına yeniden koşturulur ve yerelde test edilir.
- **Anahtarlar** yalnızca ortam değişkeni (`env.sh`, gitignore'da). Repoya, skill'e, trace'e, log'a girmez.
- Belirsiz kuralda Policy açısından güvenli değer; her seferinde `cli event uncertain_default ...`.
- Ajan Freya'da elle hiçbir şey değiştirmez; her değişiklik dosyada, `cli deploy` ile.

## 1. RuleTable (ajan yazar → `cli rules-validate`, `cli params` okur)

Dosya: `out/<brief_id>/rules.json`

```json
{
  "brief_id": "string",
  "sources": [{"id": "S1", "path": "briefs/x.md", "kind": "spec|mail|policy|memo|codelist|other", "date": "YYYY-MM-DD|null"}],
  "rules": [ <Rule> ]
}
```

Rule:

```json
{
  "id": "R001",
  "type": "band|date_window|amount_min|installments|holiday|identity_fields|outcome_codes|disclosure|statement|attempts|callback|escalation|call_hours|free",
  "value": { "...tür başına aşağıda..." },
  "source": {"doc": "S1", "quote": "ham metinden birebir alıntı"},
  "source_date": "YYYY-MM-DD|null",
  "supersedes": "R000|null",
  "confidence": "certain|uncertain",
  "applies_to": ["all"],
  "node_hint": "identity|disclose|negotiate|check|record|close|global:<ad>|null"
}
```

`applies_to`: `["all"]` ya da serbest etiketler (`band:<ad>`, `product_type:<tür>`, `customer:multi_product`…). Pratik vakalarda tarih sınırı ve ikna denemesi sayısı gecikme bandına bağlı (aynı müşteride iki ürün iki farklı sınır alabiliyor, PUB-13), bu yüzden `band` + `applies_to` birincil mekanizma.

`value` biçimleri:

| type | value |
|---|---|
| `date_window` | `{"earliest": Rel\|null, "latest": Rel\|null, "from": "now\|today\|due_date\|statement_date"}`, `Rel = {"days": int, "unit": "calendar\|business"}`. `now`/`today` ikisi de **arama zamanından** (`now` değişkeninin tarih kısmı, saat dilimi dönüşümü yok) türetilir, sınır günde kayma olmasın. |
| `band` | `{"name": str, "days_late_min": int\|null, "days_late_max": int\|null, "product_types": [str]\|null}` |
| `amount_min` | `{"min": number\|null, "min_pct_of_due": number\|null, "floor_field": str\|null, "max": number\|null, "per": "payment\|product"}`. `floor_field`: tabanın `get_account` cevabındaki alan adı (pratikte `minimum_payment`/`instalment_amount`), değer kodda değil cevaptan okunur. |
| `installments` | `{"allowed": bool, "max_count": int\|null, "max_gap_days": int\|null}` |
| `holiday` | `{"dates": ["YYYY-MM-DD"], "weekends_blocked": bool, "business_day_definition": "text\|null"}` |
| `identity_fields` | `{"fields": [{"name": str, "format": str, "spoken_example": str\|null}], "required": int, "max_failures": int, "reask_failed_field": int}`. `reask_failed_field`: yalnızca yanlış verilen alan kaç kez yeniden sorulur (PUB-12: telefon bir kez daha, doğum günü sorulmaz). |
| `outcome_codes` | `{"codes": [{"code": str, "meaning": str, "reasons": [str]\|null}]}` |
| `disclosure` | `{"forbidden_before_identity": [str], "third_party_allowed": [str], "forbidden_words_before_identity": [str]}` (örn. bir kelimenin kimlikten önce hiç söylenmemesi) |
| `statement` | `{"when": "after_promise\|identity_failed\|asked_if_bot\|already_paid\|hardship\|minimum_offered\|transfer\|close\|other", "gist": str, "max_times": int\|null}`: belli bir anda söylenmesi gereken cümle |
| `attempts` | `{"what": "persuasion\|minimum_offer\|support_offer\|exact_day_ask\|sympathy\|other", "max": int, "min": int\|null}`: sayı kuralları; hakem "tam bir kez", "iki deneme" diye sayıyor |
| `callback` | `{"earliest": Rel\|null, "time": "customer\|HH:MM", "allowed_with_third_party": bool}` |
| `escalation` | `{"trigger": "dispute\|hardship\|already_paid\|restructuring\|human_request\|abuse\|legal\|wrong_person\|callback\|refusal\|other", "action": "transfer_to_agent\|add_note\|schedule_callback\|record_dispute\|close", "queue": str\|null, "note": str\|null}`. `queue`, `reason` gibi değerler tool API enum'larından. |
| `call_hours` | `{"earliest_local": "HH:MM", "latest_local": "HH:MM", "timezone": str\|null}` |
| `free` | `{"text": str}` |

`rules.validate(table, sources, tool_api)` şunları denetler:
- `id` benzersiz; `supersedes` var olan bir id'ye gider, döngü yok. **Ezilen kural silinmez**; geçerli kurallar = ezilmeyenler.
- `source.quote`, atıf yapılan kaynakta (boşluk normalleştirilerek) **gerçekten geçiyor**; geçmiyorsa `confidence` zorla `uncertain`.
- `identity_fields.fields[].name` ve `outcome_codes.codes[].code`, tool API'nin enum'larıyla uyuşuyor; uyuşmazlık uyarı olarak trace'e.
- Çakışan geçerli kurallar (aynı `type` ve örtüşen `applies_to`): **runtime'da hata değil uyarı.** En yeni `source_date`'li kural seçilir; tarih eşit/yoksa Policy açısından güvenli (daha kısıtlayıcı) olan seçilir. Ötekisi `uncertain` sayılır ve `cli event uncertain_default` ile yazılır. Gizli brief'te 30 dk elle müdahalesiz koşulduğu için sert hata çökme, çökme sıfır puan demektir.
- **İki mod:** `validate(..., strict=False)` runtime (build.py), `strict=True` testler ve yerel koşular. Çakışma, kırık `supersedes` ve eksik alıntı strict'te hata. **Runtime'da (strict=False) hata yalnızca okunamayan veya boş tablo içindir**, geri kalan her şey uyarı + trace olayıdır.

Okuma stratejisi (ajanın işi, skill `read-collections-brief` anlatır; arayüzü etkilemez): iki bağımsız okuyucu + uyuşmazlıkta ham metinden alıntı getiren üçüncü çağrı; alıntı yoksa `uncertain`.

## 2. Parametreler, prompt'lar ve derleme (kod araçları)

`cli params out/<slot>/rules.json <tool_api> -o out/<slot>/params.json` (içeride `derive_params(rules, tool_api) -> BackboneParams`), saf ve deterministik, yerelde sınırsız test edilir.

```json
{
  "identity": {"fields": [{"name": "", "format": ""}], "required": 0, "max_failures": 0, "reask_failed_field": 0},
  "bands":    [{"name": "", "days_late_min": 0, "days_late_max": null, "product_types": null}],
  "check":    {"window_by_band": {"<band>": {}}, "holidays": ["YYYY-MM-DD"], "weekends_blocked": true, "amount": {"floor_field": null}, "installments": null, "business_day_definition": null},
  "attempts": {"<band>": {"persuasion": 0}, "all": {"minimum_offer": 1, "exact_day_ask": 1}},
  "statements": [{"when": "after_promise", "gist": "", "max_times": 1}],
  "tool_retry": {"create_promise": 1},
  "outcomes": {
    "promise": {"outcome": "", "reason": null, "tools": []},
    "no_promise": {}, "not_verified": {}, "not_reached": {}, "tool_fail": {},
    "dispute": {}, "hardship": {}, "already_paid": {}, "restructuring": {}, "wrong_person": {}, "callback": {}, "human_request": {}, "refusal_per_product": {}
  },
  "globals":  [{"name": "dispute", "trigger": "dispute", "action": "record_dispute", "tool": "add_note"}],
  "text_rules": {"identity": ["R002"], "disclose": [], "negotiate": [], "record": [], "close": [], "global:dispute": []},
  "uncertain_applied": [{"rule": "R012", "chosen": "", "why": ""}]
}
```

- `outcomes` anahtarları sabit bir enum değil, **rota adları**; değerler (`outcome`, `reason`, `queue`) tool API enum'larından. Dikkat: hazır "Collections Base" workflow'undaki `close_call` enum'u (`promise|no_promise|not_verified|not_reached`) pratik vakaların beklediği `paid` ve `transferred`'ı içermiyor; enum mutlaka kit'in `tools/openapi.json`'undan alınmalı.
- `outcomes`: **her rota** (omurga ve global düğümler: `dispute`, `hardship`, `wrong_person`, `callback`, `human_request`) → `close_call` için **sabit** `outcome`/`reason` değeri. Değerler tool API enum'larından, model doldurmaz. `tools` ek araç çağrılarını listeler (örn. itirazda `add_note`, geri aramada `schedule_callback`, devirde `transfer_to_agent`) ve `args` içinde sabit değerler taşır. Brief'in sonuç tablosunda bir rotaya karşılık gelen kod yoksa en yakın kod seçilir ve `uncertain_default` yazılır.
- `text_rules`: omurgaya sığmayan kurallar, kural id listesi olarak düğüme atanır. Yeni rota açılmaz.

**`prompts.json`** (ajan yazar): düğüm adı → prompt metni. Anahtarlar omurganın düğüm adları; eksik düğüm için şablondaki varsayılan prompt kullanılır.

```json
{"identity": {"task_message": "", "on_enter_text": null, "routing_prompt": null},
 "negotiate": {"task_message": "", "on_enter_text": null, "routing_prompt": null},
 "global:dispute": {"task_message": "", "on_enter_text": null, "routing_prompt": null}}
```

`cli compile out/<slot> -o out/<slot>/workflow.json` → Freya workflow JSON'u (`freya.py`'nin kabul ettiği biçimde), içeride `compile_workflow(params, prompts, tools) -> WorkflowDoc`:
- Araç tanımları **koddan**, `tool_api`'den (URL, gövde alanları, enum'lar, `required`). LLM yok.
- Düğüm prompt'ları **ajandan** (`prompts.json`); skill, her düğüme yalnızca o düğümün `text_rules` kurallarını yazmasını söyler. Rota kuralları prompt'a değil `routing_prompt`/geçişlere (routing modeli `task_message`'ı görmez).
- `check` kodu bir şablondan; parametreler (tatil, pencere, tutar) `params.json`'dan gömülür, şablonda sabit yok.
- Omurga: `identity → disclose(get_account) → negotiate → check(KOD) → record(create_promise) → close_*`; global düğümler: `dispute`, `hardship`, `already_paid`, `restructuring`, `wrong_person`, `callback`, `human_request`.
- **Araç hatası:** `record` başarısızsa önce `tool_retry` kadar **yeniden dener** (sonuç: tam bir söz kaydı), "kaydettim" yalnızca başarılı cevaptan sonra söylenir. Yeniden denemeler de tükenirse `close_tool_fail` (dürüst cümle). Geçiş koşulu araç cevap değişkeninden (`create_promise_response...`), modelden değil.
- **Çok ürün:** `disclose` bütün ürünleri sormadan önce söyler; `negotiate` ürün başına bandın sınırını uygular; tek geri okuma, tek onay; `record` ürün başına bir `create_promise`; reddedilen ürüne `refusal_per_product` (örn. `add_note`, reason `refused`).
- Sayı kuralları (`attempts`) ve zorunlu cümleler (`statements`) ilgili düğümün prompt'una **sayı olarak** yazılır ("en fazla 1 kez"); mümkünse sayaç değişkeniyle rota (kit'te doğrulanacak).
- **Düzeltme:** ajan yalnızca `rules.json` ve `prompts.json`'u değiştirir, sonra `cli params` / `cli compile` ile yeniden derler. Omurga ve kod düğümleri her koşuda aynı çıkar; koşular arası fark prompt metnine iner (yeniden koşturma doğrulaması: ilk 10'un builder'ını organizatör koşturur, "clearly below" ise giriş silinir). `workflow.json`'a elle müdahale **yalnızca `cli lint` hatasını gidermek için**; her biri `cli event manual_edit ...` ile trace'e. Omurgaya sığmayan kural yeni rota açmaz, ilgili düğümün prompt'una metin olarak girer.
- **`cli lint out/<slot>/workflow.json`** (yerel, saniyeler): bütün `target_node`'lar ve `initial_node` var · kullanılan her araç tanımlı · boş prompt yok · kod düğümlerinde `{{`/`}}` yok, `initial_node` kod düğümü değil · `agent_config` yok · `const` yok · her extraction alanında `min_confidence` · `close_call` workflow düzeyinde `end_of_call`, `outcome`/`reason` `default: "{{final_outcome}}"`/`"{{final_reason}}"` ve `final_outcome` kimlikten önce yazılıyor · yazan araçlarda `maxRetries: 0` · her `api_call` aracında `post_process_code` (`what_to_do_next`). Hata listesi JSON.

### Derleyici kuralları (kit'ten, v0.3)

- **`agent_config` yazılmaz** (WF). Platform doldurur; `freya.py` modeli `AGENT_LLM = experimental-5`'e sabitler. Sıcaklık konu dışı; tutarlılık yapıdan gelir.
- **Her turda 3 model çağrısı var:** extraction, routing, dialogue. **Routing modeli `task_message`'ı görmez** (WF "Three model calls per turn"). Rota kuralı prompt'a yazılırsa etkisizdir; `transitions` (`description`, koşullar), `routing_prompt` ve `extraction_schema`'ya gider.
- **Dallanma:** birden çok `matches_intent` yerine **enum extraction + `equals`** (WF "Fork on an extracted enum"). Deterministik koşullar önce değerlendirilir; biri tutarsa routing modeli çağrılmaz. `equals` string karşılaştırır (`"True"`/`"true"` ikisini de yaz, baz workflow böyle yapıyor).
- **Extraction:** tarih alanları `type: "date"`; **her alana `min_confidence` açıkça** (varsayılan 0,95 katı, düşen değer iz bırakmaz).
- **Kod düğümü:** `node_type: "code"`, `pre_actions` içinde `__function__:code_exec`, `passthrough: true` + son geçiş koşulsuz. `vars["x"] = ...` yazar, sonraki düğümler `{{x}}` okur, `vars.get("now")` erişilir. **Kodda `{{` / `}}` geçmez** (literal kalır, snippet çöker) → parametreler `json.loads('...')` stringi olarak gömülür, Python dict literal'i değil. Asla raise etmez, her okumada yedek değer; rota bayrakları **string** (`ok`/`too_late`/`holiday`). Doğrulanmış modüller: `json`, `re`, `datetime`. **Kod düğümü `initial_node` olmaz** (`/chat/message` ilk kod adımını atlayabiliyor, api.md).
- **Araç parametreleri:** sabit değerler `default` ile (model görmez, `{{var}}` kayıt anında çözülür); **`const` asla** (gönderilmez). Model doldursun istenen alan `default`'suz.
- **Sayaçlar:** her `api_call` aracı için `<araç>_success_count` / `<araç>_failure_count`, `pre_actions` düğümü için `<düğüm>_…` (TC). PUB-10: `create_promise_failure_count greater_than 0` → "tekrar dene" yolu, `create_promise_success_count` → "kaydedildi" yolu. **Yazan araçlarda `maxRetries: 0`** (çift kayıt riski), yeniden deneme rotayla.
- **Araç sonrası sessizlik / olumsuz sonucu yok sayma** pratikte görülmüş (TC "Tool results and the next turn"). Her araca `post_process_code`: `result.pop("header")` + `result["data"]["what_to_do_next"]` = sonucun anlamı ve sıradaki adım tek cümle; düğüm prompt'u buna uymayı söyler. Honesty için şablonun parçası.
- **`deploy` = `freya.validate_workflow` (dryRun) + `freya.save_workflow(slot, wf)`** (ilk seferde yaratır, sonra `.freya-agents.json` ile günceller, `{workflow_id, agent_id}` döner). Kapanış: `freya.export_workflow(workflow_id, path)`. Bozuk yaşam döngüsü aracı çalışma anında **sessizce düşer** → dryRun zorunlu.
- **API:** anahtar `fak_` ile başlar; tarayıcı benzeri `User-Agent` başlığı şart (yoksa `error code: 1010`). `FREYA_API_URL=https://staging-app.freyavoice.ai`.

**AÇIK KARAR: `close_call` nereden çağrılır?**
- (a) Yaşam döngüsü aracı (`alwaysRunsAt: ["end_of_call"]`), gövdede `outcome: {"default": "{{final_outcome}}"}`, `reason: {"default": "{{final_reason}}"}`. TC: bütün `{{var}}` çözülmüşse **model çağrılmaz, handler doğrudan çalışır**; çözülmemişse tek model çağrısı doldurur. **Müşteri ortada kapatsa bile her aramada çalışır.** `response_mapping` `end_of_call`'da uygulanmaz (close_call için gerekmiyor).
- (b) Kapanış düğümünden önce passthrough düğümde `pre_actions` ile (Latif'in ajanının önerisi). Değer yine rotadan; ama arama o düğüme ulaşmadan biterse (müşteri kapatır, `max_node_turns`) `close_call` **hiç çalışmaz** → Outcome kaybı.
- **Öneri: (a)**, şartıyla: `final_outcome`/`final_reason` her yolda erken yazılsın (kimlik düğümü başında güvenli bir başlangıç değeri, sonra her rota günceller) ve dryRun ile doğrulansın. (a) ile (b) birlikte kullanılmaz (iki `close_call` = "bir kez" ihlali riski). Kit örneği (`examples/agent_builder.py`) hangisini kullanıyor, bakılacak.

`cli deploy out/<slot>` = `cli lint` + `freya.validate_workflow` (dryRun) + `freya.save_workflow(slot, wf)` → `out/<slot>/deployed.json`:

```json
{"workflow_id": "", "agent_id": "", "steps": 0, "tools": ["verify_identity"]}
```

Çalışma alanı başına en fazla 10 workflow vardır: ad `brief_id`'den türer, mevcutsa güncellenir, yenisi yaratılmaz.

## 3. Kendi testi (`cli check-test`, `cli cases-run`; ajan okur ve düzeltir)

İki kod aracı, ikisi de `out/<slot>/test-<zaman>.json` yazar:
- `cli check-test out/<slot>` (yerel, Freya'ya gitmez): `rules-validate --strict` özeti, `check` kodunun sınır vakaları (pencerenin son günü, tatil, minimumun 1 altı, `now`'un farklı günleri), `lint`.
- `cli cases-run out/<slot> [--cases <dosya>] [--only ID,...] [--reps N]`: `tools/run_cases.py` sarmalayıcısı; süre kontrolü (§0), sonuçları JSON'a çevirir.

```json
{"cases": [{"id": "", "family": "", "result": "pass|fail|error", "reasons": [], "tool_calls": []}], "pass_rate": 0.0, "reps": 1, "duration_s": 0, "slowest_turn_s": 0}
```

- **Kendi vakaları:** ajan yazar (skill'deki tohum davranış türleri + kural tablosundaki değerler), `cli cases-check <dosya>` biçimi doğrular. `checks` kural tablosu satırlarından.
- Yerel testler (maliyet sıfır, sınırsız): `cli check-test` + kod araçlarının kendi birim testleri (`tests/`) + sızıntı testi. Freya koşusu yalnızca bunlar temizken.
- **Vaka biçimi** kit'in kökteki `public-test-set.json`'u ile aynı: `id, brief, family, level, title, variables{first_name,last_name,title,now}, identity{...doğru güvenlik cevapları}, products[{type, card_last4?, past_due, days_late, minimum_payment|instalment_amount}], script, expected{outcome, reason, promises[{product_id,amount,date}], notes[{product_id,reason}], callbacks[{date,time}], transfers[{queue}]}, checks[str], faults?[{tool, fail_first_n}]`. Builder'ın ürettiği personalar bu biçimde yazılır; `checks` alanı kural tablosundaki satırlardan üretilir (hakem bunlara göre okuyor).
- **Pratik banka kısıtı (kit):** `tools/run_cases.py --cases <dosya>` aynı biçimde herhangi bir JSON'u alır, ama her vaka için banka oturumu `POST /v1/practice/sessions {"case": <id>}` ile açılır; **hesap verisi yalnızca bankanın tanıdığı vaka id'lerinden** gelir. Kendi personalarımız = 13 vakanın hesapları + değiştirilmiş `script`/`checks`. Gizli brief koşusunda (araç alanları değişmiş olacak) kendi testi için banka oturumu olup olmayacağı **belli değil → organizatöre sorulacak**. Yoksa kendi testi = yerel testler + `/chat/message` ile kuru konuşma.
- Freya turları: 1. tur ~8 vaka (kimlik başarısız, sınır tarih, memo'nun değiştirdiği kural, araç hatası, itiraz, zor durum, numarayı iki parçada veren, yazıyla rakam söyleyen), 2. tur yalnızca kalanlar + yama. Tek simülasyon aynı anda çalışır.
- Ajan test sonucunu okur, düzeltir (§2 "Düzeltme"), yeniden `cli deploy` + test. Pratikte (A/B) en fazla 3 tur; gizli brief'te süre izin verdiği kadar.

## 4. Trace (`build.py` + `cli event`)

- `build.py` trace dosyasını açar (`traces/<slot>.jsonl`) ve yolunu `TRACE_PATH` ortam değişkeniyle ajana ve araçlara verir. **Ajanın her mesajı ve araç çağrısı** SDK akışından buraya yazılır (kit örneğindeki gibi); model ve maliyet `ResultMessage`'dan.
- Kod araçları her koşuda bir satır ekler: `{"t": iso, "tool": "cli <komut>", "in": [...], "out": "...", "summary": "..."}`. Ajan ayrıca karar notu düşebilir: `cli event <tür> --msg "..."` (`uncertain_default`, `manual_edit`, `budget_stop`…).
- `cli deploy` her kayıtta `created` olayı yazar (workflow id, agent id, adım ve araç sayısı). `cli cases-run` / `check-test` `test` olayı yazar.
- Kapanışta `build.py`, JSONL'den sayfanın istediği düz metni üretir: `traces/<slot>.log` = başlangıç/bitiş zamanı · her model çağrısı (model + **tek satır amaç**) · Freya'da yaratılan workflow/agent id, adım ve araç sayısı · kendi testleri ve sonucu.
- Anahtar değerleri her iki dosyada maskelenir (ortamdaki bilinen sır değerleri). Teslim edilen `.log` ve `.jsonl` commit edilmeden önce `cli trace-scan` ile taranır.

## 5. Kit'e bağlı noktalar (v0.3: kapandı, ayrıntı §2 "Derleyici kuralları")

1. Kod düğümü değişken yazabiliyor mu → **evet** (`vars[...]`, `{{x}}`).
2. `outcome`/`reason`'ı rotadan sabitlemek → **evet**, `default: "{{final_outcome}}"`; nereden çağrılacağı açık karar (§2).
3. Kendi personalarımız → **kısmen**: yalnızca 13 vakanın banka hesaplarıyla; gizli koşuda belirsiz (organizatöre soru).
4. `freya.py` → `save_workflow`, `validate_workflow`, `update_workflow`, `export_workflow`, `create_personas`, `run_simulation`, `get_iteration`, `get_call`.
5. `temperature` → konu dışı, `agent_config` yazılmaz.
6. Dizin/komut → sayfadaki `run_command` ile birebir: `python3 builder/build.py {brief_path} {tool_api_path}`, `submission/hidden-N.workflow.json`, `traces/hidden-N.log`.

**Organizatöre sorulacak:** gizli brief koşusunda kendi testleri için pratik banka oturumu açılabiliyor mu (yeni şemaya uygun)?
