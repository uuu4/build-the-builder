# Arayüz sözleşmesi (taslak v0, 2026-10-10)

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
  "type": "date_window|amount_min|holiday|identity_fields|outcome_codes|disclosure|escalation|call_hours|free",
  "value": { "...tür başına aşağıda..." },
  "source": {"doc": "S1", "quote": "ham metinden birebir alıntı"},
  "source_date": "YYYY-MM-DD|null",
  "supersedes": "R000|null",
  "confidence": "certain|uncertain",
  "applies_to": ["all"],
  "node_hint": "identity|disclose|negotiate|check|record|close|global:<ad>|null"
}
```

`applies_to`: `["all"]` ya da serbest etiketler (`product:<id>`, `customer:multi_product`…).

`value` biçimleri:

| type | value |
|---|---|
| `date_window` | `{"earliest": Rel\|null, "latest": Rel\|null, "from": "today\|due_date\|statement_date"}`, `Rel = {"days": int, "unit": "calendar\|business"}` |
| `amount_min` | `{"min": number\|null, "min_pct_of_due": number\|null, "max": number\|null, "per": "payment\|product"}` |
| `holiday` | `{"dates": ["YYYY-MM-DD"], "weekends_blocked": bool, "business_day_definition": "text\|null"}` |
| `identity_fields` | `{"fields": [{"name": str, "format": str, "spoken_example": str\|null}], "required": int, "max_failures": int}` |
| `outcome_codes` | `{"codes": [{"code": str, "meaning": str, "reasons": [str]\|null}]}` |
| `disclosure` | `{"forbidden_before_identity": [str], "third_party_allowed": [str], "required_statements": [str]}` |
| `escalation` | `{"trigger": "dispute\|hardship\|human_request\|abuse\|legal\|wrong_person\|callback\|other", "action": "transfer_to_agent\|add_note\|schedule_callback\|record_dispute\|close", "note": str\|null}` |
| `call_hours` | `{"earliest_local": "HH:MM", "latest_local": "HH:MM", "timezone": str\|null}` |
| `free` | `{"text": str}` |

`rules.validate(table, sources, tool_api)` şunları denetler:
- `id` benzersiz; `supersedes` var olan bir id'ye gider, döngü yok. **Ezilen kural silinmez**; geçerli kurallar = ezilmeyenler.
- `source.quote`, atıf yapılan kaynakta (boşluk normalleştirilerek) **gerçekten geçiyor**; geçmiyorsa `confidence` zorla `uncertain`.
- `identity_fields.fields[].name` ve `outcome_codes.codes[].code`, tool API'nin enum'larıyla uyuşuyor; uyuşmazlık uyarı olarak trace'e.
- Çakışan geçerli kurallar (aynı `type` ve örtüşen `applies_to`) hata verir; çözüm `supersedes` ya da `applies_to` ayrımı.

Okuma stratejisi (A'nın iç işi, arayüzü etkilemez): iki bağımsız okuyucu + uyuşmazlıkta ham metinden alıntı getiren üçüncü çağrı; alıntı yoksa `uncertain`.

## 2. Derleyici girdisi ve çıktısı (B)

`derive_params(rules, tool_api) -> BackboneParams`, saf ve deterministik, yerelde sınırsız test edilir.

```json
{
  "identity": {"fields": [{"name": "", "format": ""}], "required": 0, "max_failures": 0},
  "check":    {"window": {}, "holidays": ["YYYY-MM-DD"], "weekends_blocked": true, "amount": {}, "business_day_definition": null},
  "outcomes": {"promise": {"outcome": "", "reason": null}, "no_promise": {}, "not_verified": {}, "not_reached": {}, "tool_fail": {}},
  "globals":  [{"name": "dispute", "trigger": "dispute", "action": "record_dispute", "tool": "add_note"}],
  "text_rules": {"identity": ["R002"], "disclose": [], "negotiate": [], "record": [], "close": [], "global:dispute": []},
  "uncertain_applied": [{"rule": "R012", "chosen": "", "why": ""}]
}
```

- `outcomes`: omurga rotası → `close_call` için **sabit** `outcome`/`reason` değeri; değerler tool API enum'larından (model doldurmaz).
- `text_rules`: omurgaya sığmayan kurallar, kural id listesi olarak düğüme atanır. Yeni rota açılmaz.

`compile_workflow(...) -> WorkflowDoc` (Freya workflow JSON'u, `freya.py`'nin kabul ettiği biçimde):
- Araç tanımları **koddan**, `tool_api`'den (URL, gövde alanları, enum'lar, `required`). LLM yok.
- Düğüm prompt'ları LLM ile; her düğüm yalnızca kendi `text_rules` kurallarını ve sabit çerçeveyi görür.
- `check` kodu bir şablondan; parametreler (tatil, pencere, tutar) `params.json`'dan gömülür, şablonda sabit yok.
- Omurga: `identity → disclose(get_account) → negotiate → check(KOD) → record(create_promise) → close_*`; global düğümler: `dispute`, `hardship`, `wrong_person`, `callback`, `human_request`.
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
