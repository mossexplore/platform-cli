package edgelogin

import (
	"testing"

	"github.com/chromedp/cdproto/network"
)

func TestAcceptSameOriginCompletedUserInfo(t *testing.T) {
	const endpoint = "https://preview.example.test/ai/user/info"
	attempt := &userInfoRequest{url: endpoint}
	request := func(url string) {
		attempt.observe(&network.EventRequestWillBeSent{RequestID: "id", Request: &network.Request{
			URL: url, Method: "GET", Headers: network.Headers{"X-Csrf-Token": "mock-value"},
		}})
	}
	response := func(url string) {
		attempt.observe(&network.EventResponseReceived{
			RequestID: "id", Response: &network.Response{URL: url, Status: 200},
		})
		attempt.observe(&network.EventLoadingFinished{RequestID: "id", EncodedDataLength: 50})
	}
	request("https://unrelated.example.test/ai/user/info")
	response(endpoint)
	if id, _ := attempt.ready(); id != "" {
		t.Fatal("accepted a cross-origin request")
	}
	request(endpoint + "?local=1")
	response("https://unrelated.example.test/ai/user/info")
	if id, _ := attempt.ready(); id != "" {
		t.Fatal("accepted a cross-origin response")
	}
	request(endpoint)
	response(endpoint)
	if id, token := attempt.ready(); id != "id" || token != "mock-value" {
		t.Fatal("failed to accept a complete same-origin request and response")
	}
	request("https://unrelated.example.test/intermediate")
	if id, _ := attempt.ready(); id != "" {
		t.Fatal("accepted headers after redirect")
	}
}

func TestParseBrowserIdentityAndBusiness(t *testing.T) {
	result := parseUserInfo([]byte(`{"result":{"code":0,"username":"alice","cnName":"张三","department":"平台部"},"more":true}`))
	if result.Username != "alice" || result.ChineseName != "张三" || result.Department != "平台部" {
		t.Fatalf("identity: %+v", result)
	}
	result = parseUserInfo([]byte(`{"result":{"code":0,"username":"alice","department":{"name":"平台部"}}}`))
	if result.Username != "alice" || result.Department != "" {
		t.Fatalf("identity with non-string department: %+v", result)
	}
	for _, value := range []string{`{}`, `{"result":{"username":"alice"}}`, `{"result":{"code":0,"username":"x\nY"}}`} {
		if result := parseUserInfo([]byte(value)); result.Username != "" {
			t.Fatalf("accepted invalid identity: %q", result.Username)
		}
	}
	catalog, err := parseCatalog(`[
		{"settleTenantName":"{\"cn\":\"部门\"}","value":123,
		 "teamList":[{"teamId":"team","key":"alias","teamStatus":"available","businessId":"value"}]},
		{"settleTenantName":{"cn":"部门"},"value":"second","additional":true}
	]`)
	if err != nil || len(catalog) != 1 || len(catalog[0].Tenants) != 2 ||
		catalog[0].Tenants[0].ID != "123" || catalog[0].Tenants[0].Teams[0].BusinessID != "value" {
		t.Fatalf("unexpected catalog: %+v %v", catalog, err)
	}
}
