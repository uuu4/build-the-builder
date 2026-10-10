# Arayüz sözleşmesi (taslak v0.2, 2026-10-10)

**v0.2 değişiklikleri** (13 pratik vaka okundu, kit'in `public-test-set.json`'u): yeni türler `band`, `attempts`, `statement`, `callback` · `identity_fields`'e alan başına yeniden sorma · `amount_min.floor_field` · rotalara `already_paid` ve `restructuring` · **araç hatasında önce yeniden dene** (PUB-10 tekrar deneyip sözü kaydetmeyi bekliyor; v0.1'deki "hata → doğrudan kapat" bu vakayı kaybettirirdi) · sonuç değerleri sabit bir listeden değil tool API'den.

**v0.1 değişiklikleri** (Latif'in ajanının incelemesi, #3): `installments` türü eklendi · `date_window.from` içine `now` · `rules.validate` runtime'da çakışmada **uyarı** verir (sert hata yalnızca test modunda) · `outcomes` global rotaları da kapsar.

**Durum:** kit (`docs/`, `freya.py`, `minimal_builder.py`, `public-test-set.json`) gelmeden yazıldı, hepsi **tahmin**. Kit ile çelişirse kit geçerli, bu dosya güncellenir. Kırıcı değişiklik olursa sürümü artır ve issue #3'e not düş.

Amaç: üç parçayı ayrı kişiler/ajanlar bağımsız yazabilsin. Parçalar arasındaki tek temas noktası bu dosyadaki üç arayüz.

## 0. Hat ve ortak kurallar

```
python3 builder/build.py <brief_path> <tool_api_path>      # tek komut, elle müdahale yok
```

| Aşama | İmza | Sahip (öneri) |
|---|---|---|
| 1. brief okuma | `read_brief(brief_path, tool_api, trace, budget) -> RuleTable` | A |
| 2. parametre türetme | `derive_params(rules, tool_api) -> BackboneParams` (saf, LLM yok) | B |
| 3. derleme | `compile_workflow(params, rules, tool_api, trace, budget, overrides=None) -> WorkflowDoc` | B |
| 4. yükleme | `deploy(doc, trace) -> Deployed` (`freya.py` sarmalayıcı) | B |
| 5. kendi testi | `self_test(deployed, rules, params, trace, budget) -> TestReport` | C |
| 6. kapanış | `export_workflow`, trace'i yaz, özet | C |

Önerilen dizin: `builder/{build.py, rules.py, reader/, compiler/, deploy.py, selftest/, trace.py, budget.py}`, `tests/`, `traces/`, `submission/`.

Ortak kurallar:
- **Sızıntı yok:** kodda ve prompt şablonlarında pratik ya da gizli brief'e özgü değer yok (tatil günleri, sonuç adları, tutar/limit sabitleri). `tests/test_no_leak.py` bunu denetler. Değerler yalnızca çalışma zamanında üretilen tablolardan gelir.
- **Her model çağrısı** `trace.llm(...)` içinden geçer.
- **Her aşama `budget` alır.** 30 dk toplam sınır, öneri dağılımı: okuma 8, derleme 5, yükleme 2, kendi testi 12, tampon 3. `budget.remaining()` saniye döner; biterse aşama elindeki en iyi sonucu döndürür.
- **Ara çıktılar diske:** `out/<brief_id>/rules.json`, `params.json`, `workflow.json`. Her aşama tek başına yeniden koşturulur.
- **Anahtarlar** yalnızca ortam değişkeni. Repoya, trace'e, logda yok.
- Belirsiz kuralda varsayılan, Policy açısından güvenli değer; her seferinde `trace.event("uncertain_default", ...)`.

## 1. RuleTable (A → B)

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
- Çakışan geçerli kurallar (aynı `type` ve örtüşen `applies_to`): **runtime'da hata değil uyarı.** En yeni `source_date`'li kural seçilir; tarih eşit/yoksa Policy açısından güvenli (daha kısıtlayıcı) olan seçilir. Ötekisi `uncertain` sayılır ve `trace.event("uncertain_default", ...)` ile yazılır. Gizli brief'te 30 dk elle müdahalesiz koşulduğu için sert hata çökme, çökme sıfır puan demektir.
- **İki mod:** `validate(..., strict=False)` runtime (build.py), `strict=True` testler ve yerel koşular. Çakışma, kırık `supersedes` ve eksik alıntı strict'te hata. **Runtime'da (strict=False) hata yalnızca okunamayan veya boş tablo içindir**, geri kalan her şey uyarı + trace olayıdır.

Okuma stratejisi (A'nın iç işi, arayüzü etkilemez): iki bağımsız okuyucu + uyuşmazlıkta ham metinden alıntı getiren üçüncü çağrı; alıntı yoksa `uncertain`.

## 2. Derleyici girdisi ve çıktısı (B)

`derive_params(rules, tool_api) -> BackboneParams`, saf ve deterministik, yerelde sınırsız test edilir.

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

`compile_workflow(...) -> WorkflowDoc` (Freya workflow JSON'u, `freya.py`'nin kabul ettiği biçimde):
- Araç tanımları **koddan**, `tool_api`'den (URL, gövde alanları, enum'lar, `required`). LLM yok.
- Düğüm prompt'ları LLM ile; her düğüm yalnızca kendi `text_rules` kurallarını ve sabit çerçeveyi görür.
- `check` kodu bir şablondan; parametreler (tatil, pencere, tutar) `params.json`'dan gömülür, şablonda sabit yok.
- Omurga: `identity → disclose(get_account) → negotiate → check(KOD) → record(create_promise) → close_*`; global düğümler: `dispute`, `hardship`, `already_paid`, `restructuring`, `wrong_person`, `callback`, `human_request`.
- **Araç hatası:** `record` başarısızsa önce `tool_retry` kadar **yeniden dener** (sonuç: tam bir söz kaydı), "kaydettim" yalnızca başarılı cevaptan sonra söylenir. Yeniden denemeler de tükenirse `close_tool_fail` (dürüst cümle). Geçiş koşulu araç cevap değişkeninden (`create_promise_response...`), modelden değil.
- **Çok ürün:** `disclose` bütün ürünleri sormadan önce söyler; `negotiate` ürün başına bandın sınırını uygular; tek geri okuma, tek onay; `record` ürün başına bir `create_promise`; reddedilen ürüne `refusal_per_product` (örn. `add_note`, reason `refused`).
- Sayı kuralları (`attempts`) ve zorunlu cümleler (`statements`) ilgili düğümün prompt'una **sayı olarak** yazılır ("en fazla 1 kez"); mümkünse sayaç değişkeniyle rota (kit'te doğrulanacak).
- `overrides`: C'nin yama önerisi (`[{"node": "negotiate", "reason": "", "new_text": ""}]`). Yalnızca **düğüm prompt metinleri** değişir; omurga ve parametreler değişmez.
- `validate_workflow(doc) -> [hata]`: bütün `target_node`'lar var, `initial_node` var, kullanılan her araç tanımlı, boş prompt yok. Yükleme öncesi zorunlu.

