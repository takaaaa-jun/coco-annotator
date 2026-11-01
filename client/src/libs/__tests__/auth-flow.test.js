import { authDestination, loginErrorMessage } from "@/libs/auth-flow";

describe("authentication routing", () => {
  it("preserves image and filename range routes", () => {
    const route = "/dataset/2?file_name__icontains=04001-05000";
    expect(authDestination(route)).toBe(route);
    expect(authDestination("/annotate/4001?category_id=101")).toBe("/annotate/4001?category_id=101");
  });
  it.each([null, {}, "https://other.example", "//other.example", "/auth", "/auth?redirect=x", "/" + String.fromCharCode(92) + "other.example", "/dataset/2" + String.fromCharCode(10)])("rejects invalid destinations: %j", route => {
    expect(authDestination(route)).toBeNull();
  });
  it("explains credentials and network failures separately without exposing account existence", () => {
    expect(loginErrorMessage({ response: { status: 400 } })).toContain("check_annotatorとは別");
    expect(loginErrorMessage({ response: { status: 401 } })).toContain("ユーザー名またはパスワード");
    expect(loginErrorMessage(new Error("offline"))).toContain("接続状態");
  });
});
