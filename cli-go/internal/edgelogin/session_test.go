package edgelogin

import (
	"errors"
	"fmt"
	"testing"

	"github.com/chromedp/cdproto"
	"github.com/chromedp/cdproto/network"
	"github.com/chromedp/chromedp"
)

func TestBrowserErrorLoggerSuppressesLegacyAddressSpaceEvent(t *testing.T) {
	var logged []string
	logError := browserErrorLogger(func(format string, args ...any) {
		logged = append(logged, fmt.Sprintf(format, args...))
	})
	const eventError = "could not unmarshal event: %v"
	decodeEvent := func(addressSpace string) error {
		t.Helper()
		_, err := cdproto.UnmarshalMessage(&cdproto.Message{
			Method: cdproto.EventNetworkResponseReceivedExtraInfo,
			Params: []byte(fmt.Sprintf(`{"resourceIPAddressSpace":%q}`, addressSpace)),
		}, chromedp.DefaultUnmarshalOptions)
		if err == nil {
			t.Fatalf("expected a decode error for %q", addressSpace)
		}
		return err
	}
	legacyError := decodeEvent("Private")
	logError(eventError, legacyError)
	logError(eventError, errors.New(`json: unable to unmarshal JSON string into Go network.IPAddressSpace within "/resourceIPAddressSpace": unknown IPAddressSpace value: Private`))
	if len(logged) != 0 {
		t.Fatalf("logged the known compatibility error: %v", logged)
	}

	otherError := decodeEvent("Unexpected")
	logError(eventError, otherError)
	logError("could not unmarshal response: %v", legacyError)
	if len(logged) != 2 || logged[0] != "ERROR: could not unmarshal event: "+otherError.Error() ||
		logged[1] != "ERROR: could not unmarshal response: "+legacyError.Error() {
		t.Fatalf("unexpected diagnostics: %v", logged)
	}
}

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

func TestFirstScopePermissionUsesJSONOrder(t *testing.T) {
	for _, tc := range []struct{ raw, want string }{
		{`{"roles":{"scopePermissions":{"pps":{"read":true},"browswer":{}}}}`, "pps"},
		{`{"roles":{"scopePermissions":{"browswer":{},"pps":{}}}}`, "browswer"},
		{`{"roles":{"scopePermissions":{}}}`, ""},
		{`{"roles":{"scopePermissions":null}}`, ""},
		{`{"roles":{"scopePermissions":["pps"]}}`, ""},
		{`{"roles":{"scopePermissions":{"pps":`, ""},
		{`{"roles":{}}`, ""},
	} {
		if got := firstScopePermission(tc.raw); got != tc.want {
			t.Errorf("first scope for %s = %q, want %q", tc.raw, got, tc.want)
		}
	}
}

func TestParseBrowserAdminFlags(t *testing.T) {
	flag := func(value bool) *bool { return &value }
	for _, tc := range []struct {
		fields           string
		super, supporter *bool
	}{
		{`"isSuperAdmin":true,"isAISupporter":false`, flag(true), flag(false)},
		{`"isSuperAdmin":false,"isAISupporter":true`, flag(false), flag(true)},
		{`"isSuperAdmin":true,"isAISupporter":true`, flag(true), flag(true)},
		{`"isSuperAdmin":false,"isAISupporter":false`, flag(false), flag(false)},
		{`"isAISupporter":"true"`, nil, nil},
	} {
		result := parseUserInfo(fmt.Appendf(nil, `{"result":{"code":0,"username":"alice",%s}}`, tc.fields))
		match := func(got, want *bool) bool {
			return got == nil && want == nil || got != nil && want != nil && *got == *want
		}
		if result.Username != "alice" || !match(result.IsSuperAdmin, tc.super) || !match(result.IsAISupporter, tc.supporter) {
			t.Errorf("incorrect role parsing: %s", tc.fields)
		}
	}
}
