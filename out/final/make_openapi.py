import json
S=lambda t="string",**k: dict(type=t,**k)
def debt():
    return S("object",properties={"statementPaymentStatus":S(enum=["HAS_DEBT","NO_DEBT"]),"transferAmount":S("number"),"statementDebt":S("number"),"minPayment":S("number"),"remainingDebt":S("number"),"remainingMinPayment":S("number"),"currentPeriodExpense":S("number"),"totalDebt":S("number"),"totalDebtPaymentStatus":S(enum=["HAS_DEBT","NO_DEBT"]),"remainAutomaticPaymentAmount":S("number")})
RESULT=S("object",properties={"guid":S(),"returnCode":S(),"messageText":S(),"code":S(),"message":S(),"type":S(enum=["ERROR","WARNING"]),"details":S("object")})
CALL=S("object",properties={"ani":S(),"lang":S(default="tr")})
ops={
 "cards.list":({"customerNo":S(),"aiFlow":S(default="CardOps")},["customerNo"],{"cards":S("array",items=S("object",properties={"cardNumber":S(),"cardNumberLast4":S(),"productName":S(),"status":S(enum=["A"]),"isMainCard":S("boolean")})),"validCardsCount":S("integer"),"exitState":S(enum=["1_CARD","MULTI_CARD"])},"Customer's cards the assistant may talk about. 404 FB_IVR_CHANNEL_102 = no valid card."),
 "cards.balance":({"cardNumber":S()},["cardNumber"],{"cardNumber":S(),"cardNumberLast4":S(),"productName":S(),"statementDate":S(description="dd.MM.yyyy"),"lastPayDate":S(),"nextStatementDate":S(),"nextLastPayDate":S(),"debtTL":debt(),"debtUSD":debt(),"debtEUR":debt(),"debtGBP":debt(),"statementPaymentStatus":S(enum=["HAS_DEBT","NO_DEBT"]),"totalDebtPaymentStatus":S(enum=["HAS_DEBT","NO_DEBT"]),"automaticPaymentFlag":S(enum=["Y","N"])},"Statement and due dates, debt per currency. 404 FB_IVR_CHANNEL_120."),
 "statement.week.get":({"cardNumber":S()},["cardNumber"],{"cardNumber":S(),"cardNumberLast4":S(),"productName":S(),"statementWeek":S("integer",enum=[1,2,3,4]),"statementDay":S("integer"),"statementDate":S(),"lastPayDate":S(),"nextStatementDate":S(),"nextLastPayDate":S(),"relationType":S(enum=["","M","C"]),"relatedCardNumber":S(),"relatedCardProductName":S()},"Current statement week. 404 FB_IVR_CHANNEL_121."),
 "statement.week.decide":({"cardNumber":S(),"newStatementWeek":S(enum=["1","2","3","4"]),"statementDay":S()},["cardNumber","newStatementWeek","statementDay"],{"statementDate":S(),"statementDueDate":S(),"statementDay":S("integer"),"responseCode":S("integer"),"responseMessage":S()},"Preview of dates for a week; changes nothing."),
 "statement.week.change":({"cardNumber":S(),"newStatementWeek":S(enum=["1","2","3","4"]),"statementDay":S()},["cardNumber","newStatementWeek","statementDay"],{"responseCode":S("integer"),"responseMessage":S(),"statementWeek":S(),"statementDay":S(),"exitState":S(enum=["OK"])},"Changes the statement week. Success = exitState OK and responseCode 0."),
 "contact.email.get":({"customerNo":S(),"intAddressInfoType":S(enum=["E","P","B"])},["customerNo","intAddressInfoType"],{"communicationType":S(enum=["Both","Phone","Email"]),"ibanCountryCode":S(),"ibanAreaCode":S(),"ibanPhoneNum":S(),"ibanEmail":S(),"ttsEmail":S(),"commGramType":S(),"exitState":S(enum=["Done"])},"Registered e-mail / phone."),
 "statement.pdf.send":({"customerNo":S(),"cardNumber":S(),"currencyType":S(enum=["TL","USD","EUR","GBP"]),"statementDate":S(),"emailAddress":S()},["customerNo","cardNumber","currencyType","statementDate","emailAddress"],{"exitState":S(enum=["DONE"])},"Sends the statement PDF. 404 FB_IVR_CHANNEL_107 = no PDF."),
}
paths={}
for name,(req,reqd,resp,summ) in ops.items():
    paths["/voice/v1/"+name]={"post":{"operationId":name,"summary":summ,
     "requestBody":{"required":True,"content":{"application/json":{"schema":{"type":"object","required":reqd,"properties":req}}}},
     "responses":{"200":{"description":"success, result.returnCode 1","content":{"application/json":{"schema":{"type":"object","properties":{"data":S("object",properties=resp),"result":RESULT}}}}},
                  "default":{"description":"error, result only","content":{"application/json":{"schema":{"type":"object","properties":{"result":RESULT}}}}}}}}
doc={"openapi":"3.0.3","info":{"title":"Freya Bank voice statement services","version":"2026-10-01","description":"Request body envelope is {data:{...fields}, call:{ani,lang}}; request schemas list the data fields."},
 "servers":[{"url":"https://btb-bank-mock.latif-akgun1907.workers.dev"}],"paths":paths}
json.dump(doc,open("out/final/tools.openapi.json","w",encoding="utf-8"),indent=1,ensure_ascii=False)
