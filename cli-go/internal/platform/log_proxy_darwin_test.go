package platform

import "testing"

func TestMacHTTPSProxy(t *testing.T) {
	const output = `<dictionary> {
  ExceptionsList : <array> {
    0 : *.internal.test
  }
  ExcludeSimpleHostnames : 1
  HTTPSEnable : 1
  HTTPSPort : 8080
  HTTPSProxy : general-proxy.test
  __SCOPED__ : <dictionary> {
    en0 : <dictionary> {
      HTTPSEnable : 1
      HTTPSPort : 8081
      HTTPSProxy : scoped-proxy.test
    }
  }
}`
	got := macHTTPSProxy(output)
	want := logProxySettings{"general-proxy.test:8080", "*.internal.test,<local>"}
	if got != want {
		t.Fatalf("system proxy = %+v, want %+v", got, want)
	}
}
