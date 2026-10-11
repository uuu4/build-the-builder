import json, sys
S = lambda **k: dict(type="string", **k)
N = lambda **k: dict(type="number", **k)
def obj(props, req=None):
    o = {"type": "object", "properties": props}
    if req: o["required"] = req
    return o
CALL = obj({"ani": S(), "lang": S(enum=["tr"])})
RESULT = obj({"guid": S(), "returnCode": S(), "messageText": S(), "code": S(enum=["1","INVALID_ARGUMENTS_ERROR","FB_IVR_CHANNEL_102","FB_IVR_CHANNEL_120","FB_IVR_CHANNEL_121","FB_IVR_CHANNEL_107","FBE00099"]),
              "message": S(), "type": S(enum=["ERROR","WARNING"], nullable=True),
              "details": obj({"guid": S(), "rootCause": S(nullable=True), "errorOrigin": S(nullable=True)})})
DEBT = obj({"statementPaymentStatus": S(enum=["HAS_DEBT","NO_DEBT"]), "transferAmount": N(), "statementDebt": N(), "minPayment": N(),
            "remainingDebt": N(), "remainingMinPayment": N(), "currentPeriodExpense": N(), "totalDebt": N(),
            "totalDebtPaymentStatus": S(enum=["HAS_DEBT","NO_DEBT"]), "remainAutomaticPaymentAmount": N()})
CARD = obj({"cardNumber": S(), "cardNumberLast4": S(), "productName": S(), "status": S(enum=["A"]), "isMainCard": {"type": "boolean"}})
svc = {
 "cards.list": ("The customer's cards the assistant may talk about", obj({"customerNo": S(), "aiFlow": S(enum=["CardOps"])}, ["customerNo"]),
     obj({"cards": {"type": "array", "items": CARD}, "validCardsCount": N(), "exitState": S(enum=["1_CARD","MULTI_CARD"])}), ["404","500"]),
 "cards.balance": ("Statement and due dates, debt per currency", obj({"cardNumber": S()}, ["cardNumber"]),
     obj({"cardNumber": S(), "cardNumberLast4": S(), "productName": S(), "statementDate": S(description="dd.MM.yyyy"), "lastPayDate": S(), "nextStatementDate": S(), "nextLastPayDate": S(),
          "debtTL": DEBT, "debtUSD": DEBT, "debtEUR": DEBT, "debtGBP": DEBT, "statementPaymentStatus": S(enum=["HAS_DEBT","NO_DEBT"]),
          "totalDebtPaymentStatus": S(enum=["HAS_DEBT","NO_DEBT"]), "automaticPaymentFlag": S(enum=["Y","N"])}), ["400","404","500"]),
 "statement.week.get": ("Current statement week and day, joint statement info", obj({"cardNumber": S()}, ["cardNumber"]),
     obj({"cardNumber": S(), "cardNumberLast4": S(), "productName": S(), "statementWeek": N(), "statementDay": N(), "statementDate": S(), "lastPayDate": S(),
          "nextStatementDate": S(), "nextLastPayDate": S(), "relationType": S(enum=["", "M", "C"]), "relatedCardNumber": S(), "relatedCardProductName": S()}), ["404","500"]),
 "statement.week.decide": ("Preview of the dates for a requested week; changes nothing", obj({"cardNumber": S(), "newStatementWeek": S(enum=["1","2","3","4"]), "statementDay": N()}, ["cardNumber","newStatementWeek","statementDay"]),
     obj({"statementDate": S(), "statementDueDate": S(), "statementDay": N(), "responseCode": N(), "responseMessage": S()}), ["400","500"]),
 "statement.week.change": ("Changes the statement week", obj({"cardNumber": S(), "newStatementWeek": S(enum=["1","2","3","4"]), "statementDay": N()}, ["cardNumber","newStatementWeek","statementDay"]),
     obj({"responseCode": N(), "responseMessage": S(), "statementWeek": S(), "statementDay": S(), "exitState": S(enum=["OK"])}), ["400","401","500"]),
 "contact.email.get": ("Registered e-mail / phone", obj({"customerNo": S(), "intAddressInfoType": S(enum=["E","P","B"])}, ["customerNo","intAddressInfoType"]),
     obj({"communicationType": S(enum=["Both","Phone"]), "ibanCountryCode": S(), "ibanAreaCode": S(), "ibanPhoneNum": S(), "ibanEmail": S(), "ttsEmail": S(), "commGramType": S(), "exitState": S(enum=["Done"])}), ["400","500"]),
 "statement.pdf.send": ("Sends the statement PDF by e-mail", obj({"customerNo": S(), "cardNumber": S(), "currencyType": S(enum=["TL","USD","EUR","GBP"]), "statementDate": S(), "emailAddress": S()}, ["customerNo","cardNumber","currencyType","statementDate","emailAddress"]),
     obj({"exitState": S(enum=["DONE"])}), ["400","404","500"]),
}
paths = {}
for name, (summ, data, resp, errs) in svc.items():
    rq = obj({"data": data, "call": CALL}, ["data"])
    rs = obj({"data": resp, "result": RESULT})
    r = {"200": {"description": "Success (result.returnCode '1')", "content": {"application/json": {"schema": rs}}}}
    for e in errs:
        r[e] = {"description": "Error: result only, no data", "content": {"application/json": {"schema": obj({"result": RESULT})}}}
    paths["/voice/v1/" + name] = {"post": {"operationId": name, "summary": summ, "requestBody": {"required": True, "content": {"application/json": {"schema": rq}}}, "responses": r}}
doc = {"openapi": "3.0.3", "info": {"title": "Freya Bank voice statement services", "version": "2026-10-01"},
       "servers": [{"url": "https://btb-bank-mock.latif-akgun1907.workers.dev"}], "paths": paths}
json.dump(doc, open(sys.argv[1], "w", encoding="utf-8"), indent=1, ensure_ascii=False)