`deploy(doc, trace) -> Deployed`:

```json
{"workflow_id": "", "agent_id": "", "steps": 0, "tools": ["verify_identity"]}
```

Çalışma alanı başına en fazla 10 workflow vardır: ad `brief_id`'den türer, mevcutsa güncellenir, yenisi yaratılmaz.

## 3. Kendi testi (C)

`self_test(...) -> TestReport`:

```json
{"cases": [{"id": "", "family": "", "result": "pass|fail|error", "reasons": [], "tool_calls": []}], "pass_rate": 0.0, "rounds": 0, "patch_proposals": [{"node": "", "reason": "", "new_text": ""}]}
```

- `persona_from_rules(rules, params) -> [Case]`: elle yazılmış tohum davranış türü + kural tablosundaki değerler. Biçim kit'in `public-test-set.json`'una uyacak (kit gelince doğrulanır).
- Yerel testler (Freya'ya gitmez, maliyet sıfır): `rules.validate`, `derive_params`, `check` kodunun sınır vakaları (pencerenin son günü, tatil, minimumun 1 altı), `validate_workflow`, sızıntı testi.
- **Vaka biçimi** kit'in kökteki `public-test-set.json`'u ile aynı: `id, brief, family, level, title, variables{first_name,last_name,title,now}, identity{...doğru güvenlik cevapları}, products[{type, card_last4?, past_due, days_late, minimum_payment|instalment_amount}], script, expected{outcome, reason, promises[{product_id,amount,date}], notes[{product_id,reason}], callbacks[{date,time}], transfers[{queue}]}, checks[str], faults?[{tool, fail_first_n}]`. Builder'ın ürettiği personalar bu biçimde yazılır; `checks` alanı kural tablosundaki satırlardan üretilir (hakem bunlara göre okuyor).
- Freya turları: 1. tur ~8 vaka (kimlik başarısız, sınır tarih, memo'nun değiştirdiği kural, araç hatası, itiraz, zor durum, numarayı iki parçada veren, yazıyla rakam söyleyen), 2. tur yalnızca kalanlar + yama. Tek simülasyon aynı anda çalışır.
- C yamayı **önerir**, B `overrides` ile uygular. C workflow'u doğrudan düzenlemez.

## 4. Trace (hepsi)

```python
class Trace:
    def __init__(self, brief_id: str, path: str): ...
    def llm(self, purpose: str, model: str, call: Callable[[], R], *, in_tokens=None, out_tokens=None) -> R
    def event(self, kind: str, **fields) -> None            # uncertain_default, validate_warning, ...
    def created(self, what: str, id: str, steps: int | None = None, tools: list[str] | None = None) -> None   # what: workflow|agent
    def test(self, name: str, result: str, detail: str = "") -> None                                         # pass|fail|error
    def finish(self) -> None                                 # bitiş zamanı, JSONL -> düz metin
```

- Çıktı: `traces/<brief_id>.jsonl` ve okunur düz metin `traces/<brief_id>.log`.
- İçerik sayfanın istediğiyle birebir: başlangıç/bitiş zamanı · her model çağrısı (hangi model, **tek satır amaç**) · Freya'da yaratılan workflow/agent id, adım ve araç sayısı · builder'ın kendi yaptığı test ve sonucu.
- `purpose` ≤ 100 karakter. Anahtar değerleri çıktıdan maskelenir (ortamdaki bilinen sır değerleri).

## 5. Kit'e bağlı açık noktalar

1. Konuşma düğümleri arasında **kod düğümü** çalışıp değişken yazabiliyor mu?
2. Geçişte `outcome`/`reason` değerini **düğüm bazında sabit atayabiliyor muyuz** (`response_mapping`, `on_enter`…)? Olmazsa `close_call` yine modele kalır.
3. Kendi personalarımızı kit simülasyonuna verebiliyor muyuz? Yoksa `/chat/message` ile kendi simülatörümüz.
4. `freya.py` fonksiyon adları ve imzaları (`deploy`, `export_workflow`).
5. `temperature` serbest mi?
6. Dizin ve komut kit'in örneğiyle uyumlu mu (`builder/build.py`)?
