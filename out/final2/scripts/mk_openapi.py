import json
S=lambda t,**k: dict(type=t,**k)
res={"type":"object","properties":{"guid":S("string"),"returnCode":S("string",description="'1' = success; otherwise an error code (INVALID_ARGUMENTS_ERROR, FB_IVR_CHANNEL_102, FB_IVR_CHANNEL_120, FB_IVR_CHANNEL_121, FB_IVR_CHANNEL_107, FBE00099)"),"messageText":S("string"),"code":S("string"),"message":S("string"),"type":S("string",enum=["ERROR","WARNING"],nullable=True),"details":{"type":"object","properties":{"guid":S("string"),"rootCause":S("string"),"errorOrigin":S("string")}}}}
call={"type":"object","properties":{"ani":S("string"),"lang":S("string",default="tr")}}
debt={"type":"object","properties":{"statementPaymentStatus":S("string",enum=["HAS_DEBT","NO_DEBT"]),"transferAmount":S("number"),"statementDebt":S("number"),"minPayment":S("number"),"remainingDebt":S("number"),"remainingMinPayment":S("number"),"currentPeriodExpense":S("number"),"totalDebt":S("number"),"totalDebtPaymentStatus":S("string",enum=["HAS_DEBT","NO_DEBT"]),"remainAutomaticPaymentAmount":S("number")}}
def op(name,summary,req,reqd,resp):
    return {"post":{"operationId":name,"summary":summary,
      "requestBody":{"required":True,"content":{"application/json":{"schema":{"type":"object","required":["data"],"properties":{"data":{"type":"object","required":reqd,"properties":req},"call":call}}}}},
      "responses":{"200":{"description":"Success (result.returnCode '1')","content":{"application/json":{"schema":{"type":"object","properties":{"data":{"type":"object","properties":resp},"result":res}}}}},
                   "400":{"description":"INVALID_ARGUMENTS_ERROR"},"404":{"description":"WARNING not found code"},"500":{"description":"FBE00099 technical error"}}}}
card={"type":"object","properties":{"cardNumber":S("string"),"cardNumberLast4":S("string"),"productName":S("string"),"status":S("string",enum=["A"]),"isMainCard":S("boolean")}}
wk={"cardNumber":S("string"),"newStatementWeek":S("integer",enum=[1,2,3,4]),"statementDay":S("integer")}
doc={"openapi":"3.0.3","info":{"title":"Freya Bank voice statement/debt services","version":"2026-10-01"},
 "servers":[{"url":"https://btb-bank-mock.latif-akgun1907.workers.dev/voice/v1"}],
 "paths":{
 "/cards.list":op("cards.list","The customer's eligible cards. 404 FB_IVR_CHANNEL_102 = no valid card.",{"customerNo":S("string"),"aiFlow":S("string",default="CardOps")},["customerNo"],
   {"cards":{"type":"array","items":card},"validCardsCount":S("integer"),"exitState":S("string",enum=["1_CARD","MULTI_CARD"])}),
 "/cards.balance":op("cards.balance","Statement and due dates, debt per currency. 404 FB_IVR_CHANNEL_120 = card not found.",{"cardNumber":S("string")},["cardNumber"],
   {"cardNumber":S("string"),"cardNumberLast4":S("string"),"productName":S("string"),"statementDate":S("string",description="dd.MM.yyyy"),"lastPayDate":S("string"),"nextStatementDate":S("string"),"nextLastPayDate":S("string"),
    "debtTL":debt,"debtUSD":debt,"debtEUR":debt,"debtGBP":debt,"statementPaymentStatus":S("string",enum=["HAS_DEBT","NO_DEBT"]),"totalDebtPaymentStatus":S("string",enum=["HAS_DEBT","NO_DEBT"]),"automaticPaymentFlag":S("string",enum=["Y","N"])}),
 "/statement.week.get":op("statement.week.get","Current statement week/day and joint statement info. 404 FB_IVR_CHANNEL_121.",{"cardNumber":S("string")},["cardNumber"],
   {"cardNumber":S("string"),"cardNumberLast4":S("string"),"productName":S("string"),"statementWeek":S("integer"),"statementDay":S("integer"),"statementDate":S("string"),"lastPayDate":S("string"),"nextStatementDate":S("string"),"nextLastPayDate":S("string"),"relationType":S("string",enum=["","M","C"]),"relatedCardNumber":S("string"),"relatedCardProductName":S("string")}),
 "/statement.week.decide":op("statement.week.decide","Preview of dates for a requested week; changes nothing.",wk,["cardNumber","newStatementWeek","statementDay"],
   {"statementDate":S("string"),"statementDueDate":S("string"),"statementDay":S("integer"),"responseCode":S("integer"),"responseMessage":S("string")}),
 "/statement.week.change":op("statement.week.change","Changes the statement week. Success = exitState OK and responseCode 0.",wk,["cardNumber","newStatementWeek","statementDay"],
   {"responseCode":S("integer"),"responseMessage":S("string"),"statementWeek":S("string"),"statementDay":S("string"),"exitState":S("string",enum=["OK"])}),
 "/contact.email.get":op("contact.email.get","Registered e-mail / phone.",{"customerNo":S("string"),"intAddressInfoType":S("string",enum=["E","P","B"])},["customerNo","intAddressInfoType"],
   {"communicationType":S("string",enum=["Both","Phone","Email"]),"ibanCountryCode":S("string"),"ibanAreaCode":S("string"),"ibanPhoneNum":S("string"),"ibanEmail":S("string"),"ttsEmail":S("string"),"commGramType":S("string"),"exitState":S("string",enum=["Done"])}),
 "/statement.pdf.send":op("statement.pdf.send","Sends the statement PDF by e-mail. 404 FB_IVR_CHANNEL_107 = no PDF.",{"customerNo":S("string"),"cardNumber":S("string"),"currencyType":S("string",enum=["TL","USD","EUR","GBP"]),"statementDate":S("string"),"emailAddress":S("string")},["customerNo","cardNumber","currencyType","statementDate","emailAddress"],
   {"exitState":S("string",enum=["DONE"])}),
 }}
json.dump(doc,open("out/final2/tools.openapi.json","w",encoding="utf-8"),indent=1,ensure_ascii=False)
